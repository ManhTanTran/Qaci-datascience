const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const PROPERTY_LABELS = {
  DAT_O: "Đất ở",
  NHA_RIENG: "Nhà riêng",
  CHUNG_CU: "Chung cư",
};

let allTargets = [];
let activeMatches = [];
let activePropertyType = "";

function make(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

async function getJSON(path) {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Yêu cầu thất bại (${response.status})`);
  }
  return response.json();
}

function formatMoney(value) {
  return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 }).format(Number(value || 0));
}

function formatMillion(value) {
  return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 1 }).format(Number(value || 0) / 1_000_000);
}

function setMessage(node, message, isError = false) {
  node.textContent = message;
  node.hidden = !message;
  node.classList.toggle("is-error", isError);
}

function setLoading(node, loading) {
  node.setAttribute("aria-busy", String(loading));
  if (loading) {
    node.replaceChildren(make("p", "loading", "Đang tải dữ liệu từ SQLite…"));
  }
}

function displayFixtureText(value, fallback) {
  return String(value || "")
    .replace(/^\[DEMO\s*[-–·]\s*DỮ LIỆU GIẢ LẬP\]\s*/i, "")
    .replace(/DEMO-/gi, "MH-") || fallback;
}

function showView(name) {
  $$(".view").forEach((view) => {
    const visible = view.id === `${name}View`;
    view.hidden = !visible;
    view.classList.toggle("is-visible", visible);
  });
  $$(".nav-link").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.view === name);
  });
  if (name === "coverage") loadCoverage();
  if (name === "history") loadHistory();
}

function renderProvinceOptions() {
  const provinces = [...new Set(allTargets.map((target) => target.province))].sort((a, b) => a.localeCompare(b, "vi"));
  const select = $("#provinceFilter");
  select.replaceChildren(new Option("Chọn tỉnh / thành trước", ""));
  provinces.forEach((province) => select.add(new Option(province, province)));

  const contextProvince = $("#contextProvince");
  contextProvince.replaceChildren(new Option("Chọn tỉnh / thành", ""));
  provinces.forEach((province) => contextProvince.add(new Option(province, province)));
  renderContextWardOptions("");

  renderWardSuggestions("");

  const historyWard = $("#historyWard");
  historyWard.replaceChildren(...allTargets.map((target) => new Option(
    `#${String(target.target_rank).padStart(2, "0")} · ${target.ward_name} · ${target.province}`,
    String(target.target_rank),
  )));
}

function renderContextWardOptions(province) {
  const options = $("#contextWardOptions");
  const input = $("#contextWard");
  const matches = province ? allTargets.filter((target) => target.province === province) : [];
  options.replaceChildren(...matches.map((target) => {
    const option = document.createElement("option");
    option.value = target.ward_name;
    option.label = `#${String(target.target_rank).padStart(2, "0")} · ${target.district}`;
    return option;
  }));
  input.disabled = !province;
  input.placeholder = province ? `Nhập hoặc chọn phường/xã tại ${province}` : "Chọn tỉnh / thành trước…";
}

function renderWardSuggestions(province) {
  const wards = $("#wardOptions");
  const wardInput = $("#wardSearch");
  const provinceTargets = province ? allTargets.filter((target) => target.province === province) : [];
  wards.replaceChildren(...provinceTargets.map((target) => {
    const option = document.createElement("option");
    option.value = target.ward_name;
    option.label = `#${String(target.target_rank).padStart(2, "0")} · ${target.district}`;
    return option;
  }));
  wardInput.disabled = !province;
  wardInput.placeholder = province ? `Nhập hoặc chọn phường/xã tại ${province}` : "Chọn tỉnh / thành trước…";
}

function statCard(stat) {
  const highlighted = activePropertyType === stat.property_type;
  const card = make("article", `stat-card${highlighted ? " is-highlighted" : ""}`);
  const head = make("div", "stat-head");
  head.append(make("span", "stat-kind", PROPERTY_LABELS[stat.property_type] || stat.property_type));
  head.append(make("span", "pill pill-demo", "MINH HỌA"));
  card.append(head);
  card.append(make("p", "stat-value", formatMillion(stat.median_price_per_m2)));
  card.append(make("p", "stat-unit", "triệu đồng / m² · trung vị"));
  const meta = make("div", "stat-meta");
  const mean = make("span", "", "Trung bình");
  mean.append(make("strong", "", `${formatMillion(stat.mean_price_per_m2)} triệu/m²`));
  const count = make("span", "", "Mẫu tin");
  count.append(make("strong", "", `${stat.sample_count ?? stat.listing_count} tin`));
  meta.append(mean, count);
  card.append(meta);
  return card;
}

