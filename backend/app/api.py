from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.core.db import SessionLocal
from app.core.crypto import encrypt_text, decrypt_text
from app.models import Project, Target, Requirement, Plan, Task, TaskLog, KBDocument, KBChunk, Artifact, Report, LLMConnection
from app.schemas import (
    ProjectCreate, ProjectOut,
    TargetCreate, TargetOut,
    RequirementUpsert, PlanOut,
    TaskOut,
    KBSearchReq,
    LLMConnCreate, LLMConnOut, LLMSelectModel
)
from app.core.config import settings
from app.services.rag_simple import chunk_text, bm25_search
from pathlib import Path
from datetime import datetime
import json
from redis import Redis
from rq import Queue
from app.worker.jobs import run_task as run_task_job
from app.services.agent.state_machine import build_suricata_ids_plan
from app.services.tools.ssh_tool import SSHRunner

router = APIRouter()


def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def rq_queue():
    redis_conn = Redis.from_url(settings.REDIS_URL)
    return Queue("default", connection=redis_conn)


@router.get("/health")
def health():
    return {"ok": True}


# -------- Projects --------
@router.post("/projects", response_model=ProjectOut)
def create_project(payload: ProjectCreate):
    db: Session = SessionLocal()
    try:
        p = Project(name=payload.name, status="NEW")
        db.add(p)
        db.commit()
        db.refresh(p)
        return ProjectOut(id=p.id, name=p.name, status=p.status)
    finally:
        db.close()


@router.get("/projects", response_model=list[ProjectOut])
def list_projects():
    db: Session = SessionLocal()
    try:
        ps = db.query(Project).order_by(Project.id.desc()).all()
        return [ProjectOut(id=p.id, name=p.name, status=p.status) for p in ps]
    finally:
        db.close()


# -------- Targets --------
@router.post("/targets", response_model=TargetOut)
def create_target(payload: TargetCreate):
    db: Session = SessionLocal()
    try:
        t = Target(
            name=payload.name,
            host=payload.host,
            port=payload.port,
            username=payload.username,
            enc_secret=encrypt_text(payload.password),
        )
        db.add(t)
        db.commit()
        db.refresh(t)
        return TargetOut(id=t.id, name=t.name, host=t.host, port=t.port, username=t.username)
    finally:
        db.close()


@router.get("/targets", response_model=list[TargetOut])
def list_targets():
    db: Session = SessionLocal()
    try:
        ts = db.query(Target).order_by(Target.id.desc()).all()
        return [TargetOut(id=t.id, name=t.name, host=t.host, port=t.port, username=t.username) for t in ts]
    finally:
        db.close()


@router.post("/targets/{target_id}/test-ssh")
def test_ssh(target_id: int):
    db: Session = SessionLocal()
    try:
        t = db.query(Target).filter(Target.id == target_id).first()
        if not t:
            raise HTTPException(404, "target not found")
        pw = decrypt_text(t.enc_secret)
        ssh = SSHRunner(t.host, t.port, t.username, pw, timeout_s=15)
        r = ssh.run("bash -lc 'echo OK; whoami; uname -a; id'", timeout_s=60)
        return r
    finally:
        db.close()


# -------- Requirements --------
@router.post("/projects/{project_id}/requirements")
def upsert_requirement(project_id: int, payload: RequirementUpsert):
    db: Session = SessionLocal()
    try:
        r = Requirement(project_id=project_id, target_id=payload.target_id, text=payload.text, structured=None)
        db.add(r)
        db.commit()
        return {"ok": True, "requirement_id": r.id}
    finally:
        db.close()


# -------- Clarify (MVP: rule-based placeholder) --------
@router.post("/projects/{project_id}/agent/clarify")
def clarify(project_id: int):
    db: Session = SessionLocal()
    try:
        req = db.query(Requirement).filter(Requirement.project_id == project_id).order_by(Requirement.id.desc()).first()
        if not req:
            raise HTTPException(400, "no requirement")
        questions = []
        if not req.target_id:
            questions.append({"field": "target_id", "question": "대상 서버(target)를 선택해줘."})
        # MVP: Suricata만, interface/home_net은 자동 추정 후 plan에서 보여줌
        done = len(questions) == 0
        return {"done": done, "questions": questions}
    finally:
        db.close()


