import os
import logging
import traceback
import html
import json
from datetime import datetime

import config
import database
import chatgpt


# setup
db = database.Database()
logger = logging.getLogger(__name__)

# api server
from flask import Flask, request, jsonify
app = Flask(__name__)


@app.route('/api/messages', methods=['GET'])
async def get_messages():
    user_id = request.args.get('user_id')
    await register_user_if_not_exists(user_id)
    chatgpt_instance = chatgpt.ChatGPT(use_chatgpt_api=config.use_chatgpt_api)
    messages = chatgpt_instance.generate_messages_from_db(
        dialog_messages=db.get_dialog_messages(user_id, dialog_id=None),
        chat_mode=db.get_user_attribute(user_id, "current_chat_mode"),
    )
     
    return jsonify(messages)

@app.route('/api/message', methods=['POST'])
async def post_message():
    user_id = request.form.get('user_id')
    message = request.form.get('message')
    await register_user_if_not_exists(user_id)
    if (datetime.now() - db.get_user_attribute(user_id, "last_interaction")).seconds > config.new_dialog_timeout and len(db.get_dialog_messages(user_id)) > 0:
        db.start_new_dialog(user_id)
    db.set_user_attribute(user_id, "last_interaction", datetime.now())
    try:
        chatgpt_instance = chatgpt.ChatGPT(use_chatgpt_api=config.use_chatgpt_api)
        answer, n_used_tokens, n_first_dialog_messages_removed = chatgpt_instance.send_message(
            message,
            dialog_messages=db.get_dialog_messages(user_id, dialog_id=None),
            chat_mode=db.get_user_attribute(user_id, "current_chat_mode"),
        )
        
        # update user data
        new_dialog_message = {"user": message, "bot": answer, "date": datetime.now()}
        db.set_dialog_messages(
            user_id,
            db.get_dialog_messages(user_id, dialog_id=None) + [new_dialog_message],
            dialog_id=None
        )

        db.set_user_attribute(user_id, "n_used_tokens", n_used_tokens + db.get_user_attribute(user_id, "n_used_tokens"))

    except Exception as e:
        error_text = f"Something went wrong during completion.\nReason: {e}"
        logger.error(error_text)
        return

    return jsonify({"answer": answer})

async def register_user_if_not_exists(user_id):
    if not db.check_if_user_exists(user_id):
        db.add_new_user(
            user_id,
        )
        db.start_new_dialog(user_id)

    if db.get_user_attribute(user_id, "current_dialog_id") is None:
        db.start_new_dialog(user_id)


if __name__ == "__main__":
    app.run(host="0.0.0.0")
