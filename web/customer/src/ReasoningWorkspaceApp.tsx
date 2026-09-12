import { useEffect, useState } from "react";
import {
  BarChart3,
  BrainCircuit,
  CheckCircle2,
  Database,
  FlaskConical,
  GitBranch,
  LayoutDashboard,
  Play,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import HarnessOutputView from "./HarnessOutputView";
import "./reasoning-workspace.css";

const API = import.meta.env.VITE_API_URL ?? "";
type Page = "dashboard" | "discovery" | "knowledge" | "assessment" | "evaluation";
type Feature = { name: string; domain: string; evidence_type: string; limitation: string; allowed_for_reasoning: boolean };
type Rule = { id: string; type: string; domains: string[]; features: string[]; rule: string; source: string; evidence: string; limitation: string; confidence: string; status: string; version: string; owner: string; validation: Record<string, string> };
type Scenario = { case_id: string; label: string; description: string; features: Record<string, unknown> };
type Workspace = { counts: { features: number; rules: number; scenarios: number; rule_statuses: Record<string, number> }; domains: string[]; features: Feature[]; rules: Rule[]; scenarios: Scenario[]; llm: { configured: boolean; provider: string | null; model: string } };
type Evidence = { feature: string; value: unknown };
type ReasoningOutput = { classification: string; confidence: string; positive_evidence: Evidence[]; negative_evidence: Evidence[]; conflicts: Evidence[]; rules_used: string[]; unsupported_information: string[]; missing_information: string[]; reasoning_summary: string };
type Assessment = { scenario_id: string | null; label: string; normalized_features: Record<string, unknown>; detected_domains: string[]; observed_features: string[]; missing_features: string[]; unknown_features: string[]; retrieved_rules: Rule[]; prompt_type: string; llm_called: boolean; provider: string | null; model: string | null; output: ReasoningOutput | null; trace: string[] };
type Discovery = { ml_pattern: Record<string, unknown>; candidate_rules: { status: string; provider?: string; model?: string; rules: { title: string; rule: string; feature_refs: string[]; domains: string[]; evidence_basis: string; limitation: string; confidence: string }[]; note: string } };
type EvaluationRun = { model_choice: string; prompt_type: string; status: string; provider?: string; model?: string; classification?: string; confidence?: string; rule_adherence?: boolean; unsupported_information_count?: number; conflict_count?: number; output?: ReasoningOutput; error?: string };
type ReferenceRun = { run_id: string; model: string; turn: string; available: boolean; checks: Record<string, unknown> | null };
type AssessmentMode = "custom" | "synthetic";
type CustomerForm = {
  payment_on_time_rate_12m: string;
  overdue_days_max_12m: string;
  payment_failure_count_12m: string;
  active_domain_count: string;
  telco_internet_usage_group: string;
  recent_purchase_trend: string;
  monthly_income: string;
  monthly_expense: string;
  online_purchase_frequency: string;
};

const EMPTY_CUSTOMER: CustomerForm = {
  payment_on_time_rate_12m: "",
  overdue_days_max_12m: "",
  payment_failure_count_12m: "",
  active_domain_count: "",
  telco_internet_usage_group: "",
  recent_purchase_trend: "",
  monthly_income: "",
  monthly_expense: "",
  online_purchase_frequency: "",
};

const NAV: { id: Page; label: string; icon: React.ReactNode }[] = [
  { id: "dashboard", label: "Tổng quan", icon: <LayoutDashboard size={16} /> },
  { id: "discovery", label: "Khám phá rule", icon: <GitBranch size={16} /> },
  { id: "knowledge", label: "Kho tri thức", icon: <Database size={16} /> },
  { id: "assessment", label: "Đánh giá khách hàng", icon: <BrainCircuit size={16} /> },
  { id: "evaluation", label: "Đánh giá LLM", icon: <FlaskConical size={16} /> },
];

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, init);
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail ?? "Yêu cầu API thất bại");
  return body as T;
}

