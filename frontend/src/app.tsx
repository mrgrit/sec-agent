import React, { useEffect, useMemo, useState } from "react";

const API_BASE = (import.meta as any).env.VITE_API_BASE || "http://localhost:8000";

type Project = { id: number; name: string; status: string };
type Target = { id: number; name: string; host: string; port: number; username: string };
type Plan = { id: number; status: string; plan_json: any };
type Task = { id: number; status: string; current_step: number; error?: string | null };

type LLMConn = {
  id: number;
  name: string;
  type: "ollama" | "openai";
  base_url?: string | null;
  selected_model?: string | null;
  timeout_s: number;
};

type ClarifyQuestion = {
  field: string;
  question: string;
  type?: "text" | "select";
  options?: string[];
};

type ClarifyResp = {
  done: boolean;
  questions?: ClarifyQuestion[];
  assumptions?: any;
};

type ChatMsg = { role: "user" | "assistant"; content: string; ts: number };

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

  // ---- v0.2 LLM states ----
  const [llmConns, setLlmConns] = useState<LLMConn[]>([]);
  const [activeConnId, setActiveConnId] = useState<number | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>("");

  // ---- UI inputs for LLM connection (v0.2+) ----
  const [ollamaBaseUrl, setOllamaBaseUrl] = useState("http://<OLLAMA_HOST>:11434");
  const [openaiApiKey, setOpenaiApiKey] = useState("");

  // ---- SSH test UI status ----
  const [sshTest, setSshTest] = useState<{
    status: "IDLE" | "RUNNING" | "OK" | "FAIL";
    message?: string;
    stdout?: string;
    stderr?: string;
  } | null>({ status: "IDLE" });

  // ---- Clarify ----
  const [clarify, setClarify] = useState<ClarifyResp | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});

  // ---- Work chat ----
  const [chat, setChat] = useState<ChatMsg[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatBusy, setChatBusy] = useState(false);

  useEffect(() => {
    (async () => {
      const ps = await api<Project[]>("/api/projects");
      setProjects(ps);
      const ts = await api<Target[]>("/api/targets");
      setTargets(ts);

      // LLM connections
      try {
        const cs = await api<LLMConn[]>("/api/llm/connections");
        setLlmConns(cs);
        if (cs[0]) setActiveConnId(cs[0].id);
      } catch {
        // ignore
      }

      if (ps[0]) setActiveProjectId(ps[0].id);
      if (ts[0]) setTargetId(ts[0].id);
    })();
  }, []);

  const activeProject = useMemo(
    () => projects.find((p) => p.id === activeProjectId) || null,
    [projects, activeProjectId]
  );

  async function refreshLLMConns() {
    const cs = await api<LLMConn[]>("/api/llm/connections");
    setLlmConns(cs);
    if (!activeConnId && cs[0]) setActiveConnId(cs[0].id);
  }

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
    setClarify(null);
    setAnswers({});
    setChat([]);
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
    setSshTest({ status: "RUNNING", message: "SSH 테스트 중..." });

    try {
      const r = await api<any>(`/api/targets/${targetId}/test-ssh`, { method: "POST", body: "{}" });
      const ok = r.exit_code === 0 && (r.stdout || "").includes("OK");

      setSshTest({
        status: ok ? "OK" : "FAIL",
        message: ok ? "SSH 연결 성공" : "SSH 연결 실패",
        stdout: (r.stdout || "").slice(0, 4000),
        stderr: (r.stderr || "").slice(0, 4000),
      });
    } catch (e: any) {
      setSshTest({
        status: "FAIL",
        message: `SSH 테스트 실패: ${String(e?.message || e)}`,
        stdout: "",
        stderr: "",
      });
    }
  }

  async function saveRequirement() {
    if (!activeProjectId) return;
    await api(`/api/projects/${activeProjectId}/requirements`, {
      method: "POST",
      body: JSON.stringify({ target_id: targetId, text: reqText }),
    });
    alert("요구사항 저장 완료");
  }

  async function createLLMConnFromUI(type: "ollama" | "openai") {
    let name = "openai";
    if (type === "ollama") {
      try {
        name = `ollama-${new URL(ollamaBaseUrl).hostname}`;
      } catch {
        name = `ollama-${Date.now()}`;
      }
    }

    if (type === "ollama") {
      if (!ollamaBaseUrl.trim()) return alert("Ollama Base URL을 입력해줘");
      await api<LLMConn>("/api/llm/connections", {
        method: "POST",
        body: JSON.stringify({ name, type: "ollama", base_url: ollamaBaseUrl.trim() }),
      });
    } else {
      if (!openaiApiKey.trim()) return alert("OpenAI API Key를 입력해줘");
      await api<LLMConn>("/api/llm/connections", {
        method: "POST",
        body: JSON.stringify({ name, type: "openai", api_key: openaiApiKey.trim() }),
      });
    }

    await refreshLLMConns();
    alert("LLM connection 생성 완료");
  }

  async function loadModels() {
    if (!activeConnId) return alert("LLM connection 선택 필요");
    const r = await api<{ models: string[] }>(`/api/llm/${activeConnId}/models`);
    setModels(r.models || []);
    if (r.models?.[0]) setSelectedModel(r.models[0]);
    alert(`models loaded: ${(r.models || []).length}`);
  }

  async function selectModel() {
    if (!activeConnId) return alert("LLM connection 선택 필요");
    if (!selectedModel) return alert("model 선택 필요");
    const timeoutStr = prompt("timeout_s? (권장 600~900)", "900") || "900";
    const timeout_s = parseInt(timeoutStr, 10);

    await api(`/api/llm/${activeConnId}/select`, {
      method: "POST",
      body: JSON.stringify({ model: selectedModel, timeout_s }),
    });

    await refreshLLMConns();
    alert("모델 선택 완료");
  }

  async function runClarify() {
    if (!activeProjectId) return;
    if (!activeConnId) return alert("LLM connection 선택 필요");
    const r = await api<ClarifyResp>(`/api/projects/${activeProjectId}/agent/clarify?conn_id=${activeConnId}`, {
      method: "POST",
      body: "{}",
    });
    setClarify(r);
    setAnswers({});
    if (r.done) alert("추가 질문 없음(done=true)");
  }

  async function submitClarifyAnswers() {
    if (!activeProjectId) return;
    if (!clarify || !clarify.questions || clarify.questions.length === 0) return alert("질문이 없음");

    const updates: Record<string, string> = {};
    for (const q of clarify.questions) {
      const v = (answers[q.field] || "").trim();
      if (v) updates[q.field] = v;
    }
    if (Object.keys(updates).length === 0) return alert("답변을 1개 이상 입력해야 함");

    await api<any>(`/api/projects/${activeProjectId}/agent/clarify/answer`, {
      method: "POST",
      body: JSON.stringify({ updates }),
    });

    alert("structured 업데이트 완료");
    await runClarify();
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
        if (data.message) setLogs((prev) => [...prev, `[${data.level}] ${data.message}`].slice(-500));
      } catch {
        // ignore
      }
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

  async function sendChat() {
    if (!activeProjectId) return alert("프로젝트 선택 필요");
    if (!activeConnId) return alert("LLM connection 선택 필요");

    const msg = chatInput.trim();
    if (!msg) return;

    const userMsg: ChatMsg = { role: "user", content: msg, ts: Date.now() };
    setChat((prev) => [...prev, userMsg]);
    setChatInput("");
    setChatBusy(true);

    try {
      const r = await api<{ reply: string }>(`/api/projects/${activeProjectId}/chat?conn_id=${activeConnId}`, {
        method: "POST",
        body: JSON.stringify({ message: msg }),
      });

      const botMsg: ChatMsg = { role: "assistant", content: r.reply || "(empty)", ts: Date.now() };
      setChat((prev) => [...prev, botMsg]);
    } catch (e: any) {
      const botMsg: ChatMsg = {
        role: "assistant",
        content: `에러: ${String(e?.message || e)}`,
        ts: Date.now(),
      };
      setChat((prev) => [...prev, botMsg]);
    } finally {
      setChatBusy(false);
    }
  }

  return (
    <div style={{ fontFamily: "ui-sans-serif", padding: 16, maxWidth: 1200, margin: "0 auto" }}>
      <h2>Sec-Agent MVP v0.2 (LLM Clarify)</h2>

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

          {sshTest && sshTest.status !== "IDLE" && (
            <div style={{ marginTop: 10, padding: 10, border: "1px solid #ddd", borderRadius: 8 }}>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <b>SSH 테스트 결과:</b>
                {sshTest.status === "RUNNING" && <span>⏳ {sshTest.message}</span>}
                {sshTest.status === "OK" && <span style={{ color: "green" }}>✅ {sshTest.message}</span>}
                {sshTest.status === "FAIL" && <span style={{ color: "red" }}>❌ {sshTest.message}</span>}
              </div>

              {(sshTest.stdout || sshTest.stderr) && (
                <details style={{ marginTop: 8 }}>
                  <summary>상세 출력 보기</summary>

                  {sshTest.stdout && (
                    <>
                      <div style={{ marginTop: 8, fontWeight: 600 }}>stdout</div>
                      <pre style={{ whiteSpace: "pre-wrap", background: "#f7f7f7", padding: 8 }}>
                        {sshTest.stdout}
                      </pre>
                    </>
                  )}

                  {sshTest.stderr && (
                    <>
                      <div style={{ marginTop: 8, fontWeight: 600 }}>stderr</div>
                      <pre style={{ whiteSpace: "pre-wrap", background: "#f7f7f7", padding: 8 }}>
                        {sshTest.stderr}
                      </pre>
                    </>
                  )}
                </details>
              )}
            </div>
          )}
        </div>
      </div>

      <hr />

      <div style={{ padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
        <h3>LLM 설정 (Ollama/OpenAI)</h3>

        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <span>Ollama Base URL:</span>
          <input
            type="text"
            value={ollamaBaseUrl}
            onChange={(e) => setOllamaBaseUrl(e.target.value)}
            placeholder="http://<OLLAMA_HOST>:11434"
            style={{ width: 320, padding: 6 }}
          />
          <button onClick={() => createLLMConnFromUI("ollama")}>+ Ollama Connection</button>

          <span style={{ marginLeft: 12 }}>OpenAI Key:</span>
          <input
            type="password"
            value={openaiApiKey}
            onChange={(e) => setOpenaiApiKey(e.target.value)}
            placeholder="sk-..."
            style={{ width: 220, padding: 6 }}
          />
          <button onClick={() => createLLMConnFromUI("openai")}>+ OpenAI Connection</button>

          <button onClick={refreshLLMConns} style={{ marginLeft: 8 }}>
            리로드
          </button>

          <span style={{ marginLeft: 8 }}>Connection:</span>
          <select
            value={activeConnId ?? ""}
            onChange={(e) => setActiveConnId(parseInt(e.target.value, 10))}
            style={{ minWidth: 420 }}
          >
            <option value="">선택</option>
            {llmConns.map((c) => (
              <option value={c.id} key={c.id}>
                #{c.id} {c.name} [{c.type}] {c.base_url ? `(${c.base_url})` : ""} model={c.selected_model || "-"}
              </option>
            ))}
          </select>

          <button onClick={loadModels} disabled={!activeConnId}>
            모델 목록 로드
          </button>

          <span>Model:</span>
          <select value={selectedModel} onChange={(e) => setSelectedModel(e.target.value)} style={{ minWidth: 260 }}>
            <option value="">선택</option>
            {models.map((m) => (
              <option value={m} key={m}>
                {m}
              </option>
            ))}
          </select>

          <button onClick={selectModel} disabled={!activeConnId || !selectedModel}>
            이 모델 사용(select)
          </button>
        </div>
      </div>

      <hr />

      <h3>요구사항</h3>
      <div style={{ color: "#555", marginBottom: 6 }}>
        현재 프로젝트: <b>{activeProject ? `${activeProject.id}. ${activeProject.name}` : "없음"}</b>
      </div>

      <textarea value={reqText} onChange={(e) => setReqText(e.target.value)} rows={4} style={{ width: "100%" }} />
      <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
        <button onClick={saveRequirement}>요구사항 저장</button>

        <button onClick={runClarify} disabled={!activeConnId}>
          Clarify (LLM)
        </button>

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

      <div style={{ marginTop: 12, padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
        <h3>작업 채팅</h3>

        <div
          style={{
            height: 260,
            overflow: "auto",
            border: "1px solid #eee",
            borderRadius: 8,
            padding: 10,
            background: "#fafafa",
          }}
        >
          {chat.length === 0 && <div style={{ color: "#777" }}>작업 중 궁금한 점을 물어보면 여기에 대화가 쌓입니다.</div>}
          {chat.map((m, idx) => (
            <div key={idx} style={{ marginBottom: 10 }}>
              <div style={{ fontWeight: 700, color: m.role === "user" ? "#111" : "#0b5" }}>
                {m.role === "user" ? "You" : "Agent"}
              </div>
              <div style={{ whiteSpace: "pre-wrap" }}>{m.content}</div>
            </div>
          ))}
        </div>

        <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
          <input
            value={chatInput}
            onChange={(e) => setChatInput(e.target.value)}
            placeholder="예: 방금 실패한 이유가 뭐야? 다음에 뭘 해야 해?"
            style={{ flex: 1, padding: 10 }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                if (!chatBusy) sendChat();
              }
            }}
          />
          <button onClick={sendChat} disabled={chatBusy || !activeProjectId || !activeConnId}>
            {chatBusy ? "전송중..." : "Send"}
          </button>
          <button onClick={() => setChat([])} disabled={chatBusy}>
            Clear
          </button>
        </div>

        <div style={{ marginTop: 6, color: "#666", fontSize: 13 }}>
          ※ 현재 프로젝트/선택한 LLM Connection 기준으로 답변합니다.
        </div>
      </div>

      {clarify && !clarify.done && clarify.questions && clarify.questions.length > 0 && (
        <div style={{ marginTop: 12, padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
          <h3>Clarify 질문</h3>
          <p style={{ color: "#555" }}>아래 질문에 답하면 structured에 저장되고, 부족한 항목이 남아 있으면 다음 질문이 이어집니다.</p>

          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {clarify.questions.map((q) => (
              <div key={q.field} style={{ padding: 10, border: "1px solid #eee", borderRadius: 8 }}>
                <div style={{ marginBottom: 6 }}>
                  <b>{q.field}</b> — {q.question}
                </div>

                {q.type === "select" && q.options && q.options.length > 0 ? (
                  <select
                    value={answers[q.field] || ""}
                    onChange={(e) => setAnswers((prev) => ({ ...prev, [q.field]: e.target.value }))}
                    style={{ minWidth: 320 }}
                  >
                    <option value="">선택</option>
                    {q.options.map((opt) => (
                      <option key={opt} value={opt}>
                        {opt}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="text"
                    placeholder="답변 입력"
                    value={answers[q.field] || ""}
                    onChange={(e) => setAnswers((prev) => ({ ...prev, [q.field]: e.target.value }))}
                    style={{ width: "100%", padding: 8 }}
                  />
                )}
              </div>
            ))}
          </div>

          <div style={{ marginTop: 10 }}>
            <button onClick={submitClarifyAnswers}>답변 제출 → 다음 질문</button>
          </div>
        </div>
      )}

      {plan && (
        <div style={{ marginTop: 12, padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
          <h3>
            Plan #{plan.id} ({plan.status})
          </h3>
          <pre style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(plan.plan_json, null, 2)}</pre>
        </div>
      )}

      {task && (
        <div style={{ marginTop: 12, padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
          <h3>
            Task #{task.id} — {task.status} {task.error ? `(error: ${task.error})` : ""}
          </h3>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <div style={{ flex: 1, minWidth: 380 }}>
              <h4>실행 로그(SSE)</h4>
              <div style={{ height: 260, overflow: "auto", background: "#111", color: "#0f0", padding: 8 }}>
                {logs.map((l, i) => (
                  <div key={i}>{l}</div>
                ))}
              </div>
            </div>

            <div style={{ flex: 1, minWidth: 380 }}>
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
              <div style={{ height: 260, overflow: "auto", border: "1px solid #ddd", padding: 8 }}>
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
