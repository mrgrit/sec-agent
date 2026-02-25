```md
# Sec-Agent (v0.1 MVP)
오픈소스 보안 시스템(Suricata, OPNsense, ModSecurity, Sysmon, auditd 등)을 **지정한 서버에 원격 설치/설정/검증**하고, 설치 이후에도 **유지보수(룰 생성/설정 변경) 및 운영(로그 분석/이슈 리포트)**까지 수행하는 **에이전트 기반 보안 운영 자동화 솔루션**.

현재 버전(v0.1)은 “엔드투엔드로 실제로 돌아가는 MVP”를 목표로 하며, **Suricata IDS 설치/기본 설정/스모크 테스트/증빙 저장/보고서 생성**까지의 전체 파이프라인을 구현한다.

---

## 1. 문제 정의 & 목표

### 1) 기존 문제
- 보안 시스템 구축은 문서/버전/환경(OS, NIC, 방화벽 정책)에 따라 설치·설정이 달라 **재현 가능한 운영 런북이 없으면 반복 구축이 어렵다.**
- 설치 이후에도 룰 업데이트, 탐지 튜닝, 로그 분석, 장애 대응 등 운영 작업이 지속적으로 필요하지만 **담당자 역량 의존도가 크다.**
- LLM을 그대로 적용하면 최신성/근거/안전성 이슈가 있어 **RAG + 검증(테스트/증빙) + 승인(휴먼 인 더 루프)** 구조가 필요하다.

### 2) 목표(제품 관점)
- 사용자는 “요구사항”만 작성한다.
- 에이전트는 **질문(Clarify) → 계획(Plan/TODO) → 사용자 승인 → 실행(Execute) → 검증(Verify) → 리포트(Report)**를 반복 수행한다.
- 실행 결과는 **마일스톤 단위 증빙(로그/명령 출력)**로 저장되고, UI에서 진행 상황과 결과를 확인할 수 있다.
- 응답이 느린 오픈모델을 고려해 **Timeout/재시도/단계 실행**을 기본으로 한다.

---

## 2. 현재 버전(v0.1) 범위

### 포함(구현됨)
- Docker Compose 기반 로컬 실행
- Web UI(React/Vite)로 프로젝트/타겟/요구사항/플랜/실행/로그/아티팩트/보고서 확인
- 대상 서버 등록(SSH ID/PW) 및 접속 테스트
- 요구사항 저장
- Clarify(현재는 최소 규칙 기반: target 선택 여부 확인)
- Plan 생성(서버 facts 기반 인터페이스 추정 포함)
- Plan 승인(휴먼 검수)
- Execute(Worker가 SSH로 Suricata 설치/설정/테스트 수행)
- 마일스톤별 증빙(텍스트 캡처) 저장 및 UI 열람
- 보고서 4종 생성(초안)
  - 요구사항 분석 보고서
  - 기능 구현 보고서
  - 이슈 보고서
  - 완료 보고서

### 제외(향후 확장)
- LLM Gateway(Ollama/OpenAI) 실제 호출 기반 Clarify/Plan 생성(현재는 MVP 고정 플로우)
- 임베딩 기반 벡터DB RAG(현재는 업로드 + chunk + 간단 검색 형태)
- IPS(NFQUEUE) 전환 및 위험 작업 승인 플로우
- 멀티 시스템(Suricata 외 OPNsense/ModSecurity/Sysmon/auditd) 본격 지원
- RBAC/인증/감사로그/비밀관리(KMS) 운영 수준 보강

---

## 3. 아키텍처 개요

### 구성 요소
- **Frontend**: React(Vite)  
  - 프로젝트/타겟/요구사항 입력
  - Plan/TODO 표시 및 승인
  - Task 실행 로그(SSE) 스트리밍
  - 아티팩트(증빙) 조회
  - 보고서 조회

- **Backend**: FastAPI  
  - 프로젝트/타겟/요구사항/플랜/태스크/아티팩트/보고서 API 제공
  - 자격증명 암호화(AES-GCM)
  - RAG 문서 업로드 및 chunk 저장(현재는 간단 검색)

- **Worker**: RQ( Redis Queue ) 기반 작업 실행  
  - 에이전트 상태 머신 실행
  - SSH 원격 명령 실행(Paramiko)
  - 마일스톤 단위 증빙 저장
  - 실패 시 상태 전환(NEEDS_INPUT 등)

- **DB**: Postgres  
  - 프로젝트/타겟/요구사항/플랜/태스크/로그/아티팩트/보고서 데이터 관리

- **Redis**: Queue 및 작업 제어

---

## 4. 디렉토리 구조(현재 MVP 기준)

```

