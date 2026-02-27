from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

Message = Dict[str, str]  # {"role": "system|user|assistant", "content": "..."}

class LLMClient(ABC):
    @abstractmethod
    def list_models(self) -> List[str]:
        raise NotImplementedError

    @abstractmethod
    def chat(self, messages: List[Message], timeout_s: int = 300) -> str:
        raise NotImplementedError
