from pydantic import BaseModel
from typing import Optional, Any


class ProjectCreate(BaseModel):
    name: str


class ProjectOut(BaseModel):
    id: int
    name: str
    status: str


class TargetCreate(BaseModel):
    name: str
    host: str
    port: int = 22
    username: str
    password: str


class TargetOut(BaseModel):
    id: int
    name: str
    host: str
    port: int
    username: str


class RequirementUpsert(BaseModel):
    target_id: Optional[int] = None
    text: str


class PlanOut(BaseModel):
    id: int
    status: str
    plan_json: Any


class TaskOut(BaseModel):
    id: int
    status: str
    current_step: int
    error: Optional[str] = None


class LLMConnCreate(BaseModel):
    name: str
    type: str  # ollama/openai
    base_url: Optional[str] = None
    api_key: Optional[str] = None


class LLMConnOut(BaseModel):
    id: int
    name: str
    type: str
    base_url: Optional[str] = None
    selected_model: Optional[str] = None
    timeout_s: int


class LLMSelectModel(BaseModel):
    model: str
    timeout_s: int = 300


class KBSearchReq(BaseModel):
    query: str
    top_k: int = 5


class KBSearchHit(BaseModel):
    doc_id: int
    chunk_id: int
    score: float
    text: str
