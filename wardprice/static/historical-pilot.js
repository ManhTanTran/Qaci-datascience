const api = "/api/v1/research/historical";
const propertyLabels = {
  DAT_O: "Đất ở",
  NHA_RIENG: "Nhà riêng",
  CHUNG_CU: "Chung cư",
};
let allTargets = [];
let datasetOverview = null;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatCount(value) {
  return Number(value || 0).toLocaleString("vi-VN");
}

function formatMoney(value) {
  if (value == null || !Number.isFinite(Number(value))) return "—";
  return `${Math.round(Number(value)).toLocaleString("vi-VN")} ₫`;
}

function formatMillions(value) {
  if (value == null || !Number.isFinite(Number(value))) return "—";
  return `${(Number(value) / 1_000_000).toLocaleString("vi-VN", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })} tr`;
}

function formatDate(value) {
  if (!value) return "Không rõ";
  const date = new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" });
}

function qualityInfo(level) {
  const labels = {
    INSUFFICIENT_SAMPLE: "Chưa đủ mẫu (n < 5)",
    LOW_CONFIDENCE: "Mẫu nhỏ (5–9 tin)",
    DESCRIPTIVE_SAMPLE: "Mẫu mô tả (n ≥ 10)",
  };
  const descriptions = {
    INSUFFICIENT_SAMPLE: "Cỡ mẫu quá nhỏ để diễn giải ổn định.",
    LOW_CONFIDENCE: "Chỉ mô tả mẫu này; độ ổn định còn thấp.",
    DESCRIPTIVE_SAMPLE: "Đủ cỡ mẫu để mô tả; không chứng minh tính đại diện.",
  };
  return {
    label: labels[level] || "Chưa đánh giá cỡ mẫu",
    description: descriptions[level] || "Không suy ra tính đại diện từ cỡ mẫu.",
  };
}

async function getJson(path) {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Không thể tải dữ liệu (${response.status})`);
  }
  return response.json();
}

function showError(message) {
  const element = document.getElementById("pageMessage");
  element.textContent = message;
  element.hidden = false;
}

function metric(label, value, note) {
  return `<article class="historical-metric"><span class="historical-metric-label">${escapeHtml(label)}</span><p class="historical-metric-value">${escapeHtml(value)}</p><p class="historical-metric-note">${escapeHtml(note)}</p></article>`;
}

function renderOverview(overview) {
  const coverage = `${formatCount(overview.covered_targets)} / 50`;
  const period = overview.first_published_date && overview.last_published_date
    ? `${formatDate(overview.first_published_date)} — ${formatDate(overview.last_published_date)}`
    : "Chưa có ngày đăng hợp lệ";
  const classes = overview.deal_classification_counts || {};
  const classificationSummary = `${formatCount(classes.SALE_CONFIRMED_BY_TEXT)} bán · ${formatCount(classes.RENT_CONFIRMED_BY_TEXT)} thuê · ${formatCount((classes.AMBIGUOUS || 0) + (classes.CONFLICT || 0))} cần phân loại`;
  const outsideTop50 = overview.quality_audit?.outside_top50_rows;
  document.getElementById("overviewMetrics").innerHTML = [
    metric("Dòng ngoài Top 50", outsideTop50 == null ? "—" : formatCount(outsideTop50), `Trong mẫu ${formatCount(overview.source_rows_processed)} dòng · không khớp danh sách mục tiêu`),
    metric("Ứng viên trong pilot", formatCount(overview.candidate_count), "Lưu tại SQLite lịch sử riêng"),
    metric("Đủ điều kiện thống kê", formatCount(overview.statistics_eligible_count), "Chỉ tin bán đã phân loại và loại BĐS ánh xạ rõ"),
    metric("Địa bàn có ứng viên", coverage, "Đối chiếu theo tỉnh, quận/huyện cũ và phường/xã"),
    metric("Phân loại tiêu đề", classificationSummary, "Luật từ khóa; chưa có nhãn đối chiếu thủ công"),
    metric("Khoảng ngày đăng", period, "Thời gian ghi trong dataset lịch sử"),
  ].join("");
  const revision = String(overview.revision || "");
  document.getElementById("datasetAttribution").textContent =
    `TiniX AI · ${formatCount(overview.sample_row_count)} rows trong mẫu / ` +
    `${formatCount(overview.source_record_count)} rows nguồn · revision ${revision.slice(0, 8)}… · CC BY-NC 4.0`;
}

function renderTargets(targets) {
  allTargets = targets;
  const provinceSelect = document.getElementById("provinceSelect");
  provinceSelect.innerHTML = '<option value="">Chọn tỉnh / thành trước</option>';
  const provinces = [...new Set(targets.map((target) => target.original_province))]
    .filter(Boolean)
    .sort((left, right) => left.localeCompare(right, "vi"));
  for (const province of provinces) {
    const option = document.createElement("option");
    option.value = province;
    option.textContent = province;
    provinceSelect.append(option);
  }

  const params = new URLSearchParams(window.location.search);
  const requestedRank = Number(params.get("rank"));
  const firstWithData = targets.find((target) => Number(target.candidate_count) > 0);
  const initialTarget = targets.find((target) => target.target_rank === requestedRank) || firstWithData;
  if (initialTarget) {
    provinceSelect.value = initialTarget.original_province;
    renderWardOptions(initialTarget.original_province, initialTarget.target_rank);
  } else {
    renderWardOptions("");
  }
}

function renderWardOptions(province, selectedRank = null) {
  const select = document.getElementById("targetSelect");
  select.replaceChildren(new Option(province ? "Chọn phường / xã" : "Chọn tỉnh/thành trước", ""));
  const matchingTargets = province
    ? allTargets.filter((target) => target.original_province === province)
    : [];
  for (const target of matchingTargets) {
    const option = document.createElement("option");
    option.value = target.target_rank;
    option.textContent = `#${String(target.target_rank).padStart(2, "0")} · ${target.original_ward} · ${target.original_district} (${formatCount(target.candidate_count)} tin)`;
    select.append(option);
  }
  select.disabled = !province;
  if (selectedRank && matchingTargets.some((target) => target.target_rank === selectedRank)) {
    select.value = String(selectedRank);
  }
}

