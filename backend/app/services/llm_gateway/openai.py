import httpx
from typing import List
from .base import LLMClient, Message

class OpenAIClient(LLMClient):
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def list_models(self) -> List[str]:
        # MVP: 고정 리스트로 반환 (나중에 실제 모델 리스트 API로 확장)
        return [self.model]

    def chat(self, messages: List[Message], timeout_s: int = 300) -> str:
        # OpenAI Responses API 대신 간단히 Chat Completions 형태로 호출(향후 공식 방식으로 교체 권장)
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {"model": self.model, "messages": messages, "temperature": 0}

        with httpx.Client(timeout=timeout_s) as client:
            r = client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()

        return data["choices"][0]["message"]["content"]