# -------- Plan --------
@router.post("/projects/{project_id}/agent/plan", response_model=PlanOut)
def plan(project_id: int):
    db: Session = SessionLocal()
    try:
        req = db.query(Requirement).filter(Requirement.project_id == project_id).order_by(Requirement.id.desc()).first()
        if not req:
            raise HTTPException(400, "no requirement")
        if not req.target_id:
            raise HTTPException(400, "requirement missing target_id")
        target = db.query(Target).filter(Target.id == req.target_id).first()
        pw = decrypt_text(target.enc_secret)
        ssh = SSHRunner(target.host, target.port, target.username, pw, timeout_s=20)
        facts = {}
        # 최소 facts
        r = ssh.run("bash -lc 'ip -br link; ip -br addr'", timeout_s=60)
        primary = None
        for line in (r["stdout"] or "").splitlines():
            if "UP" in line and not line.strip().startswith("lo"):
                primary = line.split()[0]
                break
        facts["primary_iface"] = primary
        facts["home_net_guess"] = "[10.0.0.0/8,192.168.0.0/16]"

        plan_json = build_suricata_ids_plan(req.text, facts)
        p = Plan(project_id=project_id, status="DRAFT", plan_json=plan_json)
        db.add(p)
        db.commit()
        db.refresh(p)
        return PlanOut(id=p.id, status=p.status, plan_json=p.plan_json)
    finally:
        db.close()


@router.post("/projects/{project_id}/plan/{plan_id}/approve")
def approve_plan(project_id: int, plan_id: int):
    db: Session = SessionLocal()
    try:
        p = db.query(Plan).filter(Plan.id == plan_id, Plan.project_id == project_id).first()
        if not p:
            raise HTTPException(404, "plan not found")
        p.status = "APPROVED"
        db.commit()
        return {"ok": True}
    finally:
        db.close()


# -------- Execute --------
@router.post("/projects/{project_id}/agent/execute", response_model=TaskOut)
def execute(project_id: int, plan_id: int):
    db: Session = SessionLocal()
    try:
        p = db.query(Plan).filter(Plan.id == plan_id, Plan.project_id == project_id).first()
        if not p:
            raise HTTPException(404, "plan not found")
        if p.status != "APPROVED":
            raise HTTPException(400, "plan not approved")

        t = Task(project_id=project_id, plan_id=plan_id, status="QUEUED", current_step=0)
        db.add(t)
        db.commit()
        db.refresh(t)

        q = rq_queue()
        q.enqueue(run_task_job, t.id, job_timeout=60 * 60)  # 1h
        return TaskOut(id=t.id, status=t.status, current_step=t.current_step, error=t.error)
    finally:
        db.close()


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: int):
    db: Session = SessionLocal()
    try:
        t = db.query(Task).filter(Task.id == task_id).first()
        if not t:
            raise HTTPException(404, "task not found")
        return TaskOut(id=t.id, status=t.status, current_step=t.current_step, error=t.error)
    finally:
        db.close()


# -------- SSE logs --------
@router.get("/tasks/{task_id}/logs/stream")
def stream_logs(task_id: int):
    def event_gen():
        last_id = 0
        while True:
            db: Session = SessionLocal()
            try:
                logs = (
                    db.query(TaskLog)
                    .filter(TaskLog.task_id == task_id, TaskLog.id > last_id)
                    .order_by(TaskLog.id.asc())
                    .limit(100)
                    .all()
                )
                if logs:
                    for l in logs:
                        last_id = l.id
                        payload = {"ts": str(l.ts), "level": l.level, "message": l.message}
                        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                else:
                    yield "data: {}\n\n"
            finally:
                db.close()
            import time
            time.sleep(1)

    return StreamingResponse(event_gen(), media_type="text/event-stream")


# -------- Artifacts & Reports --------
@router.get("/tasks/{task_id}/artifacts")
def list_artifacts(task_id: int):
    db: Session = SessionLocal()
    try:
        arts = db.query(Artifact).filter(Artifact.task_id == task_id).order_by(Artifact.id.asc()).all()
        return [{"id": a.id, "kind": a.kind, "name": a.name, "path": a.storage_path, "meta": a.meta_json} for a in arts]
    finally:
        db.close()