function renderStats(result) {
  const container = document.getElementById("historicalStats");
  let stats = result.statistics_by_property_type || [];
  if (result.property_type) {
    const selected = stats.find((row) => row.property_type === result.property_type);
    stats = [selected || { property_type: result.property_type, sample_count: 0 }];
  } else {
    const byType = new Map(stats.map((row) => [row.property_type, row]));
    stats = ["DAT_O", "NHA_RIENG", "CHUNG_CU"].map((type) => (
      byType.get(type) || { property_type: type, sample_count: 0 }
    ));
  }
  container.innerHTML = stats.map((row) => {
    const hasValues = Number(row.sample_count) > 0;
    if (!hasValues) {
      return `<article class="historical-stat-empty"><div><strong>${escapeHtml(propertyLabels[row.property_type] || row.property_type)}</strong><br />Chưa có tin đủ điều kiện cho nhóm này trong mẫu đã lấy.</div></article>`;
    }
    const quality = qualityInfo(row.sample_quality_level);
    const typeMonths = (result.monthly_statistics || [])
      .filter((month) => month.property_type === row.property_type)
      .map((month) => month.published_month)
      .sort();
    const period = typeMonths.length
      ? `${typeMonths[0]} – ${typeMonths[typeMonths.length - 1]}`
      : "Không rõ tháng đăng";
    const showMean = Number(row.sample_count) >= 5;
    return `<article class="historical-stat-card">
      <div class="historical-stat-head"><strong>${escapeHtml(propertyLabels[row.property_type] || row.property_type)}</strong><span class="historical-stat-count">n = ${formatCount(row.sample_count)} · lịch sử</span></div>
      <span class="historical-quality-badge">${escapeHtml(quality.label)}</span>
      <div class="historical-stat-values"><div><span>Trung bình / m²${showMean ? "" : " · ẩn khi n < 5"}</span><strong>${showMean ? formatMillions(row.mean_price_per_m2) : "—"}</strong></div><div><span>Trung vị / m²</span><strong>${formatMillions(row.median_price_per_m2)}</strong></div></div>
      <div class="historical-stat-range"><span>P25–P75</span><strong>${formatMillions(row.p25_price_per_m2)} – ${formatMillions(row.p75_price_per_m2)}</strong></div>
      <p class="historical-sample-warning">${escapeHtml(quality.description)} Dữ liệu lịch sử chưa xác minh từng tin và không đại diện cho giá hiện hành.</p>
      <p class="historical-stat-unit">${escapeHtml(period)} · TiniX AI · giá rao/m² · chưa có URL tin gốc</p>
    </article>`;
  }).join("");
}

