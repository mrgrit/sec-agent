from sqlalchemy.orm import Session
from app.core.db import SessionLocal
from app.models import Task
from app.services.agent.state_machine import execute_suricata_ids


def run_task(task_id: int):
    db: Session = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return
        execute_suricata_ids(db, task)
    finally:
        db.close()
