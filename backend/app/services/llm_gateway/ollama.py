import httpx
from typing import List, Dict
from .base import LLMClient, Message

class OllamaClient(LLMClient):
    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def list_models(self) -> List[str]:
        # Ollama: GET /api/tags
        url = f"{self.base_url}/api/tags"
        with httpx.Client(timeout=30) as client:
            r = client.get(url)
            r.raise_for_status()
            data = r.json()
        models = []
        for m in data.get("models", []):
            name = m.get("name")
            if name:
                models.append(name)
        return models

    def chat(self, messages: List[Message], timeout_s: int = 300) -> str:
        # Ollama: POST /api/chat
        url = f"{self.base_url}/api/chat"
        payload: Dict = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        with httpx.Client(timeout=timeout_s) as client:
            r = client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
        # { message: { role, content }, ... }
        msg = data.get("message", {})
        return msg.get("content", "") or ""
