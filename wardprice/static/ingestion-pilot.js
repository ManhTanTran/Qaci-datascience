const API = "/api/v1/ingestion";
const COLLECTION_API = "/api/v1/collection/province-search";
const TOP50_COLLECTION_API = "/api/v1/collection/top50-search";
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

const collectionReasons = {
  GLOBAL_LIVE_DISABLED: "Cổng thu thập live đang tắt",
  SOURCE_DISABLED: "Nguồn đang tắt",
  PERMISSION_NOT_APPROVED: "Chưa duyệt quyền thu thập",
  PERMISSION_REFERENCE_MISSING: "Chưa ghi căn cứ cho phép",
  SEARCH_TEMPLATE_MISSING: "Chưa cấu hình trang tìm kiếm",
  DIRECT_LISTING_PATTERN_MISSING: "Chưa cấu hình nhận diện tin riêng",
  SOURCE_COOLDOWN_RECORDED: "Nguồn đang tạm nghỉ theo giới hạn",
  DATABASE_REGISTRY_NOT_SYNCED: "Cấu hình nguồn và SQLite chưa khớp",
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

function renderCollectionSources(sources = []) {
  const container = document.getElementById("collectionSourceCards");
  container.innerHTML = sources.map((source) => {
    const isReady = source.status === "READY";
    const isConfigured = source.status === "CONFIGURED";
    const state = isReady ? "SẴN SÀNG" : isConfigured ? "ĐÃ CẤU HÌNH" : "ĐANG KHÓA";
    const stateClass = isReady ? "is-ready" : isConfigured ? "is-configured" : "is-blocked";
    const detail = isReady
      ? "Qua cổng quyền và registry SQLite"
      : isConfigured
        ? "Qua cổng cấu hình; chờ kiểm tra SQLite"
        : (source.reasons || []).map((reason) => collectionReasons[reason] || statusLabel(reason)).join(" · ") || "Chưa sẵn sàng";
    return `<article class="collection-source-card ${stateClass}">
      <header><strong>${esc(source.display_name || source.source_id)}</strong><span>${state}</span></header>
      <p>${esc(detail)}</p>
    </article>`;
  }).join("");
}

function renderCollectionResponse(result, { readiness = false } = {}) {
  const status = document.getElementById("collectionRunStatus");
  const sourceCards = document.getElementById("collectionSourceCards");
  const panel = document.getElementById("collectionRunResults");
  renderCollectionSources(result.sources || []);
  if (readiness) {
    const targetCount = count(result.target_count);
    status.textContent = result.target_count
      ? result.configured_source_count
        ? `Có ${targetCount} địa bàn Top 50 và ${count(result.configured_source_count)} nguồn qua cổng cấu hình. Chưa gửi request; registry SQLite sẽ được kiểm tra khi bạn bấm thu thập.`
        : `Có ${targetCount} địa bàn Top 50, nhưng chưa có nguồn nào qua cổng cấu hình. Nút thu thập sẽ chỉ hiện lý do bị khóa; chưa gửi request.`
      : "Tỉnh/thành này chưa có địa bàn trong Top 50.";
    panel.hidden = true;
    panel.replaceChildren();
    return;
  }

  const message = result.message || (result.status === "COMPLETED"
    ? "Đã hoàn tất lượt thu thập."
    : result.status === "PARTIAL"
      ? "Lượt thu thập kết thúc một phần; xem kết quả theo nguồn."
      : result.status || "Đã nhận phản hồi.");
  status.textContent = result.selection_mode === "ALL_TOP50"
    ? `Phạm vi toàn bộ Top 50 (${count(result.target_count)} địa bàn). ${message}`
    : message;
  const sourceRows = (result.source_results || []).map((source) => `<tr>
    <td>${esc(source.display_name || source.source_id)}</td><td>${count(source.targets_tried)}</td>
    <td>${count(source.requests_made)}</td><td>${count(source.links_found)}</td>
    <td>${count(source.candidates_found)}</td><td>${esc(source.statuses || "—")}</td></tr>`).join("");
  const listingRows = (result.candidates || []).map((item) => `<tr>
    <td>${esc(item.source_name)}</td><td>${esc(item.original_ward)} · ${esc(item.original_district)}</td>
    <td>${esc(item.property_type || "Chưa phân loại")}</td>
    <td>${item.price_vnd == null ? "—" : `${Math.round(item.price_vnd).toLocaleString("vi-VN")} ₫`}</td>
    <td>${item.area_m2 == null ? "—" : `${Number(item.area_m2).toLocaleString("vi-VN")} m²`}</td>
    <td>${esc(statusLabel(item.evidence_status))} · ${esc(statusLabel(item.validity_status))}</td></tr>`).join("");
  if (!result.run_id && !sourceRows && !listingRows) {
    panel.hidden = true;
    panel.replaceChildren();
    return;
  }
  panel.innerHTML = `<section class="metrics" aria-label="Kết quả lượt thu thập">
      <article class="metric"><span>Request đã gửi</span><strong>${count(result.request_count)}</strong><small>Tối đa 20 trong một lượt</small></article>
      <article class="metric"><span>Liên kết tin</span><strong>${count(result.link_count)}</strong><small>Phát hiện từ nguồn</small></article>
      <article class="metric"><span>Candidate</span><strong>${count(result.candidate_count)}</strong><small>Lưu trong kho riêng</small></article>
      <article class="metric"><span>Đã xác minh</span><strong>${count(result.verified_count)}</strong><small>Không tự nhập hiện hành</small></article>
    </section>
    ${sourceRows ? `<h3>Kết quả theo nguồn</h3><div class="table-wrap"><table><thead><tr><th>Nguồn</th><th>Địa bàn</th><th>Request</th><th>Liên kết</th><th>Candidate</th><th>Trạng thái</th></tr></thead><tbody>${sourceRows}</tbody></table></div>` : ""}
    ${listingRows ? `<h3>Thông tin candidate thu được</h3><div class="table-wrap"><table><thead><tr><th>Nguồn</th><th>Địa bàn</th><th>Loại</th><th>Giá rao</th><th>Diện tích</th><th>Bằng chứng</th></tr></thead><tbody>${listingRows}</tbody></table></div>` : ""}
    <p class="collection-run-footnote">Mã lượt: ${esc(result.run_id || "—")} · network_attempted=${Boolean(result.network_attempted)} · production_database_written=${Boolean(result.production_database_written)}</p>`;
  panel.hidden = false;
  sourceCards.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

async function refreshCollectionReadiness(province) {
  const button = document.getElementById("collectionRunButton");
  const scope = document.getElementById("collectionProvinceScope");
  const status = document.getElementById("collectionRunStatus");
  const panel = document.getElementById("collectionRunResults");
  button.disabled = !province;
  panel.hidden = true;
  panel.replaceChildren();
  if (!province) {
    scope.textContent = "Chọn tỉnh/thành để xem phạm vi địa bàn Top 50.";
    status.textContent = "Có thể chạy toàn bộ Top 50 hoặc chọn riêng một tỉnh.";
    return;
  }
  scope.textContent = `Đang đọc phạm vi Top 50 tại ${province}…`;
  status.textContent = "Đang đọc cấu hình cục bộ; chưa gửi request ra website.";
  try {
    const query = new URLSearchParams({ province });
    const result = await getJson(`${COLLECTION_API}/readiness?${query}`);
    scope.textContent = `Phạm vi lượt này: ${count(result.target_count)} địa bàn Top 50 tại ${province}.`;
    renderCollectionResponse(result, { readiness: true });
  } catch (error) {
    status.textContent = error.message;
  }
}

async function refreshTop50Readiness() {
  const scope = document.getElementById("collectionAllTop50Scope");
  try {
    const result = await getJson(`${TOP50_COLLECTION_API}/readiness`);
    const provinceCount = new Set((result.targets || []).map((target) => target.province).filter(Boolean)).size;
    scope.textContent = `Phạm vi gồm ${count(result.target_count)} địa bàn Top 50 thuộc ${count(provinceCount)} tỉnh/thành. Mỗi lượt tối đa 20 request nên có thể cần nhiều lượt để rà đủ địa bàn.`;
    renderCollectionSources(result.sources || []);
    if (!document.getElementById("collectionProvinceSelect").value) {
      document.getElementById("collectionRunStatus").textContent = result.configured_source_count
        ? `Có ${count(result.configured_source_count)} nguồn qua cổng cấu hình. Chưa gửi request.`
        : "Chưa có nguồn nào qua cổng cấu hình; nút thu thập sẽ dừng trước khi gửi request ra website.";
    }
  } catch (error) {
    scope.textContent = error.message;
  }
}

async function submitCollectionRun(endpoint, { province = null, button, mode }) {
  const provinceButton = document.getElementById("collectionRunButton");
  const allButton = document.getElementById("collectionAllTop50Button");
  const select = document.getElementById("collectionProvinceSelect");
  if (mode === "PROVINCE" && !province) return;
  provinceButton.disabled = true;
  allButton.disabled = true;
  button.textContent = "Đang kiểm tra và thu thập…";
  document.getElementById("collectionRunStatus").textContent =
    "Đang kiểm tra cổng nguồn. Nếu cấu hình chưa đủ, lượt sẽ dừng trước khi gửi request.";
  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ province }),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.detail || `Không chạy được lượt thu thập (${response.status}).`);
    renderCollectionResponse(result);
  } catch (error) {
    document.getElementById("collectionRunStatus").textContent = error.message;
  } finally {
    provinceButton.disabled = !select.value;
    allButton.disabled = false;
    provinceButton.textContent = "Thu thập tỉnh này trên 4 nguồn";
    allButton.textContent = "Thu thập toàn bộ Top 50";
  }
}

