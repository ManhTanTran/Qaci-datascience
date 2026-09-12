import { useEffect, useState } from "react";
import { Activity, BrainCircuit, Database, GitBranch, RefreshCw, Sparkles } from "lucide-react";
import HarnessOutputView from "./HarnessOutputView";

const API = import.meta.env.VITE_API_URL ?? "";
type Target = "promotion_readiness" | "kpi_delivery" | "training_priority";
type Profile = { role: string; years_experience: number; projects_delivered: number; kpi_attainment: number; skill_match: number; certifications: number };
type Scenario = { id: string; label: string; summary: string; profile: Profile };
type Finding = { rule_id: string; message: string; action: string };
type Knowledge = { version: string; title: string; rules: Finding[] };
type Result = { target: Target; model_name: string; model_score: number; model_interpretation: string; rule_findings: Finding[]; conclusion: { summary: string; evidence: string[]; uncertainties: string[]; recommended_actions: string[] }; trace: string[]; knowledge_base_version: string; llm_provider: string; llm_used: boolean };

function AgentDemoApp() {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = useState("");
  const [target, setTarget] = useState<Target>("promotion_readiness");
  const [knowledge, setKnowledge] = useState<Knowledge | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function loadScenarios() {
    try {
      const response = await fetch(`${API}/api/agent-demo/scenarios`);
      if (!response.ok) throw new Error("Không đọc được dữ liệu demo");
      const body = (await response.json()) as Scenario[];
      setScenarios(body);
      setScenarioId((current) => current || body[0]?.id || "");
    } catch (e) { setError(e instanceof Error ? e.message : "Không đọc được dữ liệu demo"); }
  }
  async function loadKnowledge() {
    try {
      const response = await fetch(`${API}/api/agent-demo/knowledge`);
      if (!response.ok) throw new Error("Không đọc được knowledge base");
      setKnowledge(await response.json());
    } catch (e) { setError(e instanceof Error ? e.message : "Không đọc được knowledge base"); }
  }
  useEffect(() => { void loadScenarios(); void loadKnowledge(); }, []);
  const selected = scenarios.find((scenario) => scenario.id === scenarioId);
  async function run() {
    setBusy(true); setError("");
    try {
      const response = await fetch(`${API}/api/agent-demo/run`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scenario_id: scenarioId, target, use_llm: true }) });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? "Agent demo thất bại");
      setResult(body as Result);
    } catch (e) { setError(e instanceof Error ? e.message : "Không thể kết nối backend"); }
    finally { setBusy(false); }
  }
  return <div className="agent-shell"><header className="agent-topbar"><a href="/" className="agent-brand"><span className="agent-mark">EPI</span><span><strong>Reasoning Lab</strong><small>Agent harness demo</small></span></a><a className="agent-back" href="/">← Về flow customer</a></header><main className="agent-main"><section className="agent-hero"><div><p className="agent-kicker"><Sparkles size={15} /> Model · Knowledge · Harness</p><h1>Demo Agent readiness với dữ liệu synthetic.</h1><p>Trang này giữ riêng demo EPI cũ: chọn scenario nhân viên, áp knowledge base và xem model/rule/LLM trace.</p></div><div className="agent-flow"><div><BrainCircuit size={20} /><span>Model</span></div><i>→</i><div><Database size={20} /><span>Knowledge</span></div><i>→</i><div><GitBranch size={20} /><span>Harness</span></div></div></section>{error && <div className="agent-alert">{error}</div>}<div className="agent-grid"><section className="agent-card agent-form"><div className="agent-card-head"><div><span className="agent-index">01</span><div><p>Synthetic input</p><h2>Dữ liệu demo có sẵn</h2></div></div><span className="agent-badge">No employee form</span></div><p className="agent-intro">Chọn scenario được tạo sẵn; không cần nhập hồ sơ nhân viên.</p><div className="scenario-list" role="listbox" aria-label="Synthetic demo scenarios">{scenarios.map((scenario) => <button key={scenario.id} type="button" className={`scenario-option ${scenario.id === scenarioId ? "active" : ""}`} onClick={() => setScenarioId(scenario.id)} role="option" aria-selected={scenario.id === scenarioId}><span><b>{scenario.label}</b><small>{scenario.summary}</small></span><strong>{scenario.id === scenarioId ? "Đã chọn" : "Chọn"}</strong></button>)}</div>{selected && <div className="generated-profile"><div className="generated-profile-head"><span>Generated profile</span><b>{selected.profile.role}</b></div><div className="generated-profile-grid"><span>Kinh nghiệm<strong>{selected.profile.years_experience} năm</strong></span><span>Dự án<strong>{selected.profile.projects_delivered}</strong></span><span>KPI<strong>{(selected.profile.kpi_attainment * 100).toFixed(0)}%</strong></span><span>Skill match<strong>{(selected.profile.skill_match * 100).toFixed(0)}%</strong></span><span>Chứng chỉ<strong>{selected.profile.certifications}</strong></span></div></div>}<label>Target cần phân tích<select value={target} onChange={(e) => setTarget(e.target.value as Target)}><option value="promotion_readiness">Promotion readiness</option><option value="kpi_delivery">KPI delivery</option><option value="training_priority">Training priority</option></select></label><button className="agent-run" type="button" onClick={() => void run()} disabled={busy || !scenarioId}>{busy ? "Đang chạy harness..." : "Run agent demo"}<Activity size={17} /></button><small className="agent-note">Đây là EPI synthetic demo riêng, không phải hồ sơ khách hàng tín dụng.</small></section><section className="agent-card agent-kb"><div className="agent-card-head"><div><span className="agent-index">02</span><div><p>Knowledge base</p><h2>Rules đang active</h2></div></div><button className="icon-button" onClick={() => void loadKnowledge()} title="Reload knowledge base"><RefreshCw size={16} /></button></div>{knowledge ? <><div className="kb-version"><span>Version</span><strong>{knowledge.version}</strong><small>{knowledge.rules.length} rules · reload theo file mỗi request</small></div><div className="rule-list">{knowledge.rules.map((rule) => <article key={rule.rule_id}><b>{rule.rule_id}</b><span>{rule.message}</span><small>{rule.action}</small></article>)}</div></> : <p className="empty-state">Đang đọc knowledge base...</p>}</section></div>{result && <HarnessOutputView data={{ provider: result.llm_provider, llmUsed: result.llm_used, modelLabel: "Model score", modelValue: `${(result.model_score * 100).toFixed(1)}%`, modelDetail: `${result.model_name} · ${result.target}`, rulesMatched: result.rule_findings.length, rulesDetail: `KB ${result.knowledge_base_version}`, conclusion: { summary: result.conclusion.summary, evidence: result.conclusion.evidence, uncertainties: result.conclusion.uncertainties, recommendedActions: result.conclusion.recommended_actions }, trace: result.trace, disclaimer: "Human review bắt buộc. Kết quả chỉ minh họa cách phối hợp model, rule và LLM; không dùng để tự động quyết định nhân sự." }} />}</main><footer className="agent-footer">EPI Reasoning Lab · prototype workspace</footer></div>;
}
export default AgentDemoApp;