function listingCard(listing) {
  const card = make("article", "listing-card");
  const top = make("div", "listing-top");
  top.append(make("p", "listing-title", displayFixtureText(listing.title, "Tin rao minh họa")));
  top.append(make("span", "pill pill-demo", "MINH HỌA · CHƯA XÁC MINH"));
  card.append(top);
  card.append(make("p", "listing-address", displayFixtureText(listing.address, "Địa chỉ minh họa thuộc địa bàn này").replace(/^ĐỊA CHỈ GIẢ LẬP/i, "Địa chỉ minh họa")));
  const data = make("div", "listing-data");
  const price = make("div");
  price.append(make("span", "", "Giá · "), make("strong", "", `${formatMoney(listing.price_vnd)} ₫`));
  const area = make("div");
  area.append(make("span", "", "Diện tích · "), make("strong", "", `${Number(listing.area_m2).toLocaleString("vi-VN")} m²`));
  const unit = make("div");
  unit.append(make("span", "", "Giá/m² · "), make("strong", "", `${formatMoney(listing.price_per_m2)} ₫`));
  data.append(price, area, unit);
  card.append(data);
  return card;
}

function renderTarget(target) {
  const root = $("#lookupResults");
  root.replaceChildren();
  const heading = make("div", "result-heading");
  const title = make("div");
  title.append(make("h2", "", `#${String(target.target_rank).padStart(2, "0")} · ${target.ward_name}`));
  title.append(make("p", "result-location", `${target.district} · ${target.province} · Mã ${target.ward_code}`));
  heading.append(title, make("span", "pill pill-demo", "MỌI GIÁ LÀ MINH HỌA"));
  root.append(heading);

  if (!target.statistics?.length) {
    const empty = make("div", "empty-state");
    empty.append(make("strong", "", "Chưa có dữ liệu cho bộ lọc này"));
    empty.append(make("span", "", "Địa bàn đã có trong Top 50, nhưng không có tin thuộc loại bất động sản bạn chọn."));
    root.append(empty);
    return;
  }

  const stats = make("div", "stats-grid");
  target.statistics.forEach((item) => stats.append(statCard(item)));
  root.append(stats);

  const listSection = make("section", "listings-section");
  const listHeading = make("div", "result-heading");
  listHeading.append(make("h2", "", `Tin minh họa · ${target.listings.length} tin`));
  listHeading.append(make("p", "", "Không có URL nguồn · không phải tin thị trường thật"));
  listSection.append(listHeading);
  if (target.listings.length) {
    const grid = make("div", "listings-grid");
    target.listings.forEach((listing) => grid.append(listingCard(listing)));
    listSection.append(grid);
  } else {
    listSection.append(make("div", "empty-state", "Không có tin khớp bộ lọc."));
  }
  root.append(listSection);
}

function normalizeWardLabel(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D")
    .toLocaleLowerCase("vi")
    .replace(/^(phuong|xa|thi tran)\s+/, "")
    .replace(/\s+/g, " ")
    .trim();
}

function contextStatCard(stat) {
  const card = make("article", "context-stat");
  const head = make("div", "context-stat-head");
  head.append(make("span", "context-stat-kind", PROPERTY_LABELS[stat.property_type] || stat.property_type));
  head.append(make("span", "context-stat-mark", "R1"));
  card.append(head);
  card.append(make("p", "context-stat-value", formatMillion(stat.median_price_per_m2)));
  card.append(make("p", "context-stat-unit", "triệu đồng / m² · giá rao trung vị"));
  const details = make("div", "context-stat-details");
  const mean = make("span", "", "Trung bình");
  mean.append(make("strong", "", `${formatMillion(stat.mean_price_per_m2)} triệu/m²`));
  const count = make("span", "", "Mẫu tin");
  count.append(make("strong", "", `${stat.sample_count ?? stat.listing_count} tin`));
  details.append(mean, count);
  card.append(details);
  return card;
}

