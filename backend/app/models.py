from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey, JSON
from sqlalchemy.sql import func
from app.core.db import Base


class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    status = Column(String(50), default="NEW")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Target(Base):
    __tablename__ = "targets"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    host = Column(String(200), nullable=False)
    port = Column(Integer, default=22)
    username = Column(String(200), nullable=False)
    enc_secret = Column(Text, nullable=False)  # password (encrypted)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LLMConnection(Base):
    __tablename__ = "llm_connections"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    type = Column(String(50), nullable=False)  # ollama/openai
    base_url = Column(String(500), nullable=True)
    enc_api_key = Column(Text, nullable=True)
    selected_model = Column(String(200), nullable=True)
    timeout_s = Column(Integer, default=300)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class KBDocument(Base):
    __tablename__ = "kb_documents"
    id = Column(Integer, primary_key=True)
    filename = Column(String(300), nullable=False)
    mime = Column(String(100), nullable=False)
    storage_path = Column(String(500), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class KBChunk(Base):
    __tablename__ = "kb_chunks"
    id = Column(Integer, primary_key=True)
    doc_id = Column(Integer, ForeignKey("kb_documents.id"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)


class Requirement(Base):
    __tablename__ = "requirements"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    target_id = Column(Integer, ForeignKey("targets.id"), nullable=True)
    text = Column(Text, nullable=False)
    structured = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Plan(Base):
    __tablename__ = "plans"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    status = Column(String(50), default="DRAFT")  # DRAFT/APPROVED
    plan_json = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=False)
    status = Column(String(50), default="QUEUED")  # QUEUED/RUNNING/DONE/FAILED/NEEDS_INPUT
    current_step = Column(Integer, default=0)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class TaskLog(Base):
    __tablename__ = "task_logs"
    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    level = Column(String(20), default="INFO")
    message = Column(Text, nullable=False)
    ts = Column(DateTime(timezone=True), server_default=func.now())


class Artifact(Base):
    __tablename__ = "artifacts"
    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    kind = Column(String(50), nullable=False)  # evidence/script/report/file
    name = Column(String(200), nullable=False)
    storage_path = Column(String(500), nullable=False)
    meta_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    kind = Column(String(50), nullable=False)  # req/impl/issue/final
    content_md = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