export default function ReasoningWorkspaceApp() {
  const [page, setPage] = useState<Page>("assessment");
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [error, setError] = useState("");
  async function load() {
    setError("");
    try { setWorkspace(await request<Workspace>("/api/reasoning/workspace")); }
    catch (e) { setError(e instanceof Error ? e.message : "Không tải được workspace"); }
  }
  useEffect(() => { void load(); }, []);
  return <div className="reasoning-workspace"><header className="rw-topbar"><div className="rw-brand"><span>CRA</span><div><strong>Agent Reasoning Tín dụng</strong><small>Kho tri thức · Harness · Đánh giá</small></div></div><div className={`rw-status ${workspace?.llm.configured ? "online" : ""}`}><i />{workspace?.llm.configured ? `${workspace.llm.provider} · ${workspace.llm.model}` : "LLM chưa cấu hình"}</div></header><div className="rw-layout"><aside className="rw-sidebar"><nav>{NAV.map((item) => <button key={item.id} className={page === item.id ? "active" : ""} onClick={() => setPage(item.id)}>{item.icon}<span>{item.label}</span></button>)}</nav><div className="rw-policy"><ShieldCheck size={17} /><b>Chỉ dùng nghiên cứu</b><p>Không phải điểm tín dụng hoặc quyết định phê duyệt/từ chối.</p></div></aside><main className="rw-main">{error && <div className="rw-alert">{error}<button onClick={() => void load()}><RefreshCw size={14} /> Thử lại</button></div>}{!workspace ? <Loading /> : <>{page === "dashboard" && <Dashboard data={workspace} />}{page === "discovery" && <RuleDiscovery />}{page === "knowledge" && <KnowledgeBase rules={workspace.rules} />}{page === "assessment" && <CustomerAssessment workspace={workspace} />}{page === "evaluation" && <Evaluation workspace={workspace} />}</>}</main></div></div>;
}

function Dashboard({ data }: { data: Workspace }) {
  const cards = [
    ["Feature đã đăng ký", data.counts.features, "Danh mục feature"],
    ["Rule trong kho tri thức", data.counts.rules, `${data.counts.rule_statuses.candidate ?? 0} rule ứng viên`],
    ["Tình huống synthetic", data.counts.scenarios, "Không chứa PII khách hàng"],
    ["Nhà cung cấp LLM", data.llm.configured ? "Sẵn sàng" : "Ngoại tuyến", data.llm.provider ?? "Chỉ chạy dự phòng"],
  ];
  return <PageShell kicker="Tổng quan hệ thống" title="Không gian Reasoning" description="Một nơi để xây rule, kiểm tra Kho tri thức, đánh giá khách hàng synthetic và thử độ ổn định của LLM."><div className="rw-kpis">{cards.map(([label, value, note]) => <article key={String(label)}><span>{label}</span><strong>{value}</strong><small>{note}</small></article>)}</div><section className="rw-card"><SectionTitle title="Luồng kiến trúc" note="Phiên bản hiện tại" /><div className="rw-pipeline">{["Bằng chứng lịch sử", "Phát hiện từ ML", "Rule ứng viên", "Kho tri thức", "Ngữ cảnh khách hàng", "LLM reasoning", "Bộ kiểm tra đầu ra"].map((item, index) => <div key={item}><b>{String(index + 1).padStart(2, "0")}</b><span>{item}</span></div>)}</div></section><section className="rw-card"><SectionTitle title="Các miền đã đăng ký" note={`${data.domains.length} miền`} /><div className="rw-tags">{data.domains.map((domain) => <span key={domain}>{translateDomain(domain)}</span>)}</div></section></PageShell>;
}