function renderAIContext(target) {
  const root = $("#contextResults");
  root.replaceChildren();
  if (!target.statistics?.length) {
    const empty = make("div", "context-empty");
    empty.append(make("span", "empty-mark", "R1"));
    const copy = make("div");
    copy.append(make("strong", "", "Chưa có số liệu cho địa bàn và nhóm giá này"));
    copy.append(make("p", "", "Không tạo tham chiếu để AI tránh suy đoán từ dữ liệu còn thiếu."));
    empty.append(copy);
    root.append(empty);
    return;
  }

  const latestDate = target.statistics.map((item) => item.last_updated).filter(Boolean).sort().at(-1) || "Chưa có ngày cập nhật";
  const stats = target.statistics.map((item) => ({
    property_type: item.property_type,
    listing_count: Number(item.listing_count),
    sample_count: Number(item.sample_count ?? item.listing_count),
    mean_price_per_m2: Number(item.mean_price_per_m2),
    median_price_per_m2: Number(item.median_price_per_m2),
    data_quality: item.data_quality,
  }));
  const reference = {
    reference_id: "R1",
    source_store: "WardPriceDaily",
    administrative_area: `${target.ward_name}, ${target.province}`,
    district_context: target.district || null,
    as_of: latestDate,
    statistics: stats,
    use: "market_context_only",
    limitation: "Area-level asking prices do not describe an individual's assets or repayment capacity.",
  };

  const layout = make("div", "context-layout");
  const dataPanel = make("section", "panel context-data-panel");
  const heading = make("div", "context-panel-heading");
  const headingCopy = make("div");
  headingCopy.append(make("p", "eyebrow", "THỐNG KÊ ĐỊA BÀN"));
  headingCopy.append(make("h2", "", target.ward_name));
  headingCopy.append(make("p", "context-location", `${target.district} · ${target.province} · Mã ${target.ward_code}`));
  heading.append(headingCopy, make("span", "pill pill-demo", "DỮ LIỆU MINH HỌA"));
  dataPanel.append(heading);

  const statsGrid = make("div", "context-stats-grid");
  target.statistics.forEach((stat) => statsGrid.append(contextStatCard(stat)));
  dataPanel.append(statsGrid);
  const provenance = make("div", "context-provenance");
  provenance.append(make("span", "provenance-dot", ""));
  provenance.append(make("span", "", `Kho SQLite cục bộ · ${target.statistics.reduce((sum, item) => sum + Number(item.listing_count || 0), 0)} tin · cập nhật ${latestDate}`));
  dataPanel.append(provenance);

  const referencePanel = make("aside", "reference-card");
  const refHead = make("div", "reference-head");
  const refId = make("span", "reference-id", "R1");
  const refStatus = make("span", "reference-status", "BẢN XEM TRƯỚC");
  refHead.append(refId, refStatus);
  referencePanel.append(refHead);
  referencePanel.append(make("p", "reference-kicker", "NGỮ CẢNH ĐỊA BÀN"));
  const responseCopy = make("p", "reference-summary");
  const summaryLines = target.statistics.map((item) => `${PROPERTY_LABELS[item.property_type] || item.property_type}: trung vị ${formatMillion(item.median_price_per_m2)} triệu đồng/m² từ ${item.sample_count ?? item.listing_count} tin`);
  responseCopy.textContent = `Tại ${target.ward_name}, ${target.province}, dữ liệu hiện có ghi nhận ${summaryLines.join("; ")}. Đây là thông tin tham khảo về giá rao trong khu vực.`;
  referencePanel.append(responseCopy);

  const details = make("details", "reference-details");
  const summary = make("summary", "", "Xem dữ liệu được ghim vào R1");
  const payload = make("pre", "reference-payload", JSON.stringify(reference, null, 2));
  details.append(summary, payload);
  referencePanel.append(details);

  const guardrail = make("div", "reference-guardrail");
  guardrail.append(make("strong", "", "Phạm vi sử dụng"));
  guardrail.append(make("p", "", "Chỉ bổ sung bối cảnh giá rao cấp khu vực. Không suy ra tài sản, thu nhập, tiền thuê nhà hay khả năng trả nợ của người vay."));
  referencePanel.append(guardrail);
  referencePanel.append(make("p", "reference-footer", "Chưa gửi dữ liệu sang AI hoặc luồng đánh giá khoản vay."));

  layout.append(dataPanel, referencePanel);
  root.append(layout);
}