function formatMillionWords(value) {
  if (value == null || !Number.isFinite(Number(value))) return "chưa có số liệu";
  return `${(Number(value) / 1_000_000).toLocaleString("vi-VN", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })} triệu đồng`;
}

function periodForProperty(result, propertyType) {
  const months = (result.monthly_statistics || [])
    .filter((month) => month.property_type === propertyType)
    .map((month) => month.published_month)
    .filter(Boolean)
    .sort();
  return months.length ? `${months[0]} – ${months[months.length - 1]}` : "không rõ kỳ đăng";
}

function renderR1Preview(result) {
  const panel = document.getElementById("historicalR1");
  const summaryElement = document.getElementById("historicalR1Summary");
  const payloadElement = document.getElementById("historicalR1Payload");
  const target = result.target || {};
  const propertyType = result.property_type || "ALL";
  const availableStats = Array.isArray(result.statistics_by_property_type)
    ? result.statistics_by_property_type
    : [];
  const statistics = availableStats.filter((row) => (
    Number(row.sample_count) > 0 && (!result.property_type || row.property_type === result.property_type)
  ));

  const summaryLines = statistics.map((row) => {
    const quality = qualityInfo(row.sample_quality_level);
    return `${propertyLabels[row.property_type] || row.property_type}: trung vị ${formatMillionWords(row.median_price_per_m2)}/m² từ ${formatCount(row.sample_count)} tin (${quality.label}; ${periodForProperty(result, row.property_type)})`;
  });
  const summaryText = summaryLines.length
    ? `Tại ${target.original_ward || "địa bàn đã chọn"}, ${target.original_province || ""}, mẫu lịch sử ghi nhận ${summaryLines.join("; ")}. Đây là mô tả mẫu giá rao, không phải giá hiện hành.`
    : `Chưa có nhóm tin đủ điều kiện thống kê cho ${target.original_ward || "địa bàn đã chọn"} với bộ lọc này; R1 không tạo câu dẫn giá thay thế.`;

  const firstDate = datasetOverview?.first_published_date || null;
  const lastDate = datasetOverview?.last_published_date || null;
  const reference = {
    reference_id: "R1",
    data_classification: "HISTORICAL_RESEARCH_ONLY",
    target: {
      rank: Number(target.target_rank),
      ward: target.original_ward || null,
      legacy_district: target.original_district || null,
      province: target.original_province || null,
    },
    property_type_filter: propertyType,
    dataset: {
      dataset_id: datasetOverview?.dataset_id || null,
      attribution: datasetOverview?.attribution || null,
      dataset_url: datasetOverview?.dataset_url || null,
      revision: datasetOverview?.revision || null,
      license_id: datasetOverview?.license_id || null,
      published_date_range: firstDate && lastDate ? [firstDate, lastDate] : null,
      sampled_rows: Number(datasetOverview?.sample_row_count || 0),
    },
    statistics: statistics.map((row) => ({
      property_type: row.property_type,
      sample_count: Number(row.sample_count),
      mean_price_per_m2: Number(row.sample_count) >= 5 && row.mean_price_per_m2 != null
        ? Number(row.mean_price_per_m2)
        : null,
      median_price_per_m2: row.median_price_per_m2 == null ? null : Number(row.median_price_per_m2),
      p25_price_per_m2: row.p25_price_per_m2 == null ? null : Number(row.p25_price_per_m2),
      p75_price_per_m2: row.p75_price_per_m2 == null ? null : Number(row.p75_price_per_m2),
      sample_quality_level: row.sample_quality_level || null,
      sample_quality_flags: row.sample_quality_flags || [],
      published_month_range: periodForProperty(result, row.property_type),
    })),
    summary: summaryText,
    generated_by_ai: false,
    ai_handoff_enabled: false,
    limitations: [
      "Historical research sample; not current market verification.",
      "Non-probability sample with no per-listing source URL.",
      "Not evidence about an individual's assets, income, rent, or repayment capacity.",
    ],
  };

  summaryElement.textContent = summaryText;
  payloadElement.textContent = JSON.stringify(reference, null, 2);
  panel.hidden = false;
}