function RuleDiscovery() {
  const [data, setData] = useState<Discovery | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState(""), [hidden, setHidden] = useState<Set<string>>(new Set());
  async function run(useLlm: boolean) { setBusy(true); setError(""); try { setData(await request<Discovery>(`/api/reasoning/rule-discovery?use_llm=${useLlm}`, { method: "POST" })); } catch (e) { setError(e instanceof Error ? e.message : "Không chạy được bước khám phá rule"); } finally { setBusy(false); } }
  useEffect(() => { void run(false); }, []);
  const candidates = data?.candidate_rules.rules.filter((item) => !hidden.has(item.title)) ?? [];
  return <PageShell kicker="Dữ liệu lịch sử → rule" title="Khám phá rule" description="Đọc artifact ML tổng hợp thực tế, sau đó cho LLM chuyển phát hiện thành rule ứng viên. Rule ứng viên không tự động vào Kho tri thức.">{error && <InlineError text={error} />}<section className="rw-card"><SectionTitle title="Bằng chứng ML" note={translateStatus(String(data?.ml_pattern.status ?? "loading"))} /><div className="rw-evidence-grid"><Value label="Mô hình" value={String(data?.ml_pattern.model_name ?? "—")} /><Value label="ROC-AUC" value={formatMetric(data?.ml_pattern.roc_auc)} /><Value label="PR-AUC" value={formatMetric(data?.ml_pattern.pr_auc)} /><Value label="Tỷ lệ positive" value={formatMetric(data?.ml_pattern.positive_rate)} /></div><p className="rw-muted">{String(data?.ml_pattern.limitation ?? "Đang đọc artifact...")}</p><button className="rw-primary" disabled={busy} onClick={() => void run(true)}><Sparkles size={16} />{busy ? "Đang phân tích..." : "Sinh rule bằng LLM"}</button></section>{data && <section className="rw-card"><SectionTitle title="Hàng đợi kiểm định rule" note={translateStatus(data.candidate_rules.status)} /><p className="rw-muted">{data.candidate_rules.note}</p>{candidates.length === 0 ? <Empty text="Chưa có rule ứng viên. Cần bằng chứng ML và LLM đã cấu hình." /> : <div className="rw-candidates">{candidates.map((rule) => <article key={rule.title}><div><span className="rw-pill candidate">ứng viên</span><small>độ tin cậy {translateConfidence(rule.confidence)}</small></div><h3>{rule.title}</h3><p>{rule.rule}</p><dl><dt>Feature</dt><dd>{rule.feature_refs.join(", ")}</dd><dt>Bằng chứng</dt><dd>{rule.evidence_basis}</dd><dt>Giới hạn</dt><dd>{rule.limitation}</dd></dl><div className="rw-actions"><button disabled title="Cần bằng chứng dữ liệu, holdout và con người đánh giá">Chưa thể phê duyệt</button><button onClick={() => setHidden((current) => new Set([...current, rule.title]))}>Loại bản nháp</button></div></article>)}</div>}</section>}</PageShell>;
}

function KnowledgeBase({ rules }: { rules: Rule[] }) {
  const [selectedId, setSelectedId] = useState(rules[0]?.id ?? "");
  const selected = rules.find((rule) => rule.id === selectedId) ?? rules[0];
  return <PageShell kicker="Reasoning có quản trị" title="Kho tri thức" description="Mỗi rule có metadata, feature liên quan, bằng chứng, giới hạn và trạng thái kiểm định rõ ràng."><div className="rw-split"><section className="rw-card rw-table-card"><div className="rw-table"><div className="head"><span>ID</span><span>Miền</span><span>Nguồn</span><span>Trạng thái</span></div>{rules.map((rule) => <button key={rule.id} className={selected?.id === rule.id ? "selected" : ""} onClick={() => setSelectedId(rule.id)}><b>{rule.id}</b><span>{rule.domains.map(translateDomain).join(", ")}</span><span>{translateSource(rule.source)}</span><i className={`rw-pill ${rule.status}`}>{translateStatus(rule.status)}</i></button>)}</div></section>{selected && <section className="rw-card rw-detail"><div><span className={`rw-pill ${selected.status}`}>{translateStatus(selected.status)}</span><small>phiên bản {selected.version}</small></div><h2>{selected.id}</h2><p className="rw-rule-text">{selected.rule}</p><dl><dt>Feature liên quan</dt><dd>{selected.features.join(", ")}</dd><dt>Nguồn</dt><dd>{translateSource(selected.source)}</dd><dt>Bằng chứng</dt><dd>{selected.evidence}</dd><dt>Giới hạn</dt><dd>{selected.limitation}</dd><dt>Chủ sở hữu</dt><dd>{selected.owner}</dd></dl><h3>Kiểm định</h3><div className="rw-checks">{Object.entries(selected.validation).map(([check, state]) => <span key={check}><i className={state === "passed" ? "pass" : "pending"} />{translateValidationCheck(check)}<b>{translateStatus(state)}</b></span>)}</div></section>}</div></PageShell>;
}

