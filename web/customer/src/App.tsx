import { ChangeEvent, FormEvent, useState } from "react";
import {
  ArrowRight,
  Check,
  FileJson,
  ShieldCheck,
  Sparkles,
  UploadCloud,
} from "lucide-react";
import HarnessOutputView from "./HarnessOutputView";

type Profile = {
  age: number;
  income_million_vnd: number;
  occupation: string;
  employment_years: number;
  household_type: string;
  dependents: number;
  service_count: number;
  cic_score: number | null;
  schema_version?: string;
};
type HarnessResult = {
  extraction: { fields: string[]; source: string };
  ml_pattern: { status: string; model_name?: string; message: string };
  llm_rule_generation: { status: string; rules: { title: string; rule: string; feature_refs: string[]; limitation: string; confidence: string }[]; note: string };
  final_reasoning: { status: string; provider: string | null; model: string | null; summary: string; evidence: string[]; uncertainties: string[]; recommended_actions: string[]; error?: string };
  knowledge_base: { version: string; rule_count: number };
  synthetic_tests: { case_id: string; label: string; retrieved_rule_ids: string[]; reasoning_output: { classification?: string; confidence?: string } | null }[];
  agent_harness: { status: string; case_count: number; llm_calls: number; note: string };
  trace: string[];
  disclaimer: string;
};

const API = import.meta.env.VITE_API_URL ?? "";
const occupations = ["Nhân viên văn phòng", "Kinh doanh tự do", "Công chức/viên chức", "Lao động kỹ thuật", "Sinh viên", "Khác"];
const empty: Profile = { age: 35, income_million_vnd: 15, occupation: occupations[0], employment_years: 3, household_type: "Chung cư", dependents: 1, service_count: 2, cic_score: null };

