class ConversationMemoryService:

    def __init__(self):
        self.messages = []

    def add_user_message(self, message):

        self.messages.append({
            "role": "user",
            "content": message
        })

        self.trim_history()

    def add_assistant_message(self, message):

        self.messages.append({
            "role": "assistant",
            "content": message
        })

        self.trim_history()

    def trim_history(self):
        # Keep only the last 20 messages
        # (10 user + 10 assistant)
        if len(self.messages) > 20:
            self.messages = self.messages[-20:]

    def get_history(self):

        history = ""

        for message in self.messages:
            history += f"{message['role'].upper()}: {message['content']}\n"

        return history

    def clear(self):
        self.messages = []