function CustomerAssessment({ workspace }: { workspace: Workspace }) {
  const [scenarioId, setScenarioId] = useState(workspace.scenarios[0]?.case_id ?? ""), [useLlm, setUseLlm] = useState(workspace.llm.configured), [promptType, setPromptType] = useState("guided"), [result, setResult] = useState<Assessment | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const selected = workspace.scenarios.find((scenario) => scenario.case_id === scenarioId);
  async function analyze() { setBusy(true); setError(""); try { setResult(await request<Assessment>("/api/reasoning/assess", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scenario_id: scenarioId, use_llm: useLlm, prompt_type: promptType, model: "configured" }) })); } catch (e) { setError(e instanceof Error ? e.message : "Đánh giá khách hàng thất bại"); } finally { setBusy(false); } }
  return <PageShell kicker="Pipeline reasoning trực tuyến" title="Đánh giá khách hàng" description="Chọn một khách hàng synthetic, xem miền được phát hiện, rule được truy xuất và reasoning có cấu trúc đã qua kiểm tra.">{error && <InlineError text={error} />}<section className="rw-card"><SectionTitle title="Chọn khách hàng synthetic" note="Fixture được tạo từ simulate.zip" /><div className="rw-scenarios">{workspace.scenarios.map((scenario) => <button key={scenario.case_id} className={scenario.case_id === scenarioId ? "active" : ""} onClick={() => { setScenarioId(scenario.case_id); setResult(null); }}><b>{translateScenarioLabel(scenario.case_id, scenario.label)}</b><span>{translateScenarioDescription(scenario.case_id, scenario.description)}</span><small>{scenario.case_id}</small></button>)}</div>{selected && <div className="rw-feature-preview">{Object.entries(selected.features).map(([key, value]) => <span key={key}><small>{translateFeatureName(key)}</small><b>{translateFeatureValue(value)}</b></span>)}</div>}<div className="rw-runbar"><label><input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} /> Gọi LLM</label><label>Loại prompt<select value={promptType} onChange={(e) => setPromptType(e.target.value)}><option value="guided">Có hướng dẫn</option><option value="minimal">Tối giản</option></select></label><button className="rw-primary" disabled={busy} onClick={() => void analyze()}><Play size={15} />{busy ? "Đang chạy..." : "Phân tích khách hàng"}</button></div></section>{result && <><section className="rw-card"><SectionTitle title="Phát hiện miền và truy xuất rule" note={`${result.retrieved_rules.length} rule`} /><div className="rw-domain-line"><span>Miền được phát hiện</span>{result.detected_domains.map((domain) => <b key={domain}><CheckCircle2 size={14} />{translateDomain(domain)}</b>)}</div><div className="rw-retrieved">{result.retrieved_rules.map((rule) => <article key={rule.id}><b>{rule.id}</b><p>{rule.rule}</p><small>{rule.limitation}</small></article>)}</div></section><AssessmentOutput result={result} /></>}</PageShell>;
}