@router.get("/artifacts/{artifact_id}/content")
def artifact_content(artifact_id: int):
    db: Session = SessionLocal()
    try:
        a = db.query(Artifact).filter(Artifact.id == artifact_id).first()
        if not a:
            raise HTTPException(404, "artifact not found")
        p = Path(a.storage_path)
        if not p.exists():
            raise HTTPException(404, "file missing")
        return {"name": a.name, "kind": a.kind, "content": p.read_text(encoding="utf-8", errors="replace")}
    finally:
        db.close()


@router.get("/projects/{project_id}/reports")
def list_reports(project_id: int):
    db: Session = SessionLocal()
    try:
        rs = db.query(Report).filter(Report.project_id == project_id).order_by(Report.id.asc()).all()
        return [{"id": r.id, "kind": r.kind, "content_md": r.content_md, "created_at": str(r.created_at)} for r in rs]
    finally:
        db.close()


# -------- KB Upload/Search --------
@router.post("/kb/upload")
def kb_upload(file: UploadFile = File(...)):
    db: Session = SessionLocal()
    try:
        base = Path(settings.STORAGE_DIR) / "kb"
        base.mkdir(parents=True, exist_ok=True)
        dest = base / f"{datetime.utcnow().timestamp()}_{file.filename}"
        content = file.file.read()
        dest.write_bytes(content)

        doc = KBDocument(filename=file.filename, mime=file.content_type or "application/octet-stream", storage_path=str(dest))
        db.add(doc)
        db.commit()
        db.refresh(doc)

        # MVP: 텍스트만(나중에 PDF 파서 추가)
        try:
            text = content.decode("utf-8", errors="replace")
        except Exception:
            text = ""

        chunks = chunk_text(text)
        for i, ch in enumerate(chunks):
            db.add(KBChunk(doc_id=doc.id, chunk_index=i, text=ch))
        db.commit()
        return {"ok": True, "doc_id": doc.id, "chunks": len(chunks)}
    finally:
        db.close()


@router.post("/kb/search")
def kb_search(payload: KBSearchReq):
    db: Session = SessionLocal()
    try:
        hits = bm25_search(db, payload.query, payload.top_k)
        return {"hits": hits}
    finally:
        db.close()


# -------- LLM Connection (MVP: 저장/선택만, 실제 호출은 다음 스텝) --------
@router.post("/llm/connections", response_model=LLMConnOut)
def llm_create(payload: LLMConnCreate):
    db: Session = SessionLocal()
    try:
        conn = LLMConnection(
            name=payload.name,
            type=payload.type,
            base_url=payload.base_url,
            enc_api_key=encrypt_text(payload.api_key) if payload.api_key else None,
            selected_model=None,
            timeout_s=settings.DEFAULT_LLM_TIMEOUT_S,
        )
        db.add(conn)
        db.commit()
        db.refresh(conn)
        return LLMConnOut(
            id=conn.id,
            name=conn.name,
            type=conn.type,
            base_url=conn.base_url,
            selected_model=conn.selected_model,
            timeout_s=conn.timeout_s,
        )
    finally:
        db.close()


@router.get("/llm/connections", response_model=list[LLMConnOut])
def llm_list():
    db: Session = SessionLocal()
    try:
        cs = db.query(LLMConnection).order_by(LLMConnection.id.desc()).all()
        return [
            LLMConnOut(
                id=c.id, name=c.name, type=c.type, base_url=c.base_url, selected_model=c.selected_model, timeout_s=c.timeout_s
            )
            for c in cs
        ]
    finally:
        db.close()


@router.post("/llm/{conn_id}/select")
def llm_select(conn_id: int, payload: LLMSelectModel):
    db: Session = SessionLocal()
    try:
        c = db.query(LLMConnection).filter(LLMConnection.id == conn_id).first()
        if not c:
            raise HTTPException(404, "not found")
        c.selected_model = payload.model
        c.timeout_s = payload.timeout_s
        db.commit()
        return {"ok": True}
    finally:
        db.close()