async function previewAIContext() {
  const form = $("#contextForm");
  const button = form.querySelector("button[type=submit]");
  const root = $("#contextResults");
  const message = $("#contextMessage");
  const province = $("#contextProvince").value;
  const query = $("#contextWard").value.trim();
  const propertyType = $("#contextType").value;
  setMessage(message, "");
  if (!province || !query) {
    root.replaceChildren();
    setMessage(message, "Chọn tỉnh/thành và một phường/xã trong danh sách để tạo tham chiếu.");
    return;
  }

  root.setAttribute("aria-busy", "true");
  root.replaceChildren(make("p", "loading", "Đang đối chiếu địa bàn và đọc thống kê cục bộ…"));
  button.disabled = true;
  try {
    const params = new URLSearchParams({ q: query });
    if (propertyType) params.set("property_type", propertyType);
    const result = await getJSON(`/api/v1/demo/lookup?${params}`);
    const requestedName = normalizeWardLabel(query);
    const target = result.targets.find((item) => item.province === province && normalizeWardLabel(item.ward_name) === requestedName);
    if (!target) {
      root.replaceChildren();
      const messageText = result.targets.length
        ? `Không tìm thấy phường/xã khớp chính xác trong ${province}. Chọn một gợi ý đầy đủ từ danh sách.`
        : `Chưa có địa bàn này trong danh sách tra cứu tại ${province}.`;
      setMessage(message, messageText);
      return;
    }
    renderAIContext(target);
  } catch (error) {
    root.replaceChildren();
    setMessage(message, `Không tạo được bản xem trước: ${error.message}`, true);
  } finally {
    root.setAttribute("aria-busy", "false");
    button.disabled = false;
  }
}

async function searchListings() {
  const root = $("#lookupResults");
  const message = $("#lookupMessage");
  const query = $("#wardSearch").value.trim();
  const type = $("#propertyType").value;
  const province = $("#provinceFilter").value;
  activePropertyType = type;
  setMessage(message, "");
  if (!province) {
    root.replaceChildren();
    setMessage(message, "Hãy chọn tỉnh/thành trước; gợi ý địa bàn sẽ được giới hạn trong tỉnh/thành đó.");
    return;
  }
  if (!query) {
    root.replaceChildren();
    setMessage(message, "Chọn hoặc nhập một phường/xã trong danh sách gợi ý để tra cứu.");
    return;
  }
  setLoading(root, true);
  $("#searchForm button[type=submit]").disabled = true;
  try {
    const params = new URLSearchParams({ q: query });
    if (type) params.set("property_type", type);
    const result = await getJSON(`/api/v1/demo/lookup?${params}`);
    activeMatches = result.targets.filter((target) => !province || target.province === province);
    const pickerWrap = $("#targetPickerWrap");
    const picker = $("#targetPicker");
    if (!activeMatches.length) {
      pickerWrap.hidden = true;
      root.replaceChildren();
      const empty = make("div", "empty-state");
      if (result.targets.length && province) {
        empty.append(make("strong", "", "Địa bàn không thuộc tỉnh/thành đang chọn"));
        empty.append(make("span", "", `Chọn một địa bàn trong ${province}, hoặc đổi tỉnh/thành để tìm địa bàn này.`));
      } else if (result.status === "NOT_IN_TOP50" || result.status === "NOT_FOUND") {
        empty.append(make("strong", "", "Chưa có dữ liệu tra cứu cho địa bàn này"));
        empty.append(make("span", "", `Danh sách hiện có 50 phường xã thuộc Top 50 tại ${province}.`));
      } else {
        empty.append(make("strong", "", "Không có dữ liệu khớp bộ lọc"));
      }
      root.append(empty);
      return;
    }
    if (activeMatches.length > 1) {
      pickerWrap.hidden = false;
      picker.replaceChildren(...activeMatches.map((target) => new Option(
        `#${String(target.target_rank).padStart(2, "0")} · ${target.ward_name} · ${target.district}, ${target.province}`,
        String(target.target_rank),
      )));
    } else {
      pickerWrap.hidden = true;
    }
    renderTarget(activeMatches[0]);
  } catch (error) {
    root.replaceChildren();
    setMessage(message, `Không tải được dữ liệu: ${error.message}`, true);
  } finally {
    root.setAttribute("aria-busy", "false");
    $("#searchForm button[type=submit]").disabled = false;
  }
}

