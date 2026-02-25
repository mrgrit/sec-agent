import React, { useEffect, useMemo, useState } from "react";

const API_BASE = (import.meta as any).env.VITE_API_BASE || "http://localhost:8000";

type Project = { id: number; name: string; status: string };
type Target = { id: number; name: string; host: string; port: number; username: string };
type Plan = { id: number; status: string; plan_json: any };
type Task = { id: number; status: string; current_step: number; error?: string | null };

async function api<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...opts,
    headers: { "Content-Type": "application/json", ...(opts?.headers || {}) },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export default function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [targets, setTargets] = useState<Target[]>([]);
  const [activeProjectId, setActiveProjectId] = useState<number | null>(null);

  const [reqText, setReqText] = useState("Suricata를 IDS 모드로 설치하고 eve.json 로그가 나오도록 설정해줘.");
  const [targetId, setTargetId] = useState<number | null>(null);

  const [plan, setPlan] = useState<Plan | null>(null);
  const [task, setTask] = useState<Task | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [artifacts, setArtifacts] = useState<any[]>([]);
  const [artifactContent, setArtifactContent] = useState<string>("");
  const [reports, setReports] = useState<any[]>([]);

  useEffect(() => {
    (async () => {
      const ps = await api<Project[]>("/api/projects");
      setProjects(ps);
      const ts = await api<Target[]>("/api/targets");
      setTargets(ts);
      if (ps[0]) setActiveProjectId(ps[0].id);
      if (ts[0]) setTargetId(ts[0].id);
    })();
  }, []);

  const activeProject = useMemo(
    () => projects.find((p) => p.id === activeProjectId) || null,
    [projects, activeProjectId]
  );

  async function createProject() {
    const name = prompt("프로젝트 이름?");
    if (!name) return;
    const p = await api<Project>("/api/projects", { method: "POST", body: JSON.stringify({ name }) });
    setProjects([p, ...projects]);
    setActiveProjectId(p.id);
    setPlan(null);
    setTask(null);
    setLogs([]);
    setArtifacts([]);
    setReports([]);
  }

  async function createTarget() {
    const name = prompt("대상 서버 이름?") || "target";
    const host = prompt("IP/Host?") || "";
    const username = prompt("username?") || "root";
    const password = prompt("password?") || "";
    const portStr = prompt("port? (default 22)") || "22";
    const t = await api<Target>("/api/targets", {
      method: "POST",
      body: JSON.stringify({ name, host, username, password, port: parseInt(portStr, 10) }),
    });
    setTargets([t, ...targets]);
    setTargetId(t.id);
  }

  async function testSSH() {
    if (!targetId) return alert("target 선택 필요");
    const r = await api<any>(`/api/targets/${targetId}/test-ssh`, { method: "POST", body: "{}" });
    alert(`exit=${r.exit_code}\n${(r.stdout || "").slice(0, 500)}\n${(r.stderr || "").slice(0, 200)}`);
  }

  async function saveRequirement() {
    if (!activeProjectId) return;
    await api(`/api/projects/${activeProjectId}/requirements`, {
      method: "POST",
      body: JSON.stringify({ target_id: targetId, text: reqText }),
    });
    alert("요구사항 저장 완료");
  }

  async function clarify() {
    if (!activeProjectId) return;
    const r = await api<any>(`/api/projects/${activeProjectId}/agent/clarify`, { method: "POST", body: "{}" });
    if (r.done) alert("추가 질문 없음(OK)");
    else alert(JSON.stringify(r.questions, null, 2));
  }

  async function makePlan() {
    if (!activeProjectId) return;
    const p = await api<Plan>(`/api/projects/${activeProjectId}/agent/plan`, { method: "POST", body: "{}" });
    setPlan(p);
    alert("플랜 생성 완료(승인 필요)");
  }

  async function approvePlan() {
    if (!activeProjectId || !plan) return;
    await api(`/api/projects/${activeProjectId}/plan/${plan.id}/approve`, { method: "POST", body: "{}" });
    setPlan({ ...plan, status: "APPROVED" });
    alert("승인 완료");
  }

  async function execute() {
    if (!activeProjectId || !plan) return;
    setLogs([]);
    const t = await api<Task>(`/api/projects/${activeProjectId}/agent/execute?plan_id=${plan.id}`, {
      method: "POST",
      body: "{}",
    });
    setTask(t);
  }

  useEffect(() => {
    if (!task) return;
    const es = new EventSource(`${API_BASE}/api/tasks/${task.id}/logs/stream`);
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data || "{}");
        if (data.message) setLogs((prev) => [...prev, `[${data.level}] ${data.message}`].slice(-300));
      } catch {}
    };
    return () => es.close();
  }, [task?.id]);

  async function refreshTask() {
    if (!task) return;
    const t = await api<Task>(`/api/tasks/${task.id}`);
    setTask(t);
    if (t.status === "DONE" || t.status === "FAILED" || t.status === "NEEDS_INPUT") {
      const arts = await api<any[]>(`/api/tasks/${t.id}/artifacts`);
      setArtifacts(arts);
      if (activeProjectId) {
        const rs = await api<any[]>(`/api/projects/${activeProjectId}/reports`);
        setReports(rs);
      }
    }
  }

  async function openArtifact(id: number) {
    const r = await api<any>(`/api/artifacts/${id}/content`);
    setArtifactContent(r.content || "");
  }

  return (
    <div style={{ fontFamily: "ui-sans-serif", padding: 16, maxWidth: 1200, margin: "0 auto" }}>
      <h2>Sec-Agent MVP v0.1</h2>

      <div style={{ display: "flex", gap: 12 }}>
        <div style={{ flex: 1 }}>
          <h3>프로젝트</h3>
          <button onClick={createProject}>+ 프로젝트</button>
          <ul>
            {projects.map((p) => (
              <li key={p.id}>
                <button onClick={() => setActiveProjectId(p.id)}>
                  {p.id}. {p.name} ({p.status})
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div style={{ flex: 1 }}>
          <h3>대상 서버(Target)</h3>
          <button onClick={createTarget}>+ Target</button>
          <button onClick={testSSH} style={{ marginLeft: 8 }}>
            SSH 테스트
          </button>
          <div style={{ marginTop: 8 }}>
            <select value={targetId ?? ""} onChange={(e) => setTargetId(parseInt(e.target.value, 10))}>
              <option value="">선택</option>
              {targets.map((t) => (
                <option value={t.id} key={t.id}>
                  {t.name} ({t.host}:{t.port})
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      <hr />

      <h3>요구사항</h3>
      <textarea value={reqText} onChange={(e) => setReqText(e.target.value)} rows={4} style={{ width: "100%" }} />
      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
        <button onClick={saveRequirement}>요구사항 저장</button>
        <button onClick={clarify}>Clarify</button>
        <button onClick={makePlan}>Plan 생성</button>
        <button onClick={approvePlan} disabled={!plan || plan.status !== "DRAFT"}>
          Plan 승인
        </button>
        <button onClick={execute} disabled={!plan || plan.status !== "APPROVED"}>
          실행
        </button>
        <button onClick={refreshTask} disabled={!task}>
          상태/아티팩트 갱신
        </button>
      </div>

      {plan && (
        <div style={{ marginTop: 12, padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
          <h3>Plan #{plan.id} ({plan.status})</h3>
          <pre style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(plan.plan_json, null, 2)}</pre>
        </div>
      )}

      {task && (
        <div style={{ marginTop: 12, padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
          <h3>
            Task #{task.id} — {task.status} {task.error ? `(error: ${task.error})` : ""}
          </h3>
          <div style={{ display: "flex", gap: 12 }}>
            <div style={{ flex: 1 }}>
              <h4>실행 로그(SSE)</h4>
              <div style={{ height: 240, overflow: "auto", background: "#111", color: "#0f0", padding: 8 }}>
                {logs.map((l, i) => (
                  <div key={i}>{l}</div>
                ))}
              </div>
            </div>
            <div style={{ flex: 1 }}>
              <h4>아티팩트</h4>
              <ul>
                {artifacts.map((a) => (
                  <li key={a.id}>
                    <button onClick={() => openArtifact(a.id)}>
                      [{a.kind}] {a.name}
                    </button>
                  </li>
                ))}
              </ul>
              <h4>아티팩트 내용</h4>
              <div style={{ height: 240, overflow: "auto", border: "1px solid #ddd", padding: 8 }}>
                <pre style={{ whiteSpace: "pre-wrap" }}>{artifactContent}</pre>
              </div>
            </div>
          </div>
        </div>
      )}

      {reports.length > 0 && (
        <div style={{ marginTop: 12, padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
          <h3>보고서</h3>
          {reports.map((r) => (
            <details key={r.id} style={{ marginBottom: 8 }}>
              <summary>
                #{r.id} - {r.kind} ({r.created_at})
              </summary>
              <pre style={{ whiteSpace: "pre-wrap" }}>{r.content_md}</pre>
            </details>
          ))}
        </div>
      )}
    </div>
  );
}