function App() {
  const [profile, setProfile] = useState<Profile>(empty);
  const [fileName, setFileName] = useState("");
  const [harness, setHarness] = useState<HarnessResult | null>(null);
  const [useLlm, setUseLlm] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState<"input" | "review" | "result">("input");
  const update = (key: keyof Profile, value: string) => setProfile((current) => ({ ...current, [key]: key === "occupation" || key === "household_type" ? value : key === "cic_score" && value === "" ? null : Number(value) }));

  async function validateAndReview(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`${API}/api/leads/validate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(profile) });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? "Không thể kiểm tra hồ sơ");
      setProfile(body);
      setStep("review");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Không thể kết nối máy chủ");
    } finally {
      setBusy(false);
    }
  }

  async function runHarness() {
    setBusy(true);
    setError("");
    const { cic_score: _cic, schema_version: _schema, ...safeProfile } = profile;
    try {
      const response = await fetch(`${API}/api/credit-flow/run`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ profile: safeProfile, use_llm: useLlm }) });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? "Không thể chạy Agent Harness");
      setHarness(body as HarnessResult);
      setStep("result");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Không thể kết nối máy chủ");
    } finally {
      setBusy(false);
    }
  }

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    setError("");
    try {
      const parsed = JSON.parse(await file.text()) as Profile;
      const { schema_version: _schema, cic_score: _cic, ...lead } = parsed;
      const response = await fetch(`${API}/api/leads/validate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(lead) });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? "Lead JSON không hợp lệ");
      setProfile(body);
      setStep("review");
    } catch (e) {
      setError(e instanceof Error ? e.message : "File JSON không hợp lệ");
    }
  }

  const startOver = () => { setProfile(empty); setHarness(null); setUseLlm(false); setFileName(""); setError(""); setStep("input"); };
  return (
    <div className="shell">
      <header className="topbar"><div className="brand"><div className="brand-mark">D5</div><div><strong>DC5</strong><span>Credit reasoning</span></div></div><div className="secure"><ShieldCheck size={16} /> Phiên demo bảo mật</div></header>
      <main>
        <section className="hero"><div><p className="eyebrow"><Sparkles size={15} /> Customer → Agent Harness</p><h1>Điền hồ sơ,<br /><em>chạy reasoning.</em></h1><p className="lede">Một flow duy nhất: hồ sơ khách hàng đi qua extraction, ML pattern, Knowledge Base và 3 synthetic case trước khi Agent Harness trả trace.</p></div><div className="hero-card"><div className="hero-orbit orbit-one" /><div className="hero-orbit orbit-two" /><span>01</span><small>REASONING<br />FLOW</small></div></section>
        <div className="steps"><div className={step === "input" ? "active" : "done"}><b>{step === "input" ? "01" : <Check size={15} />}</b><span>Nhập hồ sơ</span></div><i /><div className={step === "review" ? "active" : step === "result" ? "done" : ""}><b>{step === "result" ? <Check size={15} /> : "02"}</b><span>Kiểm tra</span></div><i /><div className={step === "result" ? "active" : ""}><b>03</b><span>Agent Harness</span></div></div>
        {error && <div className="alert">{error}</div>}
        {step === "input" && <><div className="upload-card"><div className="upload-icon"><FileJson /></div><div><h3>Đã có lead JSON?</h3><p>Upload file theo schema <code>dc5-lead-v1</code> để điền nhanh hồ sơ.</p></div><label className="button secondary"><UploadCloud size={17} /> Chọn file<input type="file" accept=".json,application/json" onChange={upload} /></label>{fileName && <small className="filename">{fileName}</small>}</div><form className="panel" onSubmit={validateAndReview}><div className="panel-heading"><div><p className="eyebrow">Thông tin đầu vào</p><h2>Hồ sơ khách hàng</h2></div><span className="optional">Bước 1 / 3</span></div><div className="grid"><Field label="Tuổi" value={profile.age} onChange={(v) => update("age", v)} min={18} max={100} /><Field label="Thu nhập (triệu VNĐ/tháng)" value={profile.income_million_vnd} onChange={(v) => update("income_million_vnd", v)} min={0} step="0.5" /><Select label="Nghề nghiệp" value={profile.occupation} options={occupations} onChange={(v) => update("occupation", v)} /><Field label="Thâm niên làm việc (năm)" value={profile.employment_years} onChange={(v) => update("employment_years", v)} min={0} step="0.5" /><Select label="Loại hình nhà ở" value={profile.household_type} options={["Nhà thường", "Chung cư", "Nhà trọ", "Khác"]} onChange={(v) => update("household_type", v)} /><Field label="Số người phụ thuộc" value={profile.dependents} onChange={(v) => update("dependents", v)} min={0} max={20} /><Field label="Số dịch vụ đang sử dụng" value={profile.service_count} onChange={(v) => update("service_count", v)} min={0} max={10} /><Field label="CIC score (tùy chọn)" value={profile.cic_score ?? ""} onChange={(v) => update("cic_score", v)} min={0} max={900} /></div><div className="panel-footer"><p><ShieldCheck size={16} /> CIC chỉ dùng cho validation, không gửi sang LLM.</p><button className="button primary" disabled={busy}>{busy ? "Đang kiểm tra..." : <>Tiếp tục <ArrowRight size={17} /></>}</button></div></form></>}
        {step === "review" && <section className="panel review"><div className="panel-heading"><div><p className="eyebrow">Kiểm tra lại</p><h2>Thông tin đã chuẩn hóa</h2></div><span className="valid"><Check size={15} /> JSON hợp lệ</span></div><div className="review-grid">{Object.entries(profile).filter(([key]) => key !== "schema_version" && key !== "cic_score").map(([key, value]) => <div key={key}><small>{key.replaceAll("_", " ")}</small><strong>{String(value)}</strong></div>)}</div><label className="harness-option"><input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} /><span>Gọi LLM để sinh rule candidate và reasoning <small>Có thể tốn quota; tắt để chạy Harness deterministic.</small></span></label><div className="panel-footer"><button className="button secondary" onClick={() => setStep("input")}>Chỉnh sửa</button><button className="button primary" onClick={runHarness} disabled={busy}>{busy ? "Đang chạy harness..." : <>Chạy Agent Harness <ArrowRight size={17} /></>}</button></div></section>}
        {step === "result" && harness && <HarnessOutput result={harness} onRestart={startOver} />}
      </main>
      <footer>DC5 Customer Experience <span>•</span> Research prototype — không phải quyết định tín dụng</footer>
    </div>
  );
}

function HarnessOutput({ result, onRestart }: { result: HarnessResult; onRestart: () => void }) {
  const matchedRuleIds = new Set(result.synthetic_tests.flatMap((test) => test.retrieved_rule_ids));
  const llmUsed = result.final_reasoning.status === "llm_generated";
  return <HarnessOutputView data={{ provider: result.final_reasoning.provider ?? "fallback", llmUsed, modelLabel: "ML pattern", modelValue: result.ml_pattern.status === "available" ? "Ready" : "N/A", modelDetail: result.ml_pattern.model_name ?? "research evidence", rulesMatched: matchedRuleIds.size, rulesDetail: `KB ${result.knowledge_base.version}`, conclusion: { summary: result.final_reasoning.summary, evidence: result.final_reasoning.evidence, uncertainties: result.final_reasoning.uncertainties, recommendedActions: result.final_reasoning.recommended_actions }, trace: result.trace, disclaimer: result.disclaimer, error: result.final_reasoning.error }} onRestart={onRestart} />;
}

function Field({ label, value, onChange, min, max, step = "1" }: { label: string; value: number | string; onChange: (v: string) => void; min?: number; max?: number; step?: string }) { return <label className="field"><span>{label}</span><input type="number" value={value} min={min} max={max} step={step} onChange={(e) => onChange(e.target.value)} /></label>; }
function Select({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (v: string) => void }) { return <label className="field"><span>{label}</span><select value={value} onChange={(e) => onChange(e.target.value)}>{options.map((option) => <option key={option}>{option}</option>)}</select></label>; }
export default App;