function metricCard(label, value, caption) {
  const card = make("article", "metric-card");
  card.append(make("div", "metric-label", label));
  card.append(make("p", "metric-value", value));
  card.append(make("p", "metric-caption", caption));
  return card;
}

async function loadCoverage() {
  const metrics = $("#coverageMetrics");
  if (metrics.dataset.loaded === "true") return;
  metrics.replaceChildren(make("p", "loading", "Đang đọc độ phủ…"));
  try {
    const [coverage, wardResult] = await Promise.all([
      getJSON("/api/v1/demo/coverage"),
      getJSON("/api/v1/demo/wards"),
    ]);
    metrics.dataset.loaded = "true";
    metrics.replaceChildren(
      metricCard("Địa bàn trong danh sách", `${coverage.target_count} / 50`, "Danh sách mục tiêu Top 50"),
      metricCard("Địa bàn có tin", `${coverage.wards_with_data} / 50`, "Có ít nhất một tin minh họa"),
      metricCard("Tin đang theo dõi", `${coverage.listings} / ${coverage.listing_cap}`, "Giới hạn theo dõi hiện tại"),
      metricCard("Lịch sử quan sát", String(coverage.daily_observations), "Bản ghi observation trong SQLite"),
    );
    const distribution = $("#typeDistribution");
    distribution.replaceChildren();
    const values = Object.entries(coverage.property_type_counts || {});
    const max = Math.max(1, ...values.map(([, count]) => count));
    values.forEach(([type, count]) => {
      const row = make("div", "distribution-row");
      row.append(make("span", "", PROPERTY_LABELS[type] || type));
      const track = make("div", "distribution-track");
      const fill = make("div", "distribution-fill");
      fill.style.width = `${(count / max) * 100}%`;
      track.append(fill);
      row.append(track, make("strong", "", `${count} tin`));
      distribution.append(row);
    });
    const tbody = $("#wardTable");
    tbody.replaceChildren();
    wardResult.targets.forEach((target) => {
      const row = document.createElement("tr");
      [String(target.target_rank).padStart(2, "0"), target.ward_name, target.district, target.province, String(target.listing_count ?? "—")].forEach((value) => row.append(make("td", "", value)));
      tbody.append(row);
    });
    $("#wardCoverageCount").textContent = `${wardResult.targets.length} địa bàn · network_called=${coverage.network_called}`;
  } catch (error) {
    metrics.replaceChildren(make("p", "inline-message is-error", `Không tải được độ phủ: ${error.message}`));
  }
}

async function loadHistory() {
  const rank = $("#historyWard").value || "1";
  const type = $("#historyType").value;
  const params = new URLSearchParams({ target_rank: rank });
  if (type) params.set("property_type", type);
  const table = $("#historyTable");
  const message = $("#historyMessage");
  table.replaceChildren();
  setMessage(message, "Đang đọc lịch sử quan sát…");
  try {
    const result = await getJSON(`/api/v1/demo/history?${params}`);
    setMessage(message, result.observations.length ? `${result.observations.length} quan sát · dữ liệu minh họa, chưa có nguồn thị trường để đối chiếu.` : "Chưa có quan sát cho địa bàn và bộ lọc này.");
    result.observations.forEach((item) => {
      const row = document.createElement("tr");
      [item.observation_date, PROPERTY_LABELS[item.property_type] || item.property_type, item.title, `${formatMoney(item.price_vnd)} ₫`, `${Number(item.area_m2).toLocaleString("vi-VN")} m²`, `${formatMoney(item.price_per_m2)} ₫`, item.evidence_status].forEach((value) => row.append(make("td", "", value)));
      table.append(row);
    });
  } catch (error) {
    setMessage(message, `Không tải được lịch sử: ${error.message}`, true);
  }
}