async function runProvinceCollection() {
  const province = document.getElementById("collectionProvinceSelect").value;
  return submitCollectionRun(COLLECTION_API, {
    province,
    button: document.getElementById("collectionRunButton"),
    mode: "PROVINCE",
  });
}

async function runAllTop50Collection() {
  return submitCollectionRun(TOP50_COLLECTION_API, {
    button: document.getElementById("collectionAllTop50Button"),
    mode: "ALL_TOP50",
  });
}

async function loadCollectionProvinces() {
  const select = document.getElementById("collectionProvinceSelect");
  try {
    const response = await getJson("/api/v1/research/historical/targets");
    const provinces = [...new Set((response.targets || []).map((target) => target.original_province).filter(Boolean))]
      .sort((left, right) => left.localeCompare(right, "vi"));
    select.replaceChildren(new Option("Chọn tỉnh / thành", ""));
    for (const province of provinces) select.add(new Option(province, province));
    const params = new URLSearchParams(window.location.search);
    if (provinces.includes(params.get("province"))) select.value = params.get("province");
    select.addEventListener("change", () => {
      window.history.replaceState({}, "", select.value ? `?province=${encodeURIComponent(select.value)}` : window.location.pathname);
      refreshCollectionReadiness(select.value);
    });
    document.getElementById("collectionRunButton").addEventListener("click", runProvinceCollection);
    document.getElementById("collectionAllTop50Button").addEventListener("click", runAllTop50Collection);
    await refreshTop50Readiness();
    await refreshCollectionReadiness(select.value);
  } catch (error) {
    select.replaceChildren(new Option("Không tải được danh sách", ""));
    document.getElementById("collectionRunStatus").textContent = error.message;
  }
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
  await loadCollectionProvinces();
}

start();
