import json
from datetime import datetime
from sqlalchemy.orm import Session
from app.models import Task, TaskLog, Artifact, Target, Requirement, Plan, Report, Project
from app.core.crypto import decrypt_text
from app.core.config import settings
from app.services.tools.ssh_tool import SSHRunner
from pathlib import Path


def _log(db: Session, task_id: int, msg: str, level: str = "INFO"):
    db.add(TaskLog(task_id=task_id, level=level, message=msg))
    db.commit()


def _save_artifact(db: Session, task_id: int, kind: str, name: str, content: str, meta=None):
    meta = meta or {}
    base = Path(settings.STORAGE_DIR) / "artifacts" / str(task_id)
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{name}.txt"
    path.write_text(content, encoding="utf-8")
    art = Artifact(task_id=task_id, kind=kind, name=name, storage_path=str(path), meta_json=meta)
    db.add(art)
    db.commit()
    return art.id


def build_suricata_ids_plan(requirement_text: str, target_facts: dict):
    # MVP: 질문/응답은 이후 고도화. 지금은 "Suricata IDS 설치" 고정 플랜
    iface = target_facts.get("primary_iface") or "<IFACE>"
    home_net = target_facts.get("home_net_guess") or "[10.0.0.0/8,192.168.0.0/16]"

    plan = {
        "title": "Install & configure Suricata (IDS)",
        "assumptions": {
            "iface": iface,
            "home_net": home_net,
            "mode": "IDS",
        },
        "todos": [
            {"id": "T1", "title": "Precheck OS/NIC/Disk", "status": "PENDING"},
            {"id": "T2", "title": "Install packages", "status": "PENDING"},
            {"id": "T3", "title": "Write config + local.rules", "status": "PENDING"},
            {"id": "T4", "title": "Config test (suricata -T)", "status": "PENDING"},
            {"id": "T5", "title": "Enable & start service", "status": "PENDING"},
            {"id": "T6", "title": "Smoke test (curl) + verify eve.json alert", "status": "PENDING"},
        ],
        "tests": [
            "suricata -T -c /etc/suricata/suricata.yaml",
            "systemctl is-active suricata",
            "test -f /var/log/suricata/eve.json",
            'tail -n 200 /var/log/suricata/eve.json | grep -n "LOCAL TEST" | tail -n 3',
        ],
        "rollback": [
            "cp /etc/suricata/suricata.yaml.bak.* /etc/suricata/suricata.yaml (select latest)",
            "systemctl restart suricata",
        ],
    }
    return plan


def gather_target_facts(ssh: SSHRunner):
    facts = {}
    r = ssh.run("bash -lc 'cat /etc/os-release | head -n 3; uname -a; ip -br link; ip -br addr'", timeout_s=120)
    txt = r["stdout"] + "\n" + r["stderr"]
    # 아주 단순한 iface 추정: 첫 번째 UP 인터페이스
    primary = None
    for line in (r["stdout"] or "").splitlines():
        if "UP" in line and not line.strip().startswith("lo"):
            primary = line.split()[0]
            break
    facts["primary_iface"] = primary
    facts["home_net_guess"] = "[10.0.0.0/8,192.168.0.0/16]"
    return facts, txt