function clearR1Preview() {
  document.getElementById("historicalR1").hidden = true;
  document.getElementById("historicalR1Summary").textContent = "";
  document.getElementById("historicalR1Payload").textContent = "";
}

function statusFor(candidate) {
  if (candidate.dedupe_classification === "POSSIBLE_DUPLICATE") {
    return { label: "Có thể trùng · cần rà soát", kind: "is-review" };
  }
  if (candidate.deal_classification === "CONFLICT") {
    return { label: "Tiêu đề có dấu hiệu bán và thuê · xung đột", kind: "is-review" };
  }
  if (candidate.deal_type === "EXPLICIT_RENT") {
    return { label: "Tiêu đề ghi thuê · ngoài thống kê giá bán", kind: "is-excluded" };
  }
  if (candidate.deal_type === "AMBIGUOUS") {
    return { label: "Tiêu đề có tín hiệu giao dịch lẫn nhau · rà soát", kind: "is-review" };
  }
  if (candidate.deal_type === "UNCLASSIFIED") {
    return { label: "Không suy đoán loại giao dịch · rà soát", kind: "is-review" };
  }
  if (candidate.candidate_status === "ELIGIBLE_HISTORICAL_SALE") {
    if ((candidate.review_reason || "").includes("PROPERTY_TYPE_FROM_TITLE_RESIDENTIAL_LAND_UNVERIFIED")) {
      return { label: "Đất ở theo tiêu đề · chưa xác minh quyền sử dụng", kind: "is-review" };
    }
    return { label: "Tiêu đề ghi bán · đủ điều kiện thống kê lịch sử", kind: "" };
  }
  return { label: candidate.review_reason || "Nhóm bất động sản cần rà soát", kind: "is-review" };
}

function renderCandidates(result) {
  const tableBody = document.getElementById("candidateRows");
  const empty = document.getElementById("emptyCandidates");
  const rows = result.candidates || [];
  document.getElementById("candidateCount").textContent =
    `${formatCount(result.candidate_count)} dòng · ${formatCount(result.statistics_eligible_count)} đủ điều kiện thống kê`;
  empty.hidden = rows.length > 0;
  if (!rows.length) {
    empty.textContent = result.property_type === "DAT_O"
      ? "Mẫu chưa có loại “Đất ở” đủ rõ. Nguồn ghi “Đất” chung nên hệ thống không tự xếp thành đất ở."
      : `Không có dòng khớp địa bàn và bộ lọc này trong ${formatCount(result.sample_row_count)} rows đã khảo sát. Điều đó không chứng minh địa bàn không có tin rao.`;
  }
  tableBody.innerHTML = rows.map((candidate) => {
    const status = statusFor(candidate);
    const pricePerM2 = candidate.deal_type === "EXPLICIT_SALE"
      ? formatMoney(candidate.price_per_m2)
      : "—";
    const type = candidate.property_type
      ? `${propertyLabels[candidate.property_type] || candidate.property_type} · ${candidate.property_type_raw}`
      : `${candidate.property_type_raw || "Chưa rõ"} · chưa ánh xạ`;
    return `<tr>
      <td><div class="candidate-title">${escapeHtml(candidate.title)}</div><span class="candidate-status ${status.kind}">${escapeHtml(status.label)}</span><div class="subtle-label">Nguồn dòng #${formatCount(candidate.source_row_index)} · không có URL tin riêng</div></td>
      <td>${escapeHtml(type)}</td>
      <td class="number-cell">${formatMoney(candidate.price_vnd)}</td>
      <td class="number-cell">${Number(candidate.area_m2).toLocaleString("vi-VN")} m²</td>
      <td class="number-cell">${pricePerM2}</td>
      <td class="number-cell">${formatDate(candidate.published_date)}</td>
    </tr>`;
  }).join("");
}

