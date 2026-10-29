"use strict";
// Module 2 ops UI. All dynamic text goes through esc(): answers come from chatbots/web pages.
const $ = (id) => document.getElementById(id);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (v) => (v == null ? "—" : `${(v * 100).toFixed(1)}%`);
const num = (v) => (v == null ? "—" : Number(v).toLocaleString("vi-VN"));
const trieu = (v) => (v == null ? "" : `${(v / 1e6).toLocaleString("vi-VN", { maximumFractionDigits: 1 })}`);
const short = (iso) => (iso ? String(iso).replace("T", " ").slice(0, 19) : "—");
const bytes = (n) => (n == null ? "—" : n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1048576).toFixed(1)} MB`);
const pill = (s) => `<span class="pill ${esc(s)}">${esc(s)}</span>`;

let state = { tab: "overview", aOff: 0, cOff: 0, status: null };
const PAGE = 50;

const BASE = "/api/v1/extract-claims";
async function api(path, opts = {}) {
  path = path.replace(/^\/api\//, BASE + "/");
  const init = { method: opts.method || "GET", headers: {} };
  if (init.method === "POST") {
    init.headers["Content-Type"] = "application/json";
    init.headers["X-Requested-With"] = "ops-ui";
    init.body = JSON.stringify(opts.body || {});
  }
  const res = await fetch(path, init);
  let data = null;
  try { data = await res.json(); } catch { /* non-JSON */ }
  if (!res.ok) throw new Error((data && data.detail) || `HTTP ${res.status}`);
  return data;
}

let toastTimer;
function toast(msg, isErr = false) {
  const t = $("toast");
  t.textContent = msg; t.className = "toast" + (isErr ? " err" : ""); t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => (t.hidden = true), 5000);
}
async function act(fn, okMsg) {
  try { const r = await fn(); if (okMsg) toast(typeof okMsg === "function" ? okMsg(r) : okMsg); refresh(true); return r; }
  catch (e) { toast(e.message, true); }
}

// ---------- tabs ----------
document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
function showTab(name) {
  state.tab = name;
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("is-active", b.dataset.tab === name));
  document.querySelectorAll(".pane").forEach((p) => p.classList.toggle("is-active", p.id === `tab-${name}`));
  refresh(true);
}

// ---------- overview ----------
function card(label, value, cls = "", sub = "") {
  return `<div class="card ${cls}"><div class="n">${esc(value)}</div><div class="l">${esc(label)}</div>${sub ? `<div class="s">${esc(sub)}</div>` : ""}</div>`;
}

function renderStatus(s) {
  state.status = s;
  const ov = s.overview, st = ov.status;
  const badge = $("modeBadge");
  badge.textContent = s.auto_running ? "Tự động: BẬT" : s.mode === "auto" ? "Tự động: TẮT" : "Thủ công";
  badge.className = "badge" + (s.auto_running ? " auto" : "");
  $("queueCards").innerHTML =
    card("Chờ xử lý", num(st.pending), st.pending ? "warn" : "") +
    card("Đang xử lý", num(st.processing)) +
    card("OK (có claim)", num(st.ok), "ok") +
    card("Rỗng (0 claim)", num(st.empty)) +
    card("Lỗi", num(st.failed), st.failed ? "err" : "", ov.failed_exhausted ? `${ov.failed_exhausted} đã hết lượt thử` : "") +
    card("Claim", num(ov.claims), "ok") +
    card("Claim bị loại", num(ov.rejected), ov.rejected ? "warn" : "") +
    card("Dòng đầu vào lỗi", num(ov.input_errors), ov.input_errors ? "warn" : "");

  const p = s.worker.progress, busyElsewhere = s.worker.busy_elsewhere;
  const running = p.running;
  let w = "";
  if (running) {
    const pc = p.target ? Math.min(100, Math.round((p.processed / p.target) * 100)) : 0;
    w = `<div class="state">Đang chạy (${esc(p.trigger)}) · ${esc(p.phase)} · ${p.elapsed_s ?? 0}s</div>
         <div class="progress"><i style="width:${pc}%"></i></div>
         <div class="muted">${p.processed}/${p.target} answer · ok ${p.ok} · rỗng ${p.empty} · lỗi ${p.failed} · claim ${p.claims} · bị loại ${p.rejected}</div>`;
  } else if (busyElsewhere) {
    const l = s.worker.lock;
    w = `<div class="state">Tiến trình khác đang xử lý (pid ${esc(l.pid)} · ${esc(l.activity || "")}) — chờ nó xong.</div>`;
  } else {
    const last = p.last_status ? ` · lượt trước: ${esc(p.last_status)}${p.last_error ? " — " + esc(p.last_error) : ""}` : "";
    w = `<div class="state">Rảnh${last}</div>`;
  }
  $("workerBox").innerHTML = w;
  $("btnRun").disabled = running || busyElsewhere;
  $("btnTrial").disabled = running || busyElsewhere;
  $("btnRetry").disabled = running || busyElsewhere;
  $("btnStop").disabled = !running;
  const toggle = $("autoToggle");
  toggle.checked = s.auto_running; toggle.disabled = !s.allow_mode_switch;
  $("autoText").textContent = s.allow_mode_switch
    ? "Tự động xử lý khi Module 1 ghi thêm dữ liệu (chỉ trong lúc UI này đang mở)"
    : "Đổi chế độ bị khóa bởi config.yaml";

  const f = s.input_file;
  $("inputBox").innerHTML = [
    ["File đầu vào", f.path + (f.exists ? "" : "  (CHƯA TỒN TẠI)")],
    ["Kích thước", f.exists ? bytes(f.size) : "—"],
    ["Sửa lần cuối", short(f.modified_at)],
    ["Đã quét tới", f.scanned_bytes == null ? "—" : bytes(f.scanned_bytes)],
    ["Chưa quét", f.unscanned_bytes == null ? "—" : bytes(f.unscanned_bytes) + (f.unscanned_bytes ? " (dữ liệu mới hoặc dòng đang ghi dở)" : "")],
    ["Database", s.database_file],
    ["Model trích xuất", s.extractor.model],
    ["Phiên bản", s.extractor.version],
    ["Lô / số lần thử", `${s.processing.batch_size} answer · tối đa ${s.processing.max_retries} lần`],
  ].map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("");
  const r = s.last_run;
  $("lastRun").innerHTML = r
    ? `#${r.run_id} · ${pill(r.status)} · ${esc(r.trigger)} · ${short(r.started_at)} · ${num(r.duration_ms)} ms<br>
       mới ${r.registered} · xử lý ${r.processed} (ok ${r.ok}, rỗng ${r.empty}, lỗi ${r.failed}) · claim ${r.claims} · bị loại ${r.rejected} · gọi LLM ${r.llm_calls} · token ${num(r.prompt_tokens)} vào / ${num(r.completion_tokens)} ra${r.error ? `<br><span class="pill error">${esc(r.error)}</span>` : ""}`
    : "Chưa có lượt chạy nào.";
}

// ---------- quality ----------
function bars(el, obj, empty = "Không có dữ liệu.") {
  const entries = Object.entries(obj || {});
  if (!entries.length) { $(el).innerHTML = `<span class="muted">${empty}</span>`; return; }
  const max = Math.max(...entries.map(([, v]) => v));
  $(el).innerHTML = entries.slice(0, 12).map(([k, v]) =>
    `<div class="bar"><span class="k" title="${esc(k)}">${esc(k)}</span><span class="t"><i style="width:${(v / max) * 100}%"></i></span><b>${num(v)}</b></div>`).join("");
}
function table(el, head, rows, empty = "Không có dữ liệu.") {
  $(el).innerHTML = rows.length
    ? `<thead><tr>${head.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody>`
    : `<tbody><tr><td class="muted">${empty}</td></tr></tbody>`;
}

function renderAlerts(alerts) {
  $("alerts").innerHTML = (alerts || []).map((a) => `<div class="alert ${esc(a.level)}"><b>${esc(a.level.toUpperCase())}</b> · ${esc(a.message)}</div>`).join("");
}

function renderQuality(q) {
  const r = q.rates;
  $("rateCards").innerHTML =
    card("Answer OK", pct(r.ok), "ok", `${num(q.finished_answers)} answer đã xong`) +
    card("Answer rỗng", pct(r.empty), "", `${num(q.empty_declared_no_result)} do 'chưa tìm thấy' (không gọi LLM)`) +
    card("Answer lỗi", pct(r.failed), r.failed > 0.1 ? "err" : "") +
    card("Claim bị loại", pct(r.rejected), r.rejected > 0.25 ? "err" : "", `${num(q.rejected)} / ${num(q.claims + q.rejected)}`) +
    card("Claim bị gắn cờ", pct(r.flagged), r.flagged > 0.3 ? "warn" : "", `${num(q.flagged)} / ${num(q.claims)}`) +
    card("Claim có nguồn URL", pct(r.with_source), "", "dẫn [n] khớp danh sách nguồn") +
    card("Claim / answer OK", q.claims_per_ok_answer ?? "—") +
    card("Độ trễ LLM (p50 / p95)", `${num(q.latency_ms.p50)} / ${num(q.latency_ms.p95)} ms`, "", `trung bình ${num(q.latency_ms.avg)} ms · ${q.latency_ms.samples} mẫu`);
  const d = q.distributions;
  bars("dConf", d.confidence_flag); bars("dType", d.property_type); bars("dBasis", d.price_basis);
  bars("dRej", q.rejected_reasons, "Chưa có claim bị loại."); bars("dFlag", q.flag_reasons, "Chưa có claim bị gắn cờ.");
  $("dErr").innerHTML = q.top_errors.length
    ? q.top_errors.map((e) => `<div class="bar"><span class="k" style="grid-column:1/3;white-space:normal">${esc(e.error)}</span><b>${e.n}</b></div>`).join("")
    : '<span class="muted">Không có lỗi.</span>';
  table("tMonth", ["Tháng", "Answer", "OK", "Rỗng", "Lỗi", "Chờ", "Claim", "Gắn cờ"],
    q.by_month.map((m) => `<tr><td>${esc(m.month)}</td><td class="num">${m.answers}</td><td class="num">${m.ok}</td><td class="num">${m.empty}</td><td class="num">${m.failed}</td><td class="num">${m.waiting}</td><td class="num">${m.claims}</td><td class="num">${m.flagged} (${m.claims ? Math.round((m.flagged / m.claims) * 100) : 0}%)</td></tr>`));
  table("tBot", ["Chatbot", "Answer", "OK", "Rỗng", "Lỗi"],
    q.by_chatbot.map((b) => `<tr><td>${esc(b.chatbot)}</td><td class="num">${b.answers}</td><td class="num">${b.ok}</td><td class="num">${b.empty}</td><td class="num">${b.failed}</td></tr>`));
  table("tVer", ["Phiên bản", "Answer"],
    q.extractor_versions.map((v) => `<tr><td><code>${esc(v.version)}</code>${v.version === q.current_version ? " ✓ hiện tại" : ""}</td><td class="num">${v.n}</td></tr>`));
  $("btnStale").disabled = !q.stale_answers;
  $("btnStale").textContent = `Xử lý lại answer dùng bản cũ (${q.stale_answers})`;
}

// ---------- answers ----------
async function loadAnswers() {
  const p = new URLSearchParams({ limit: PAGE, offset: state.aOff });
  [["status", "aStatus"], ["month", "aMonth"], ["chatbot", "aBot"], ["q", "aSearch"]].forEach(([k, id]) => $(id).value && p.set(k, $(id).value.trim()));
  const data = await api(`/api/answers?${p}`);
  table("tAnswers", ["Trạng thái", "Tháng", "Chatbot", "Câu hỏi", "Claim", "Bị loại", "Lần thử", "Lỗi / ghi chú", "Xử lý lúc"],
    data.rows.map((a) => `<tr class="click" data-id="${esc(a.answer_id)}"><td>${pill(a.status)}</td><td>${esc(a.target_month || "—")}</td><td>${esc(a.chatbot)}</td><td class="q">${esc(a.query_text)}</td><td class="num">${a.claims}</td><td class="num">${a.rejected}</td><td class="num">${a.attempt_count}</td><td class="q">${esc(a.last_error || a.note || "")}</td><td>${short(a.processed_at)}</td></tr>`),
    "Không có answer nào khớp bộ lọc.");
  $("tAnswers").querySelectorAll("tr.click").forEach((tr) => tr.addEventListener("click", () => openAnswer(tr.dataset.id)));
  pager("aPager", data.total, state.aOff, (o) => { state.aOff = o; loadAnswers(); });
}
function pager(id, total, off, go) {
  const end = Math.min(total, off + PAGE);
  $(id).innerHTML = `<span>${total ? off + 1 : 0}–${end} / ${num(total)}</span><button class="btn" ${off ? "" : "disabled"} id="${id}P">‹</button><button class="btn" ${end < total ? "" : "disabled"} id="${id}N">›</button>`;
  $(`${id}P`).onclick = () => go(Math.max(0, off - PAGE));
  $(`${id}N`).onclick = () => go(off + PAGE);
}

async function openAnswer(id) {
  const a = await api(`/api/answers/${encodeURIComponent(id)}`);
  $("dwTitle").textContent = `Answer ${a.answer_id.slice(0, 10)}…`;
  const claims = a.claims.map((c) => `<tr><td>${pill(c.confidence_flag)}</td><td>${esc([c.ward, c.district, c.street].filter(Boolean).join(" · "))}</td><td>${esc(c.property_type)}${c.sub_segment ? "<br><span class=muted>" + esc(c.sub_segment) + "</span>" : ""}</td><td class="num">${trieu(c.value_low)}${c.value_high ? "–" + trieu(c.value_high) : ""}${c.open_ended ? "+" : ""}</td><td class="q">${esc(c.quote)}${c.flag_reasons.length ? "<br><b>" + esc(c.flag_reasons.join(", ")) + "</b>" : ""}</td></tr>`);
  const rej = a.rejected_items.map((r) => `<tr><td><span class="pill error">${esc(r.reason)}</span></td><td class="q">${esc(r.detail || "")}</td><td class="q">${esc(JSON.stringify(r.raw || {}).slice(0, 400))}</td></tr>`);
  $("dwBody").innerHTML = `
    <div class="actions">${pill(a.status)}<span>lần thử ${a.attempt_count} · xử lý lại ${a.reprocess_count} · ${a.duration_ms ?? "—"} ms</span>
      <button class="btn" id="dwRe">Xử lý lại answer này</button></div>
    <dl class="kv"><dt>answer_id</dt><dd>${esc(a.answer_id)}</dd><dt>crawl_run_id</dt><dd>${esc(a.crawl_run_id || "—")}</dd><dt>target_month</dt><dd>${esc(a.target_month || "—")}</dd>
      <dt>crawled_at</dt><dd>${esc(a.crawled_at)}</dd><dt>chatbot / model</dt><dd>${esc(a.chatbot)} / ${esc(a.model_name || "—")}</dd><dt>phiên bản</dt><dd>${esc(a.extractor_version || "—")}</dd>
      ${a.last_error ? `<dt>Lỗi</dt><dd>${esc(a.last_error)}</dd>` : ""}${a.note ? `<dt>Ghi chú</dt><dd>${esc(a.note)}</dd>` : ""}
      <dt>Claim cũ (lịch sử)</dt><dd>${a.history_count}</dd></dl>
    <h3>Câu hỏi</h3><pre>${esc(a.query_text)}</pre>
    <h3>Claim (${a.claims.length})</h3>${a.claims.length ? `<div class="scroll"><table><thead><tr><th>Cờ</th><th>Địa điểm</th><th>Loại</th><th>triệu/m²</th><th>Trích dẫn / lý do cờ</th></tr></thead><tbody>${claims.join("")}</tbody></table></div>` : '<span class="muted">Không có.</span>'}
    <h3>Claim bị loại (${a.rejected_items.length})</h3>${rej.length ? `<table><thead><tr><th>Lý do</th><th>Chi tiết</th><th>Dữ liệu LLM trả</th></tr></thead><tbody>${rej.join("")}</tbody></table>` : '<span class="muted">Không có.</span>'}
    <h3>Văn bản gốc</h3><pre>${esc(a.answer_text)}</pre>`;
  $("dwRe").onclick = () => act(() => api("/api/reprocess", { method: "POST", body: { answer_ids: [a.answer_id] } }), (r) => `Đã xếp lại ${r.requeued} answer${r.started ? " và bắt đầu chạy" : ""}.`);
  $("drawer").hidden = false;
}
$("dwClose").onclick = () => ($("drawer").hidden = true);

// ---------- usage ----------
const money = (v, cur) => (v == null ? "—" : `${Number(v).toLocaleString("en-US", { maximumFractionDigits: 4 })} ${cur}`);
async function loadUsage() {
  const u = await api("/api/usage"), t = u.total, cur = u.currency;
  $("usageNote").innerHTML = u.prices_configured
    ? `Quy đổi tiền theo giá trong <code>config.yaml → cost.module2</code> (${esc(cur)}).`
    : "Chưa cấu hình giá: chỉ hiển thị token. Điền <code>cost.module2</code> trong <code>config.yaml</code> để xem chi phí.";
  $("usageCards").innerHTML =
    card("Token đầu vào", num(t.prompt_tokens)) + card("Token đầu ra", num(t.completion_tokens)) +
    card("Tổng token", num(t.tokens)) + card("Số lần gọi LLM", num(t.llm_calls), "", `${num(t.answers_without_llm)} answer không cần gọi LLM`) +
    card("Chi phí ước tính", money(t.cost, cur), "", t.avg_cost_per_answer != null ? `${money(t.avg_cost_per_answer, cur)} / answer` : "") +
    card("Token TB / lần gọi", num(t.avg_tokens_per_llm_call), "", `model ${u.model}`) +
    card("Lần gọi thiếu usage", num(t.usage_missing_calls), t.usage_missing_calls ? "warn" : "", "endpoint không trả token");
  table("tUsageMonth", ["Tháng", "Answer", "Lần gọi", "Token vào", "Token ra", "Chi phí"],
    u.by_month.map((m) => `<tr><td>${esc(m.month)}</td><td class="num">${num(m.answers)}</td><td class="num">${num(m.llm_calls)}</td><td class="num">${num(m.prompt_tokens)}</td><td class="num">${num(m.completion_tokens)}</td><td class="num">${money(m.cost, cur)}</td></tr>`));
  table("tUsageRun", ["#", "Kích hoạt", "Bắt đầu", "Xử lý", "Lần gọi", "Token vào", "Token ra", "Chi phí"],
    u.by_run.map((r) => `<tr><td>${r.run_id}</td><td>${esc(r.trigger)}</td><td>${short(r.started_at)}</td><td class="num">${r.processed}</td><td class="num">${num(r.llm_calls)}</td><td class="num">${num(r.prompt_tokens)}</td><td class="num">${num(r.completion_tokens)}</td><td class="num">${money(r.cost, cur)}</td></tr>`));
}

// ---------- claims / errors / runs ----------
function claimParams() {
  const p = new URLSearchParams();
  [["month", "cMonth"], ["flag", "cFlag"], ["property_type", "cType"], ["q", "cSearch"]].forEach(([k, id]) => $(id).value && p.set(k, $(id).value.trim()));
  return p;
}
async function loadClaims() {
  const p = claimParams(); p.set("limit", PAGE); p.set("offset", state.cOff);
  const data = await api(`/api/claims?${p}`);
  table("tClaims", ["Tháng", "Phường / Quận", "Phố", "Loại", "Cơ sở", "Chỉ số", "triệu/m²", "Cờ", "Ghi chú", "Nguồn", "Trích dẫn"],
    data.rows.map((c) => `<tr><td>${esc(c.target_month || "—")}</td><td>${esc([c.ward, c.district].filter(Boolean).join(", "))}</td><td>${esc(c.street || "")}</td><td>${esc(c.property_type)}${c.sub_segment ? "<br><span class=muted>" + esc(c.sub_segment) + "</span>" : ""}</td><td>${esc(c.price_basis)}</td><td>${esc(c.metric)}</td><td class="num">${trieu(c.value_low)}${c.value_high ? "–" + trieu(c.value_high) : ""}${c.open_ended ? "+" : ""}</td><td>${pill(c.confidence_flag)}</td><td class="q">${esc([c.qualifier, c.period_text].filter(Boolean).join(" · "))}</td><td>${(c.source_urls || []).map((u, i) => /^https?:\/\//.test(u) ? `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">[${i + 1}]</a>` : "").join(" ")}</td><td class="q">${esc(c.quote)}</td></tr>`),
    "Không có claim nào khớp bộ lọc.");
  pager("cPager", data.total, state.cOff, (o) => { state.cOff = o; loadClaims(); });
  const m = $("cMonth").value.trim();
  $("expCsv").href = `${BASE}/export?format=csv${m ? "&month=" + encodeURIComponent(m) : ""}`;
  $("expJsonl").href = `${BASE}/export?format=jsonl${m ? "&month=" + encodeURIComponent(m) : ""}`;
}
async function loadErrors() {
  const rows = await api("/api/input-errors");
  table("tErrors", ["Lúc", "File", "Vị trí (byte/stt)", "Lý do", "Trích đoạn"],
    rows.map((e) => `<tr><td>${short(e.seen_at)}</td><td>${esc(e.source_file.split(/[\\/]/).pop())}</td><td class="num">${esc(e.position ?? "—")}</td><td>${esc(e.reason)}</td><td class="q">${esc(e.snippet || "")}</td></tr>`),
    "Không có dòng lỗi.");
}
async function loadRuns() {
  const rows = await api("/api/runs");
  const max = Math.max(1, ...rows.map((r) => r.processed));
  $("runChart").innerHTML = rows.slice().reverse().map((r) => {
    const h = (n) => Math.max(n ? 3 : 0, Math.round((n / max) * 100));
    return `<div class="col" title="#${r.run_id} ${esc(r.status)}"><div class="stack"><i style="height:${h(r.ok)}px;background:var(--ok)"></i><i style="height:${h(r.empty)}px;background:var(--info)"></i><i style="height:${h(r.failed)}px;background:var(--err)"></i></div>#${r.run_id}</div>`;
  }).join("") || '<span class="muted">Chưa có lượt chạy.</span>';
  table("tRuns", ["#", "Trạng thái", "Kích hoạt", "Bắt đầu", "Thời lượng", "Mới", "Xử lý", "OK", "Rỗng", "Lỗi", "Claim", "Bị loại", "Tỉ lệ loại", "Gọi LLM", "Token vào/ra", "Phiên bản", "Lỗi"],
    rows.map((r) => `<tr><td>${r.run_id}</td><td>${pill(r.status)}</td><td>${esc(r.trigger)}</td><td>${short(r.started_at)}</td><td class="num">${r.duration_ms == null ? "…" : num(r.duration_ms) + " ms"}</td><td class="num">${r.registered}</td><td class="num">${r.processed}</td><td class="num">${r.ok}</td><td class="num">${r.empty}</td><td class="num">${r.failed}</td><td class="num">${r.claims}</td><td class="num">${r.rejected}</td><td class="num">${pct(r.rejected_rate)}</td><td class="num">${r.llm_calls}</td><td class="num">${num(r.prompt_tokens)} / ${num(r.completion_tokens)}</td><td><code>${esc(r.extractor_version || "")}</code></td><td class="q">${esc(r.error || "")}</td></tr>`),
    "Chưa có lượt chạy.");
}

// ---------- refresh loop ----------
async function refresh(force = false) {
  try {
    const s = await api("/api/status");
    renderStatus(s);
    if (state.tab === "overview") renderAlerts((await api("/api/quality")).alerts);
    if (state.tab === "quality") { const q = await api("/api/quality"); renderQuality(q); renderAlerts(q.alerts); }
    if (force) {
      if (state.tab === "answers") await loadAnswers();
      if (state.tab === "claims") await loadClaims();
      if (state.tab === "errors") await loadErrors();
      if (state.tab === "usage") await loadUsage();
      if (state.tab === "runs") await loadRuns();
    } else if (state.tab === "runs") await loadRuns();
  } catch (e) { toast(`Không tải được trạng thái: ${e.message}`, true); }
}
function loop() {
  const running = state.status && (state.status.worker.progress.running || state.status.worker.busy_elsewhere);
  setTimeout(async () => { await refresh(false); loop(); }, running ? 1500 : 5000);
}

// ---------- wiring ----------
$("btnRun").onclick = () => {
  const limit = parseInt($("runLimit").value, 10);
  act(() => api("/api/run", { method: "POST", body: { limit: Number.isFinite(limit) ? limit : null, rescan: $("rescan").checked } }), "Đã bắt đầu chạy.");
};
$("btnTrial").onclick = () => act(() => api("/api/run", { method: "POST", body: { limit: 5, rescan: $("rescan").checked } }), "Đã bắt đầu chạy thử 5 answer.");
$("btnStop").onclick = () => act(() => api("/api/stop", { method: "POST" }), "Sẽ dừng sau answer hiện tại.");
$("btnRetry").onclick = () => act(() => api("/api/retry-failed", { method: "POST" }), (r) => `Đã xếp lại ${r.requeued} answer lỗi${r.started ? " và bắt đầu chạy" : ""}.`);
$("btnStale").onclick = () => {
  if (!confirm("Xử lý lại các answer trích bằng bản prompt/logic cũ? Sẽ gọi LLM cho từng answer đó (có tốn chi phí).")) return;
  act(() => api("/api/reprocess", { method: "POST", body: { stale: true } }), (r) => `Đã xếp lại ${r.requeued} answer${r.started ? " và bắt đầu chạy" : ""}.`);
};
$("autoToggle").onchange = (e) => act(() => api("/api/auto", { method: "POST", body: { enabled: e.target.checked } }), e.target.checked ? "Đã bật tự động." : "Đã tắt tự động.");
$("aGo").onclick = () => { state.aOff = 0; loadAnswers(); };
$("cGo").onclick = () => { state.cOff = 0; loadClaims(); };

refresh(true); loop();