async function initialize() {
  $$('[data-view]').forEach((button) => button.addEventListener("click", () => showView(button.dataset.view)));
  $("#searchForm").addEventListener("submit", (event) => { event.preventDefault(); searchListings(); });
  $("#contextForm").addEventListener("submit", (event) => { event.preventDefault(); previewAIContext(); });
  $("#contextProvince").addEventListener("change", () => {
    renderContextWardOptions($("#contextProvince").value);
    $("#contextWard").value = "";
    $("#contextResults").replaceChildren();
    setMessage($("#contextMessage"), "Chọn một phường/xã trong tỉnh/thành đã chọn.");
  });
  $("#contextWard").addEventListener("input", () => {
    $("#contextResults").replaceChildren();
    setMessage($("#contextMessage"), "");
  });
  $$(".filter-chip").forEach((button) => button.addEventListener("click", () => {
    $("#propertyType").value = button.dataset.type;
    $$(".filter-chip").forEach((chip) => chip.classList.toggle("is-active", chip === button));
    searchListings();
  }));
  $("#propertyType").addEventListener("change", () => {
    $$(".filter-chip").forEach((chip) => chip.classList.toggle("is-active", chip.dataset.type === $("#propertyType").value));
  });
  $("#provinceFilter").addEventListener("change", () => {
    const province = $("#provinceFilter").value;
    renderWardSuggestions(province);
    // A locality is scoped to the province selected when it was chosen.
    // Clear it on every province change so a stale value cannot cross regions.
    $("#wardSearch").value = "";
    $("#lookupResults").replaceChildren();
    $("#targetPickerWrap").hidden = true;
    $("#targetPicker").replaceChildren();
    setMessage($("#lookupMessage"), province
      ? `Gợi ý đã lọc theo ${province}. Chọn một phường/xã rồi nhấn “Tra cứu giá”.`
      : "Chọn tỉnh/thành trước; gợi ý địa bàn sẽ được giới hạn trong tỉnh/thành đó.");
  });
  $("#targetPicker").addEventListener("change", () => {
    const target = activeMatches.find((item) => String(item.target_rank) === $("#targetPicker").value);
    if (target) renderTarget(target);
  });
  $("#loadHistory").addEventListener("click", loadHistory);
  $("#historyWard").addEventListener("change", loadHistory);
  $("#historyType").addEventListener("change", loadHistory);

  try {
    const health = await getJSON("/api/v1/health");
    const banner = $("#modeBanner");
    if (!health.demo_mode) {
      banner.classList.add("is-error");
      banner.querySelector("strong").textContent = "Dữ liệu minh họa chưa bật";
      $("#modeDescription").textContent = "Khởi chạy chế độ dữ liệu minh họa để xem bộ 500 tin tham khảo.";
      setMessage($("#lookupMessage"), "Trang đang kết nối với kho dữ liệu chính. Hãy khởi chạy API ở chế độ dữ liệu minh họa để xem bộ thông tin tham khảo.", true);
      return;
    }
    banner.querySelector("strong").textContent = "DỮ LIỆU MINH HỌA";
    $("#modeDescription").textContent = "Giá và tin rao chưa được xác minh từ thị trường; không dùng để định giá giao dịch.";
    const result = await getJSON("/api/v1/demo/wards");
    allTargets = result.targets;
    renderProvinceOptions();
    setMessage($("#lookupMessage"), "Chọn tỉnh/thành trước; gợi ý địa bàn sẽ được giới hạn trong tỉnh/thành đó.");
    await loadCoverage();
    const pageParams = new URLSearchParams(window.location.search);
    if (pageParams.get("view") === "aiContext") {
      showView("aiContext");
      const rank = Number(pageParams.get("rank"));
      const sampleTarget = allTargets.find((target) => target.target_rank === rank);
      if (sampleTarget) {
        $("#contextProvince").value = sampleTarget.province;
        renderContextWardOptions(sampleTarget.province);
        $("#contextWard").value = sampleTarget.ward_name;
        await previewAIContext();
      }
    }
  } catch (error) {
    $("#modeBanner").classList.add("is-error");
    $("#modeBanner").querySelector("strong").textContent = "Không kết nối được dữ liệu";
    $("#modeDescription").textContent = error.message;
    setMessage($("#lookupMessage"), "Kiểm tra API cục bộ rồi tải lại trang.", true);
  }
}

document.addEventListener("DOMContentLoaded", initialize);