function AssessmentOutput({ result }: { result: Assessment }) {
  const output = result.output;
  const evidenceText = (items: Evidence[]) => items.map((item) => `${item.feature}: ${String(item.value)}`);
  return <HarnessOutputView data={{ provider: result.provider ?? "dự phòng", llmUsed: result.llm_called, modelLabel: output ? "Phân loại" : "Số miền", modelValue: output ? translateClassification(output.classification) : String(result.detected_domains.length), modelDetail: output ? `Độ tin cậy ${translateConfidence(output.confidence)}` : "LLM chưa chạy", rulesMatched: result.retrieved_rules.length, rulesDetail: "Tham chiếu đã được kiểm tra", conclusion: output ? { summary: output.reasoning_summary, evidence: [...evidenceText(output.positive_evidence), ...evidenceText(output.negative_evidence)], uncertainties: [...output.unsupported_information, ...output.missing_information], recommendedActions: ["Con người phải đánh giá trước mọi quyết định.", "Đối chiếu giới hạn của các rule đã sử dụng."] } : { summary: "Feature đã được chuẩn hóa và rule đã được truy xuất; chưa có phân loại từ LLM.", evidence: result.observed_features.map((item) => `Đã quan sát: ${item}`), uncertainties: [...result.missing_features.map((item) => `Đang thiếu: ${item}`), "Không có reasoning có cấu trúc khi LLM bị tắt."], recommendedActions: ["Cấu hình API key và bật Gọi LLM để sinh reasoning."] }, trace: result.trace, disclaimer: "Bản demo nghiên cứu; phân loại không phải điểm tín dụng, PD hoặc quyết định phê duyệt/từ chối." }} />;
}

