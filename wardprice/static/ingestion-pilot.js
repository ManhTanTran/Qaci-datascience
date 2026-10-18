const API = "/api/v1/ingestion";
const labels = {
  SOURCE_PAGE_CONFIRMED: "Đã đối chiếu trang nguồn",
  SOURCE_PARTIAL: "Nguồn chưa đủ bằng chứng",
  SEARCH_SNIPPET_ONLY: "Chỉ có đoạn trích tìm kiếm",
  CATEGORY_ONLY: "Chỉ có trang danh mục",
  UNVERIFIED: "Chưa xác minh nguồn",
  WEB_SEARCH_UNAVAILABLE: "Không thực hiện tìm kiếm web",
  NEWLY_POSTED_LAST_24H: "Mới đăng trong 24 giờ",
  NEWLY_DISCOVERED: "Mới phát hiện",
  PREVIOUSLY_SEEN: "Đã gặp trước đó",
  UPDATED_LISTING: "Tin đã cập nhật",
  EXPIRED: "Đã hết hạn",
  UNKNOWN: "Chưa rõ",
  NEEDS_REVIEW: "Cần rà soát",
  VALID: "Hợp lệ cấu trúc",
  BLOCKED_SOURCE: "Nguồn đang bị chặn",
  SUCCEEDED: "Hoàn tất",
  SUCCEEDED_WITH_QUARANTINE: "Hoàn tất · có cách ly",
  APPLIED: "Đã nhập",
  APPLIED_WITH_QUARANTINE: "Đã nhập · có cách ly",
  PREVIEW_ONLY: "Chỉ xem trước",
};

function esc(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;");
}

function count(value) {
  return Number(value || 0).toLocaleString("vi-VN");
}