function renderMonthly(result) {
  const body = document.getElementById("monthlyRows");
  const empty = document.getElementById("emptyMonthly");
  const rows = result.monthly_statistics || [];
  body.innerHTML = rows.map((row) => {
    const showMean = Number(row.sample_count) >= 5;
    return `<tr>
    <td class="number-cell">${escapeHtml(row.published_month)}</td>
    <td>${escapeHtml(propertyLabels[row.property_type] || row.property_type)}</td>
    <td class="number-cell">${formatCount(row.sample_count)}</td>
    <td class="number-cell" title="${showMean ? "" : "Ẩn trung bình vì cỡ mẫu dưới 5"}">${showMean ? formatMillions(row.mean_price_per_m2) : "—"}</td>
    <td class="number-cell">${formatMillions(row.median_price_per_m2)}</td>
    <td class="number-cell">${formatMillions(row.p25_price_per_m2)} – ${formatMillions(row.p75_price_per_m2)}</td>
    <td class="number-cell">${formatMillions(row.min_price_per_m2)} – ${formatMillions(row.max_price_per_m2)}</td>
    <td><span class="historical-quality-badge">${escapeHtml(qualityInfo(row.sample_quality_level).label)}</span><br /><small>${escapeHtml(row.sample_quality_flags || row.data_quality)}</small></td>
  </tr>`;
  }).join("");
  empty.hidden = rows.length > 0;
}

async function loadLookup() {
  const targetRank = document.getElementById("targetSelect").value;
  if (!targetRank) {
    document.getElementById("targetHeading").replaceChildren();
    document.getElementById("historicalStats").replaceChildren();
    clearR1Preview();
    document.getElementById("candidateRows").replaceChildren();
    document.getElementById("monthlyRows").replaceChildren();
    document.getElementById("candidateCount").textContent = "";
    document.getElementById("emptyCandidates").hidden = true;
    document.getElementById("emptyMonthly").hidden = true;
    return;
  }
  clearR1Preview();
  const propertyType = document.getElementById("propertySelect").value;
  const query = new URLSearchParams({ target_rank: targetRank });
  if (propertyType) query.set("property_type", propertyType);
  try {
    const result = await getJson(`${api}/lookup?${query}`);
    const target = result.target;
    document.getElementById("targetHeading").innerHTML = `<div><h2>#${String(target.target_rank).padStart(2, "0")} · ${escapeHtml(target.original_ward)}</h2><p>${escapeHtml(target.original_district)} · ${escapeHtml(target.original_province)} · mapping theo tên địa bàn cũ</p></div><span class="result-side-note">Không đại diện cho giá hiện tại</span>`;
    renderStats(result);
    renderR1Preview(result);
    renderCandidates(result);
    renderMonthly(result);
    window.history.replaceState({}, "", `?rank=${targetRank}${propertyType ? `&property_type=${propertyType}` : ""}`);
  } catch (error) {
    clearR1Preview();
    showError(error.message);
  }
}

async function start() {
  try {
    const [overview, targetResponse] = await Promise.all([
      getJson(`${api}/overview`),
      getJson(`${api}/targets`),
    ]);
    datasetOverview = overview;
    renderOverview(overview);
    renderTargets(targetResponse.targets || []);
    document.getElementById("provinceSelect").addEventListener("change", (event) => {
      renderWardOptions(event.currentTarget.value);
      document.getElementById("targetHeading").replaceChildren();
      document.getElementById("historicalStats").replaceChildren();
      clearR1Preview();
      document.getElementById("candidateRows").replaceChildren();
      document.getElementById("monthlyRows").replaceChildren();
      document.getElementById("candidateCount").textContent = "";
      document.getElementById("emptyCandidates").hidden = true;
      document.getElementById("emptyMonthly").hidden = true;
    });
    const params = new URLSearchParams(window.location.search);
    const initialPropertyType = params.get("property_type");
    if (["DAT_O", "NHA_RIENG", "CHUNG_CU"].includes(initialPropertyType)) {
      document.getElementById("propertySelect").value = initialPropertyType;
    }
    document.getElementById("targetSelect").addEventListener("change", loadLookup);
    document.getElementById("propertySelect").addEventListener("change", loadLookup);
    await loadLookup();
  } catch (error) {
    showError(error.message);
    document.getElementById("overviewMetrics").innerHTML =
      '<div class="metric-loading">Chưa đọc được database pilot. Hãy kiểm tra rằng lệnh import đã hoàn tất.</div>';
  }
}

start();