function Evaluation({ workspace }: { workspace: Workspace }) {
  const [scenarioId, setScenarioId] = useState(workspace.scenarios[1]?.case_id ?? workspace.scenarios[0]?.case_id ?? ""), [promptType, setPromptType] = useState("guided"), [runs, setRuns] = useState<EvaluationRun[]>([]), [references, setReferences] = useState<ReferenceRun[]>([]), [policy, setPolicy] = useState(""), [busy, setBusy] = useState(false), [error, setError] = useState(""), [challenge, setChallenge] = useState<Record<string, unknown> | null>(null);
  useEffect(() => { request<{ runs: ReferenceRun[]; metrics_policy: string }>("/api/reasoning/evaluation/reference").then((data) => { setReferences(data.runs); setPolicy(data.metrics_policy); }).catch((e) => setError(e instanceof Error ? e.message : "Không đọc được simulate.zip")); }, []);
  async function evaluate() { setBusy(true); setError(""); setChallenge(null); try { const data = await request<{ runs: EvaluationRun[] }>("/api/reasoning/evaluate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scenario_id: scenarioId, models: ["gpt", "gemini"], prompt_types: [promptType] }) }); setRuns(data.runs); } catch (e) { setError(e instanceof Error ? e.message : "Evaluation thất bại"); } finally { setBusy(false); } }
  async function runChallenge(run: EvaluationRun) { if (!run.output) return; setBusy(true); setError(""); try { setChallenge(await request<Record<string, unknown>>("/api/reasoning/challenge", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scenario_id: scenarioId, original_output: run.output, model: run.model_choice, prompt_type: promptType, challenge: "Khách hàng có mức tương tác mạnh và sử dụng nhiều dịch vụ. Tại sao không coi đây là hồ sơ ổn định? Không thêm dữ kiện mới." }) })); } catch (e) { setError(e instanceof Error ? e.message : "Phản biện thất bại"); } finally { setBusy(false); } }
  return <PageShell kicker="Độ ổn định của mô hình và prompt" title="Đánh giá LLM" description="So sánh GPT/Gemini trên cùng tình huống và prompt; phản biện chỉ kiểm tra độ ổn định, không suy ra độ chính xác khi chưa có nhãn chuẩn.">{error && <InlineError text={error} />}<section className="rw-card"><div className="rw-eval-controls"><label>Tình huống<select value={scenarioId} onChange={(e) => setScenarioId(e.target.value)}>{workspace.scenarios.map((scenario) => <option key={scenario.case_id} value={scenario.case_id}>{translateScenarioLabel(scenario.case_id, scenario.label)}</option>)}</select></label><label>Loại prompt<select value={promptType} onChange={(e) => setPromptType(e.target.value)}><option value="guided">Có hướng dẫn</option><option value="minimal">Tối giản</option></select></label><button className="rw-primary" disabled={busy} onClick={() => void evaluate()}><FlaskConical size={15} />{busy ? "Đang gọi mô hình..." : "Chạy GPT + Gemini"}</button></div></section>{runs.length > 0 && <section className="rw-card"><SectionTitle title="Kết quả đánh giá trực tiếp" note="Đầu ra đã được kiểm tra schema" /><div className="rw-eval-table"><div className="head"><span>Mô hình</span><span>Phân loại</span><span>Độ tin cậy</span><span>Tuân thủ rule</span><span>Thông tin chưa hỗ trợ</span><span /></div>{runs.map((run) => <div key={`${run.model_choice}-${run.prompt_type}`}><b>{run.model_choice}</b><span>{run.classification ? translateClassification(run.classification) : translateStatus(run.status)}</span><span>{run.confidence ? translateConfidence(run.confidence) : "—"}</span><span>{run.rule_adherence ? "Đạt" : "—"}</span><span>{run.unsupported_information_count ?? "—"}</span>{run.status === "completed" ? <button onClick={() => void runChallenge(run)}>Phản biện</button> : <small>{run.error}</small>}</div>)}</div></section>}{challenge && <section className="rw-card rw-challenge"><SectionTitle title="Kết quả phản biện" note={translateStatus(String(challenge.conclusion))} /><div><Value label="Ban đầu" value={translateClassification(String(challenge.original_classification))} /><Value label="Sau phản biện" value={translateClassification(String(challenge.challenged_classification))} /><Value label="Thay đổi" value={challenge.classification_changed ? "Cần đánh giá lại" : "Ổn định"} /></div></section>}<section className="rw-card"><SectionTitle title="Kiểm tra dữ liệu tham chiếu simulate.zip" note={`${references.filter((run) => run.available).length} tệp có sẵn`} /><p className="rw-muted">{translatePolicy(policy) || "Đang đọc manifest..."}</p><div className="rw-reference-grid">{references.map((run) => <article key={run.run_id}><div><b>{run.model}</b><span>{run.turn === "one_shot" ? "một lượt" : "phản biện"}</span></div><p>{run.available ? "Đã phân tích từ tệp đính kèm" : "Không tìm thấy tệp"}</p>{run.checks && <ul><li>Đủ phạm vi: {displayCheck(run.checks.coverage_complete)}</li><li>Xử lý xung đột: {displayCheck(run.checks.conflict_handling_present)}</li><li>Nhận biết dữ liệu thiếu: {displayCheck(run.checks.missingness_awareness_present)}</li><li>Thận trọng nhân quả: {displayCheck(run.checks.causal_caution_present)}</li></ul>}</article>)}</div></section></PageShell>;
}

