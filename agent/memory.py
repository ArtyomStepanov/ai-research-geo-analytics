"""Simple conversation memory with Database for the agent."""
from typing import Optional
from .db import load_chat_history, save_chat_history

class ConversationMemory:
    """Хранит историю диалога и контекст между шагами."""


    def __init__(self, system_prompt: str, max_turns: int = 10):
        self.system_prompt = system_prompt
        self.max_turns = max_turns
        self.history: list[dict] = [{"role": "system", "content": system_prompt}]


    def add_user_message(self, content: str):
        self.history.append({"role": "user", "content": content})


    def add_assistant_message(self, content: str, tool_calls: Optional[list] = None):
        msg = {"role": "assistant", "content": content}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        self.history.append(msg)


    def add_tool_result(self, tool_call_id: str, content: str):
        self.history.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content
        })


    def get_messages(self) -> list[dict]:
        """Возвращает сообщения для отправки в LLM, обрезая старые, если нужно."""
        # Оставляем system + последние (max_turns * 2) сообщений (пользователь+ассистент)
        if len(self.history) <= self.max_turns * 2 + 1:
            return self.history.copy()
        # Сохраняем system + последние сообщения
        return [self.history[0]] + self.history[-(self.max_turns * 2):]


    def clear(self):
        """Очистить память, оставив только system prompt."""
        self.history = [{"role": "system", "content": self.system_prompt}]

class PersistedMemory(ConversationMemory):
    """Расширенная память с автосохранением в SQLite."""
    def __init__(self, chat_id: str, system_prompt: str, max_turns: int = 10):
        super().__init__(system_prompt, max_turns)
        self.chat_id = chat_id
        self._load_from_db()

    def _load_from_db(self):
        db_history = load_chat_history(self.chat_id)
        if db_history:
            self.history = db_history
            # Гарантируем, что system prompt всегда первый
            if not self.history or self.history[0].get("role") != "system":
                self.history.insert(0, {"role": "system", "content": self.system_prompt})

    def save(self):
        """Сохраняет полную историю в БД."""
        save_chat_history(self.chat_id, self.history)