def execute_suricata_ids(db: Session, task: Task):
    task.status = "RUNNING"
    task.started_at = datetime.utcnow()
    db.commit()

    plan = db.query(Plan).filter(Plan.id == task.plan_id).first()
    req = db.query(Requirement).filter(Requirement.project_id == task.project_id).order_by(Requirement.id.desc()).first()
    if not plan or not req or not req.target_id:
        task.status = "FAILED"
        task.error = "Missing plan/requirement/target"
        task.finished_at = datetime.utcnow()
        db.commit()
        return

    target = db.query(Target).filter(Target.id == req.target_id).first()
    if not target:
        task.status = "FAILED"
        task.error = "Target not found"
        task.finished_at = datetime.utcnow()
        db.commit()
        return

    password = decrypt_text(target.enc_secret)
    ssh = SSHRunner(target.host, target.port, target.username, password, timeout_s=30)

    _log(db, task.id, f"Connected target: {target.host}:{target.port} as {target.username}")

    # T1: precheck + facts
    facts, evidence = gather_target_facts(ssh)
    _save_artifact(db, task.id, "evidence", "milestone_T1_precheck", evidence, meta={"facts": facts})
    _log(db, task.id, f"Facts: {json.dumps(facts)}")

    iface = plan.plan_json.get("assumptions", {}).get("iface") or facts.get("primary_iface") or "eth0"
    home_net = plan.plan_json.get("assumptions", {}).get("home_net") or facts.get("home_net_guess")

    # T2: install
    cmd_install = "bash -lc 'sudo apt update && sudo apt install -y suricata jq'"
    r = ssh.run(cmd_install, timeout_s=900)
    _save_artifact(db, task.id, "evidence", "milestone_T2_install", r["stdout"] + "\n" + r["stderr"])
    if r["exit_code"] != 0:
        task.status = "FAILED"
        task.error = "Install failed"
        db.commit()
        return
    _log(db, task.id, "Packages installed.")

    # T3: config + rules
    cmd_cfg = f"""bash -lc '
set -euo pipefail
sudo cp -a /etc/suricata/suricata.yaml /etc/suricata/suricata.yaml.bak.$(date +%F_%H%M%S) || true
sudo install -d -m 0755 /etc/suricata/rules
sudo tee /etc/suricata/rules/local.rules >/dev/null <<\\EOF
alert http any any -> any any (msg:"LOCAL TEST - HTTP request detected"; flow:to_server,established; http.method; content:"GET"; sid:1000001; rev:1;)
EOF

sudo tee /etc/suricata/suricata.yaml >/dev/null <<\\EOF
vars:
  address-groups:
    HOME_NET: "{home_net}"
    EXTERNAL_NET: "!$HOME_NET"

af-packet:
  - interface: {iface}
    cluster-id: 99
    cluster-type: cluster_flow
    defrag: yes

outputs:
  - eve-log:
      enabled: yes
      filetype: regular
      filename: /var/log/suricata/eve.json
      types:
        - alert:
            tagged-packets: yes
        - http
        - dns
        - tls
        - flow

logging:
  default-log-level: notice

default-rule-path: /etc/suricata/rules
rule-files:
  - local.rules
EOF
'
"""
    r = ssh.run(cmd_cfg, timeout_s=300)
    _save_artifact(db, task.id, "evidence", "milestone_T3_config", r["stdout"] + "\n" + r["stderr"], meta={"iface": iface, "home_net": home_net})
    if r["exit_code"] != 0:
        task.status = "FAILED"
        task.error = "Config write failed"
        db.commit()
        return
    _log(db, task.id, f"Config written. iface={iface}")

    # T4: test
    r = ssh.run("bash -lc 'sudo suricata -T -c /etc/suricata/suricata.yaml'", timeout_s=240)
    _save_artifact(db, task.id, "evidence", "milestone_T4_test", r["stdout"] + "\n" + r["stderr"])
    if r["exit_code"] != 0:
        task.status = "FAILED"
        task.error = "suricata -T failed"
        db.commit()
        return
    _log(db, task.id, "suricata -T OK")

    # T5: enable/start
    r = ssh.run("bash -lc 'sudo systemctl enable --now suricata && systemctl is-active suricata'", timeout_s=240)
    _save_artifact(db, task.id, "evidence", "milestone_T5_service", r["stdout"] + "\n" + r["stderr"])
    if "active" not in (r["stdout"] or ""):
        task.status = "FAILED"
        task.error = "service not active"
        db.commit()
        return
    _log(db, task.id, "Service active.")

    # T6: smoke test
    smoke = "bash -lc 'curl -I http://example.com/ || true; sudo tail -n 200 /var/log/suricata/eve.json | grep -n \"LOCAL TEST\" | tail -n 3 || true'"
    r = ssh.run(smoke, timeout_s=240)
    _save_artifact(db, task.id, "evidence", "milestone_T6_smoke", r["stdout"] + "\n" + r["stderr"])
    if "LOCAL TEST" not in (r["stdout"] or "") and "LOCAL TEST" not in (r["stderr"] or ""):
        _log(db, task.id, "Smoke test did not find LOCAL TEST. (May be no traffic or http parsing.)", level="WARN")
        # MVP: 실패로 처리하지 않고 NEEDS_INPUT로 전환
        task.status = "NEEDS_INPUT"
        task.error = "Smoke test not confirmed. Check interface/traffic."
        task.finished_at = datetime.utcnow()
        db.commit()
        return

    _log(db, task.id, "Smoke test OK. Installation complete.")

    # reports (초안)
    _generate_reports(db, task.project_id, plan.plan_json, req.text, target, task.id)

    task.status = "DONE"
    task.finished_at = datetime.utcnow()
    db.commit()

def _generate_reports(db: Session, project_id: int, plan_json: dict, req_text: str, target: Target, task_id: int):
    import json

    req_md = (
        "# 요구사항 분석 보고서\n"
        f"- 대상: {target.name} ({target.host}:{target.port})\n"
        "- 요구사항(원문):\n"
        "```\n"
        f"{req_text}\n"
        "```\n\n"
        "## 해석(초안)\n"
        "- Suricata IDS 설치 및 기본 설정\n"
        "- eve.json 로그 생성 확인\n"
        "- 로컬 테스트 룰로 동작 검증\n"
    )

    impl_md = (
        "# 기능구현 보고서\n"
        "## 적용 계획\n"
        "```json\n"
        f"{json.dumps(plan_json, indent=2, ensure_ascii=False)}\n"
        "```\n\n"
        "## 산출물\n"
        f"- 마일스톤 증빙(artifacts): task_id={task_id} 하위에 저장됨\n"
        "- 설정 파일: /etc/suricata/suricata.yaml\n"
        "- 로컬 룰: /etc/suricata/rules/local.rules\n"
        "- 로그: /var/log/suricata/eve.json\n"
    )

    issue_md = (
        "# 이슈 보고서\n"
        "- 실패/경고가 발생한 경우, 해당 마일스톤 증빙을 기반으로 원인/조치 내역을 기록합니다.\n"
        "- MVP에서는 자동 작성의 초안만 생성합니다.\n"
    )

    final_md = (
        "# 완료 보고서\n"
        "## 완료 기준(DoD)\n"
        "- 설치 완료\n"
        "- 설정 적용\n"
        "- 서비스 active\n"
        "- 검증(테스트/증빙) 저장\n\n"
        "## 운영 가이드(초안)\n"
        "- 상태 확인: systemctl status suricata\n"
        "- 설정 검증: sudo suricata -T -c /etc/suricata/suricata.yaml\n"
        "- 알람 확인: tail -n 200 /var/log/suricata/eve.json | jq 'select(.event_type==\"alert\")'\n"
    )

    for kind, md in [("req", req_md), ("impl", impl_md), ("issue", issue_md), ("final", final_md)]:
        db.add(Report(project_id=project_id, kind=kind, content_md=md))
    db.commit()
