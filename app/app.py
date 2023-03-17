import os
import sys
import logging
import traceback
import html
import json
from datetime import datetime
import requests

sys.path.append(os.path.abspath(os.path.dirname(__file__)))
import config
import database
import chatgpt


# setup
db = database.Database()
logger = logging.getLogger(__name__)

# api server
from flask import Flask, request, jsonify
from flask_cors import CORS

ALLOWED_ORIGINS = [
    'https://feat-chat.front.signalplus.net',
    'https://t.signalplus.com',
    'https://fi.signalplus.com',
    'http://localhost:8000'
]
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": ALLOWED_ORIGINS}})

@app.route('/', methods=['GET'])
async def get():
    return jsonify({}), 200

@app.route('/lark', methods=['POST'])
async def handle_lark_request():
    # 解析请求 body
    obj = request.json

    schema = obj.get("schema", "")
    if schema == "2.0":
        event_id = obj["header"]["event_id"]
        if not db.check_if_lark_event_exists(event_id):
            db.add_new_lark_event(
                event_id,
            )
            # 根据 type 处理不同类型事件
            type = obj["header"]["event_type"]
            if "im.message.receive_v1" == type:  # 事件回调
                # 获取事件内容和类型，并进行相应处理，此处只关注给机器人推送的消息事件
                event = obj.get("event")
                await handle_message(event)
        return jsonify({}), 200

    else:
        # 校验 verification token 是否匹配，token 不匹配说明该回调并非来自开发平台
        token = obj.get("token", "")
        if token != config.lark_app_verification_token:
            logger.error(f"verification token not match, token = {token}")
        return jsonify({}), 200

async def handle_message(event):
    # 此处只处理 text 类型消息，其他类型消息忽略
    msg_type = event["message"]["message_type"]
    if msg_type != "text":
        logger.error("unknown msg_type =", msg_type)
        return

    # 调用 OpenAI API 生成回复
    open_id = event["sender"]["sender_id"]["open_id"]
    content = json.loads(event["message"]["content"])
    prompt = content["text"]
    if "@" in prompt:
        at_key = event["message"]["mentions"][0]["key"]
        prompt = prompt.replace(at_key, "")

    response = await generate_chatgpt_response(open_id, prompt, "signalplus")

    # 调用发消息 API 发送回复消息
    await send_message(event, response)

async def generate_chatgpt_response(user_id, message, chat_mode):
    await register_user_if_not_exists(user_id, chat_mode)
    if (datetime.now() - db.get_user_attribute(user_id, "last_interaction")).seconds > config.new_dialog_timeout and len(db.get_dialog_messages(user_id)) > 0:
        db.start_new_dialog(user_id)
    db.set_user_attribute(user_id, "last_interaction", datetime.now())
    try:
        chatgpt_instance = chatgpt.ChatGPT(use_chatgpt_api=config.use_chatgpt_api, chat_mode=chat_mode)
        answer, n_used_tokens, n_first_dialog_messages_removed = await chatgpt_instance.send_message(
            message,
            dialog_messages=db.get_dialog_messages(user_id, dialog_id=None),
        )
        
        # update user data
        new_dialog_message = {"user": message, "bot": answer, "date": datetime.now()}
        db.set_dialog_messages(
            user_id,
            db.get_dialog_messages(user_id, dialog_id=None) + [new_dialog_message],
            dialog_id=None
        )

        db.set_user_attribute(user_id, "n_used_tokens", n_used_tokens + db.get_user_attribute(user_id, "n_used_tokens"))

        return answer

    except Exception as e:
        error_text = f"Something went wrong during completion.\nReason: {e}"
        logger.error(error_text)
        return

async def send_message(event, text):
    url = "https://open.feishu.cn/open-apis/message/v4/send/"

    token = await get_tenant_access_token()
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + token
    }

    content = json.loads(event["message"]["content"])
    message = content["text"]
    if "@" in message and event["message"]["mentions"][0]["name"]=="ChatGPT":
        # This message is an @ message
        chat_id = event["message"]["chat_id"]
        message_id = event["message"]["message_id"]
        sender_id = event["sender"]["sender_id"]["open_id"]
        req_body = {
            "chat_id": chat_id,
            "msg_type": "text",
            "content": {
                "text": text
            },
            "root_id": message_id,
            "user_id": sender_id
        }
    else:
        open_id = event["sender"]["sender_id"]["open_id"]
        req_body = {
            "open_id": open_id,
            "msg_type": "text",
            "content": {
                "text": text
            }
        }

    response = requests.post(url, headers=headers, json=req_body)
    if response.status_code != 200:
        logger.error("send message error, status_code = ", response.status_code)

async def get_tenant_access_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal/"
    headers = {
        "Content-Type" : "application/json"
    }
    req_body = {
        "app_id": config.lark_app_id,
        "app_secret": config.lark_app_secret
    }

    try:
        response = requests.post(url, headers=headers, json=req_body)
    except Exception as e:
        logger.error(e)
        return

    rsp_dict = response.json()
    code = rsp_dict.get("code", -1)
    if code == 0:
        return rsp_dict.get("tenant_access_token", "")
    else:
        logger.error(f"get tenant_access_token error, code = {code}")


@app.route('/api/messages', methods=['GET'])
async def get_messages():
    user_id = request.args.get('user_id')
    await register_user_if_not_exists(user_id, "assistant")
    chatgpt_instance = chatgpt.ChatGPT(use_chatgpt_api=config.use_chatgpt_api)
    messages = chatgpt_instance.generate_messages_from_db(
        dialog_messages=db.get_dialog_messages(user_id, dialog_id=None),
    )
     
    return jsonify(succ=True, code=0, message="", value=messages)

@app.route('/api/message', methods=['POST'])
async def post_message():
    request_data = request.json
    user_id = request_data.get('user_id')
    message = request_data.get('message')
    answer = await generate_chatgpt_response(user_id, message, "assistant")

    return jsonify(succ=True, code=0, message="", value=answer)

async def register_user_if_not_exists(user_id, chat_mode):
    if not db.check_if_user_exists(user_id):
        db.add_new_user(
            user_id,
            chat_mode,
        )
        db.start_new_dialog(user_id)

    if db.get_user_attribute(user_id, "current_dialog_id") is None:
        db.start_new_dialog(user_id)


if __name__ == "__main__":
    app.run(host="0.0.0.0")