sec-agent/
infra/
docker-compose.yml

backend/
Dockerfile
pyproject.toml
app/
main.py              # FastAPI entry
api.py               # API routes (MVP 단일 파일)
models.py            # SQLAlchemy models (MVP 단일 파일)
schemas.py           # Pydantic schemas (MVP 단일 파일)

```
  core/
    config.py          # 환경설정
    db.py              # DB 초기화/세션
    crypto.py          # AES-GCM 암호화(자격증명)

  services/
    rag_simple.py      # 문서 chunk + 간단 검색(BM25 유사)
    tools/
      ssh_tool.py      # SSH 실행(Paramiko)
    agent/
      state_machine.py # Plan/Execute/Verify/Report 핵심 로직

  worker/
    worker.py          # RQ worker 엔트리
    jobs.py            # run_task(job) 정의
```

frontend/
Dockerfile
package.json
vite.config.ts
index.html
src/
main.tsx
app.tsx              # 단일 페이지 MVP UI

README.md

````

> v1.0(모듈 분리형) 구조는 향후 리팩토링 단계에서 적용 예정.

---

## 5. 실행 방법

### 1) Docker Compose(v2) 설치
Ubuntu 22.04 기준 권장:
- `docker compose`가 동작해야 함(Compose v2 플러그인)
- 미설치 시 Docker 공식 repo 기반으로 `docker-compose-plugin` 설치

### 2) 실행
프로젝트 루트에서:
```bash
sudo docker compose -f infra/docker-compose.yml up -d --build
````

### 3) 접속

* Frontend: `http://localhost:5173`
* Backend(Swagger): `http://localhost:8000/docs`
* Health: `http://localhost:8000/api/health`

> 서버에서 띄워 원격 접속한다면 방화벽/보안그룹에서 5173/8000을 허용하고, 프론트의 API_BASE 설정도 서버 IP로 맞춰야 한다.

---

## 6. 사용 흐름(End-to-End)

### Step 1) Target(대상 서버) 등록

* UI에서 Target을 추가

  * host/IP, port(기본 22), username, password 입력
* SSH 테스트로 접속 확인

### Step 2) Project 생성

* 프로젝트 생성 후 요구사항 작성

### Step 3) Requirements 저장

예시 요구사항:

* “Suricata를 IDS 모드로 설치하고 eve.json 로그가 나오도록 설정해줘.”

### Step 4) Clarify (현재 MVP: 최소 질문)

* Target 선택이 되어 있는지 확인
* (향후) 인터페이스, HOME_NET, 룰 소스, 운영 정책 등 추가 질문을 LLM이 수행

### Step 5) Plan 생성

* 대상 서버 facts(인터페이스 등)를 기반으로 Plan/TODO 생성
* TODO는 설치/설정/검증 마일스톤으로 구성됨

### Step 6) 사용자 승인

* UI에서 Plan/TODO를 확인한 후 승인(Approve)

### Step 7) Execute(Worker)

Worker가 마일스톤 단위로 수행:

1. Precheck(OS/NIC/ADDR 등)
2. 패키지 설치(suricata, jq)
3. 설정 파일 작성 + local.rules 작성
4. `suricata -T`로 설정 검증
5. 서비스 enable/start + active 확인
6. 스모크 테스트(curl + eve.json에서 LOCAL TEST 탐지 확인)

### Step 8) 증빙 저장 및 UI 확인

* 각 마일스톤은 “증빙(evidence)” 텍스트로 저장됨
* UI에서 로그(SSE) 및 증빙 열람 가능

### Step 9) 보고서 생성

* 요구사항 분석/구현/이슈/완료 보고서 4종 자동 생성(초안)
* UI에서 확인 가능

---

## 7. 검증 전략(Why “증빙”이 중요한가)

LLM/에이전트는 “설치했다”고 말할 수 있지만 운영에서 중요한 건 **실제 상태를 증명하는 근거**다.

v0.1은 스크린샷 대신 다음을 “증빙”으로 저장한다:

* `systemctl status` / `systemctl is-active`
* `suricata -T` 결과
* `ip link`, `ip addr` 결과
* `tail eve.json` 및 alert signature 확인

향후에는 환경에 따라:

* 웹 UI/대시보드 캡처(실제 스크린샷)
* 그래프/리포트 렌더링 이미지 생성
* PCAP 기반 테스트(재현 가능한 탐지 테스트)
  까지 확장 가능하다.

---

## 8. 보안/안전장치(현재 수준 & 향후 강화)

### 현재(v0.1)

* 대상 서버 비밀번호는 DB에 **AES-GCM 암호화**로 저장
* Plan 승인 후에만 실행(휴먼 인 더 루프)

### 향후 강화(v1.0+)

* 비밀정보는 환경키가 아닌 KMS/Secret Manager로 이전
* 사용자/팀 기반 RBAC
* 실행 커맨드 마스킹/감사로그
* 위험 작업(방화벽 변경, IPS drop, 인라인 모드)은 2단계 승인
* 자동 롤백(원격 세션 끊김 대비)

---

## 9. 알려진 이슈 / 트러블슈팅

### 1) `docker compose`가 인식되지 않음

* Compose v2 플러그인 설치 필요(`docker-compose-plugin`)

### 2) `permission denied while trying to connect to /var/run/docker.sock`

* `sudo`로 실행하거나, 사용자를 docker 그룹에 추가:

  * `sudo usermod -aG docker $USER && newgrp docker`

### 3) 프론트가 실행 실패: `@vitejs/plugin-react` not found

* `frontend/package.json`에 `@vitejs/plugin-react` devDependency 추가 필요

### 4) 백엔드 connection refused

* 보통 import/syntax 에러로 uvicorn이 뜨기 전에 죽은 상태
* `docker compose logs backend`로 원인 확인

---

## 10. 향후 확장 계획(로드맵)

### v1.0 (구조 리팩토링 + LLM Gateway 연결)

* **모듈 분리형 폴더 구조** 적용

  * `api/routes`, `models/`, `schemas/`, `services/agent/*`로 분리
* LLM Gateway 구현

  * Ollama 모델 목록 로드(`/api/tags`)
  * 모델 호출(`/api/chat`) + timeout/retry
  * OpenAI fallback 연결
* Clarify/Plan을 LLM이 수행

  * “필수 슬롯” 기반 질문 자동 생성
  * RAG 검색 결과 인용 + TODO/테스트케이스/롤백 포함 계획 생성

### v1.1 (RAG 고도화 + 문서 자동 생성)

* 문서 업로드 → chunking 개선(섹션/헤더 기반)
* 임베딩 + 벡터DB(FAISS/pgvector) 적용
* “OpenAI 상용모델로 런북 자동 생성 → 업로드/인덱싱” 파이프라인 추가

### v1.2 (운영/유지보수 기능 강화)

* 룰 관리 UI

  * local.rules 생성/수정/버전관리
  * 룰 업데이트 타이머(systemd timer/cron)
* 로그 분석 기능

  * eve.json 통계(top signature, src/dst, severity)
  * triage 템플릿 기반 “사건 요약/대응 권고” 생성

### v1.3 (다중 보안 시스템 확장)

* ModSecurity + OWASP CRS 배포/튜닝
* auditd 규칙 배포/검증
* Sysmon(Windows) 수집/분석(WinRM/agent 기반)
* OPNsense API 연동(정책/룰/로그)

### v2.0 (운영 수준)

* RBAC/조직 단위 운영
* 멀티 타겟 동시 실행/스케줄링
* 안전한 변경(드라이런/diff/롤백/승인)
* 감사/컴플라이언스 리포트 자동화(IEC 62443/조직 기준 등)

---

## 11. 개발 원칙(핵심 설계 철학)

* **근거 기반 자동화**: 실행 결과는 증빙으로 저장되어야 한다.
* **안전한 변경**: Plan 승인 없이 실행하지 않는다.
* **단계적 자동화**: IDS로 안정화 → IPS/drop은 승인/검증 후 확대.
* **확장 가능 구조**: 보안 시스템별 “플러그인”처럼 추가할 수 있어야 한다.

---

## 12. 라이선스

* (추후 결정) MVP 단계에서는 내부 프로젝트 용도로 사용.

```

---

```

