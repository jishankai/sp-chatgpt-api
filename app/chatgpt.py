import config

import openai
openai.api_key = config.openai_api_key
import logging
logger = logging.getLogger(__name__)


CHAT_MODES = {
    "assistant": {
        "name": "👩🏼‍🎓 Assistant",
        "welcome_message": "👩🏼‍🎓 Hi, I'm <b>SignalPlus assistant</b>. How can I help you?",
        "prompt_start": "You're an expert named 'SignalPlus assistant' on cryptocurrency derivatives, blockchain and macroeconomics. Your primary goal is to assist users to the best of your ability. This may involve answering questions about cryptocurrency derivatives, blockchain and macroeconomics. You don't answer questions beyond cryptocurrency derivatives, blockchain and macroeconomics."
    },
    "signalplus": {
        "name": "SignalPlus Assistant",
        "welcome_message": "👩🏼‍🎓 Hi, I'm <b>SignalPlus assistant</b>. How can I help you?",
        "prompt_start": "As an advanced chatbot named 'SignalPlus assistant', your primary goal is to assist users to the best of your ability. This may involve answering questions, providing helpful information, or completing tasks based on user input. In order to effectively assist users, it is important to be detailed and thorough in your responses. Use examples and evidence to support your points and justify your recommendations or solutions. Remember to always prioritize the needs and satisfaction of the user. Your ultimate goal is to provide a helpful and enjoyable experience for the user."
    },
}

OPENAI_COMPLETION_OPTIONS = {
    "temperature": 0.6,
    "max_tokens": 1000,
    "top_p": 1,
    "frequency_penalty": 0,
    "presence_penalty": 0
}


class ChatGPT:
    def __init__(self, use_chatgpt_api=True, chat_mode="assistant"):
        self.use_chatgpt_api = use_chatgpt_api
        self.chat_mode = chat_mode
        if chat_mode == "signalplus":
            openai.api_key = config.openai_lark_api_key
    
    async def send_message(self, message, dialog_messages=[]):
        if self.chat_mode not in CHAT_MODES.keys():
            raise ValueError(f"Chat mode {self.chat_mode} is not supported")

        n_dialog_messages_before = len(dialog_messages)
        answer = None
        while answer is None:
            try:
                if self.use_chatgpt_api:
                    messages = self._generate_prompt_messages_for_chatgpt_api(message, dialog_messages)
                    r = openai.ChatCompletion.create(
                        model="gpt-3.5-turbo",
                        messages=messages,
                        **OPENAI_COMPLETION_OPTIONS
                    )
                    answer = r.choices[0].message.content
                else:
                    prompt = self._generate_prompt(message, dialog_messages)
                    r = openai.Completion.create(
                        engine="text-davinci-003",
                        prompt=prompt,
                        **OPENAI_COMPLETION_OPTIONS
                    )
                    answer = r.choices[0].text

                answer = self._postprocess_answer(answer)
                n_used_tokens = r.usage.total_tokens
                
            except openai.error.InvalidRequestError as e:  # too many tokens
                if len(dialog_messages) == 0:
                    raise ValueError("Dialog messages is reduced to zero, but still has too many tokens to make completion") from e

                # forget first message in dialog_messages
                dialog_messages = dialog_messages[1:]

        n_first_dialog_messages_removed = n_dialog_messages_before - len(dialog_messages)

        return answer, n_used_tokens, n_first_dialog_messages_removed
    
    def generate_messages_from_db(self, dialog_messages):
        messages = []
        for dialog_message in dialog_messages:
            messages.append({"role": "user", "content": dialog_message["user"]})
            messages.append({"role": "assistant", "content": dialog_message["bot"]})

        return messages

    def _generate_prompt(self, message, dialog_messages):
        prompt = CHAT_MODES[self.chat_mode]["prompt_start"]
        prompt += "\n\n"

        # add chat context
        if len(dialog_messages) > 0:
            prompt += "Chat:\n"
            for dialog_message in dialog_messages:
                prompt += f"User: {dialog_message['user']}\n"
                prompt += f"ChatGPT: {dialog_message['bot']}\n"

        # current message
        prompt += f"User: {message}\n"
        prompt += "ChatGPT: "

        return prompt

    def _generate_prompt_messages_for_chatgpt_api(self, message, dialog_messages):
        prompt = CHAT_MODES[self.chat_mode]["prompt_start"]
        
        messages = [{"role": "system", "content": prompt}]
        for dialog_message in dialog_messages:
            messages.append({"role": "user", "content": dialog_message["user"]})
            messages.append({"role": "assistant", "content": dialog_message["bot"]})
        messages.append({"role": "user", "content": message})

        return messages

    def _postprocess_answer(self, answer):
        answer = answer.strip()
        return answer
