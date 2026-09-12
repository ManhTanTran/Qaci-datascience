import { ListChecks, Sparkles } from "lucide-react";

export type HarnessOutputData = {
  provider: string;
  llmUsed: boolean;
  modelLabel: string;
  modelValue: string;
  modelDetail: string;
  rulesMatched: number;
  rulesDetail: string;
  conclusion: {
    summary: string;
    evidence: string[];
    uncertainties: string[];
    recommendedActions: string[];
  };
  trace: string[];
  disclaimer: string;
  error?: string;
};

export default function HarnessOutputView({ data, onRestart }: { data: HarnessOutputData; onRestart?: () => void }) {
  return <section className="agent-card agent-output harness-result"><div className="agent-card-head"><div><span className="agent-index">03</span><div><p>Kết quả Agent Harness</p><h2>Kết luận có truy vết</h2></div></div><span className={`agent-provider ${data.llmUsed ? "live" : "fallback"}`}>{data.provider}</span></div><div className="result-summary"><Metric label={data.modelLabel} value={data.modelValue} detail={data.modelDetail} /><Metric label="Số rule phù hợp" value={String(data.rulesMatched)} detail={data.rulesDetail} /><Metric label="LLM" value={data.llmUsed ? "Trực tiếp" : "Dự phòng"} detail={data.llmUsed ? "Kết luận có cấu trúc" : "Kết luận xác định trước"} /></div><div className="conclusion"><p className="agent-kicker"><Sparkles size={14} /> Reasoning cuối cùng</p><h3>{data.conclusion.summary}</h3><div className="conclusion-cols"><ListBlock title="Bằng chứng" items={data.conclusion.evidence} /><ListBlock title="Điểm chưa chắc chắn" items={data.conclusion.uncertainties} /><ListBlock title="Hành động đề xuất" items={data.conclusion.recommendedActions} /></div>{data.error && <small className="harness-error">LLM chuyển sang dự phòng: {data.error}</small>}</div><div className="trace"><h4><ListChecks size={15} /> Truy vết Harness</h4>{data.trace.map((item, index) => <div key={`${item}-${index}`}>{item}</div>)}</div><p className="agent-disclaimer">{data.disclaimer}</p>{onRestart && <button className="button secondary harness-restart" onClick={onRestart}>Tạo flow mới</button>}</section>;
}

function Metric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <div><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>;
}

function ListBlock({ title, items }: { title: string; items: string[] }) {
  return <div><h4>{title}</h4><ul>{items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul></div>;
}