function dateTime(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("vi-VN", {
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

function statusLabel(value) {
  return labels[value] || String(value || "Chưa rõ").replaceAll("_", " ");
}

async function getJson(path) {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`Không đọc được pipeline (${response.status}).`);
  return response.json();
}

function renderRuns(runs = []) {
  const body = document.getElementById("runRows");
  body.innerHTML = runs.map((run) => `<tr>
    <td>${esc(dateTime(run.started_at))}</td><td>${esc(run.source_id)}</td>
    <td><span class="status-tag">${esc(statusLabel(run.status))}</span></td>
    <td>${count(run.received)}</td><td>${count(run.newly_posted + run.newly_discovered)}</td>
    <td>${count(run.quarantined)}</td></tr>`).join("");
  document.getElementById("emptyRuns").hidden = runs.length > 0;
}

function renderSources(sources = []) {
  const list = document.getElementById("sourceRows");
  list.innerHTML = sources.map((source) => {
    const ready = source.health === "READY";
    const reasons = (source.block_reasons || []).map(statusLabel).join(" · ");
    return `<div class="source-row">
      <div class="source-mark ${ready ? "ready" : "blocked"}" aria-hidden="true"></div>
      <div class="source-info"><strong>${esc(source.source_name)}</strong>
        <span>${esc(source.source_type)} · ${esc(source.permission_status)}</span>
        <small>${esc(reasons || "Đã khai báo phạm vi, quyền lưu và attribution")}</small></div>
      <span class="source-state ${ready ? "ready" : "blocked"}">${ready ? "Sẵn sàng" : "Chờ quyền"}</span>
    </div>`;
  }).join("");
  document.getElementById("sourceCount").textContent = `${count(sources.length)} nguồn`;
  document.getElementById("emptySources").hidden = sources.length > 0;
}

function renderListings(listings = []) {
  const body = document.getElementById("listingRows");
  body.innerHTML = listings.map((item) => {
    const link = item.source_url_type === "DIRECT_LISTING" && item.source_url
      ? `<a href="${esc(item.source_url)}" target="_blank" rel="noreferrer">${esc(item.title || "Mở tin")}</a>`
      : esc(item.title || "Chưa có tiêu đề");
    const price = item.price_vnd == null ? "—" : `${Math.round(item.price_vnd).toLocaleString("vi-VN")} ₫`;
    const area = item.area_m2 == null ? "—" : `${Number(item.area_m2).toLocaleString("vi-VN")} m²`;
    const type = item.property_type || "Chưa phân loại";
    return `<tr><td><strong>#${String(item.target_rank).padStart(2, "0")} · ${esc(item.original_ward)}</strong>
      <small>${esc(item.original_province)}</small></td><td>${link}
      <small>${esc(item.source_id || item.primary_source_id)} · ${esc(item.source_url_type)}</small></td>
      <td>${esc(type)}<small>${esc(item.transaction_type)}</small></td>
      <td>${esc(price)}<small>${esc(area)}${item.price_per_m2 ? ` · ${Math.round(item.price_per_m2).toLocaleString("vi-VN")} ₫/m²` : ""}</small></td>
      <td><span class="evidence-tag">${esc(statusLabel(item.evidence_status))}</span></td>
      <td>${esc(statusLabel(item.freshness_status))}${item.stats_eligible ? " · đủ điều kiện thống kê" : " · chưa tính thống kê"}</td></tr>`;
  }).join("");
  document.getElementById("candidateCount").textContent = `${count(listings.length)} dòng gần nhất`;
  document.getElementById("emptyListings").hidden = listings.length > 0;
}

function renderTargetCoverage(targets = []) {
  const body = document.getElementById("targetRows");
  body.innerHTML = targets.map((target) => {
    const goal = Number(target.daily_goal || 10);
    const today = Number(target.newly_posted_today || 0);
    const met = Boolean(target.goal_met);
    return `<tr>
      <td><strong>#${String(target.target_rank).padStart(2, "0")} · ${esc(target.ward)}</strong>
        <small>${esc(target.province)}</small></td>
      <td>${count(target.candidate_count)}</td>
      <td>${count(target.verified_count)}</td>
      <td>${count(today)}</td>
      <td><span class="goal-state ${met ? "met" : "waiting"}">${count(Math.min(today, goal))} / ${count(goal)} · ${met ? "đạt" : "còn " + count(target.goal_remaining)}</span></td>
    </tr>`;
  }).join("");
  const ready = targets.filter((target) => target.goal_met).length;
  document.getElementById("targetCoverageLabel").textContent = `${count(ready)} / ${count(targets.length)} đạt mục tiêu ngày`;
  document.getElementById("emptyTargets").hidden = targets.length > 0;
}

function renderCounts(containerId, emptyId, rows, key, valueLabel = "bản ghi") {
  const container = document.getElementById(containerId);
  container.innerHTML = rows.map((row) => `<div class="count-row"><span>${esc(statusLabel(row[key]))}</span>
    <strong>${count(row.count)} <small>${valueLabel}</small></strong></div>`).join("");
  document.getElementById(emptyId).hidden = rows.length > 0;
}

function renderQuarantine(rows = []) {
  const body = document.getElementById("quarantineRows");
  body.innerHTML = rows.map((row) => `<tr><td>${esc(dateTime(row.quarantined_at))}</td>
    <td>${esc(row.source_id)}</td><td>${count(row.row_index)}</td><td>${esc(statusLabel(row.reason))}</td></tr>`).join("");
  document.getElementById("emptyQuarantine").hidden = rows.length > 0;
}

function renderMonitoring(summary) {
  const totals = summary.daily_totals || {};
  document.getElementById("todayLabel").textContent = summary.run_date || "Hôm nay";
  document.getElementById("newPosted").textContent = count(totals.newly_posted);
  document.getElementById("newDiscovered").textContent = count(totals.newly_discovered);
  document.getElementById("verified").textContent = count(totals.verified);
  document.getElementById("coverage").textContent = `${count(summary.covered_targets)} / ${count(summary.target_count || 50)}`;
  const statusTitle = document.getElementById("statusTitle");
  const statusDetail = document.getElementById("statusDetail");
  if (summary.status === "NOT_INITIALIZED") {
    statusTitle.textContent = "Pilot DB chưa khởi tạo";
    statusDetail.textContent = "Chạy `python -m wardprice.ingestion_pilot init` để tạo kho pilot riêng.";
  } else {
    const ready = (summary.source_health || []).filter((source) => source.health === "READY").length;
    statusTitle.textContent = ready ? `${ready} nguồn đã qua cổng quyền` : "Chưa có nguồn đầu vào được cấp quyền";
    statusDetail.textContent = `${count(summary.candidate_count)} candidate trong pilot · ${count(summary.stats_eligible_count)} đủ điều kiện thống kê · không gửi request mạng.`;
  }
  renderRuns(summary.recent_runs || []);
  renderTargetCoverage(summary.target_coverage || []);
  renderSources(summary.source_health || []);
  renderCounts("evidenceRows", "emptyEvidence", summary.evidence_counts || [], "evidence_status");
  renderQuarantine(summary.recent_quarantine || []);
}

async function start() {
  try {
    const [summary, lookup] = await Promise.all([
      getJson(`${API}/monitoring`),
      getJson(`${API}/listings?limit=20`),
    ]);
    renderMonitoring(summary);
    renderListings(lookup.listings || []);
  } catch (error) {
    document.getElementById("statusTitle").textContent = "Không đọc được trạng thái pipeline";
    document.getElementById("statusDetail").textContent = error.message;
    document.getElementById("statusStrip").classList.add("error");
  }
}

start();