function PageShell({ kicker, title, description, children }: { kicker: string; title: string; description: string; children: React.ReactNode }) { return <div className="rw-page"><header className="rw-page-head"><p>{kicker}</p><h1>{title}</h1><span>{description}</span></header>{children}</div>; }
function SectionTitle({ title, note }: { title: string; note: string }) { return <div className="rw-section-title"><h2>{title}</h2><span>{note}</span></div>; }
function Value({ label, value }: { label: string; value: string }) { return <div className="rw-value"><span>{label}</span><strong>{value}</strong></div>; }
function InlineError({ text }: { text: string }) { return <div className="rw-inline-error">{text}</div>; }
function Empty({ text }: { text: string }) { return <div className="rw-empty"><Search size={22} /><p>{text}</p></div>; }
function Loading() { return <div className="rw-loading"><RefreshCw size={22} /><p>Đang tải không gian Reasoning...</p></div>; }
function formatMetric(value: unknown) { const number = Number(value); return Number.isFinite(number) ? number.toFixed(3) : "—"; }
function displayCheck(value: unknown) { return value === true ? "Có" : value === false ? "Chưa phát hiện" : "Không chấm"; }
function translateDomain(value: string) { return ({ payment: "thanh toán", engagement: "tương tác", shopping: "mua sắm", capacity: "khả năng tài chính", consumption: "tiêu dùng", demographic: "nhân khẩu học", employment: "việc làm", healthcare: "y tế", loyalty: "khách hàng thân thiết", regional_context: "bối cảnh khu vực" } as Record<string, string>)[value] ?? value; }
function translateStatus(value: string) { return ({ available: "sẵn có", loading: "đang tải", ready_to_run: "sẵn sàng chạy", candidate_generated: "đã sinh ứng viên", candidate: "ứng viên", validated: "đã kiểm định", rejected: "đã loại", deprecated: "ngừng sử dụng", completed: "hoàn tất", error: "lỗi", passed: "đạt", pending: "đang chờ", not_run: "chưa chạy", not_applicable: "không áp dụng", failed: "không đạt", stable: "ổn định", changed_requires_review: "thay đổi, cần đánh giá lại" } as Record<string, string>)[value] ?? value; }
function translateConfidence(value: string) { return ({ Low: "thấp", Medium: "trung bình", High: "cao", low: "thấp", medium: "trung bình", high: "cao" } as Record<string, string>)[value] ?? value; }
function translateClassification(value: string) { return ({ "Relatively stable": "Tương đối ổn định", Mixed: "Tín hiệu hỗn hợp", "Potentially risky": "Có khả năng rủi ro" } as Record<string, string>)[value] ?? value; }
function translateSource(value: string) { return ({ human: "con người", domain_rule: "rule nghiệp vụ", ml_discovery: "khám phá từ ML", failure_analysis: "phân tích lỗi" } as Record<string, string>)[value] ?? value; }
function translateValidationCheck(value: string) { return ({ data_support: "bằng chứng dữ liệu", holdout: "kiểm tra holdout", logical_consistency: "tính nhất quán logic", causal_claim_check: "kiểm tra tuyên bố nhân quả", human_review: "con người đánh giá" } as Record<string, string>)[value] ?? value.replaceAll("_", " "); }
function translateScenarioLabel(id: string, fallback: string) { return ({ stable_profile: "Thanh toán ổn định, tương tác bình thường", conflicting_signals: "Tương tác tích cực nhưng thanh toán xung đột", deteriorating_profile: "Hành vi thanh toán suy giảm" } as Record<string, string>)[id] ?? fallback; }
function translateScenarioDescription(id: string, fallback: string) { return ({ stable_profile: "Đã quan sát hành vi thanh toán và mức tương tác không bất thường.", conflicting_signals: "Tín hiệu tương tác, mua sắm tích cực nhưng hành vi thanh toán chưa nhất quán.", deteriorating_profile: "Quan sát thanh toán yếu hơn và mức tương tác gần đây đang giảm." } as Record<string, string>)[id] ?? fallback; }
function translateFeatureName(value: string) { return ({ payment_on_time_rate_12m: "Tỷ lệ thanh toán đúng hạn trong 12 tháng", overdue_days_max_12m: "Số ngày quá hạn tối đa trong 12 tháng", payment_failure_count_12m: "Số lần thanh toán thất bại trong 12 tháng", active_domain_count: "Mức sử dụng dịch vụ", telco_internet_usage_group: "Mức sử dụng Internet", recent_purchase_trend: "Xu hướng mua sắm gần đây" } as Record<string, string>)[value] ?? value.replaceAll("_", " "); }
function translateFeatureValue(value: unknown) { const text = String(value); return ({ low: "thấp", medium: "trung bình", high: "cao", stable: "ổn định", rising: "đang tăng", declining: "đang giảm" } as Record<string, string>)[text] ?? text; }
function translatePolicy(value: string) { return value ? "Không báo cáo độ chính xác, độ bền hoặc tỷ lệ ảo giác khi chưa có prompt gốc, metadata mô hình, đầu ra có cấu trúc và rubric được phê duyệt." : ""; }
