const API = "/api/v1/research-answers";
const PAGE_SIZE = 50;
let currentOffset = 0;
let providersConfigured = false;
let pollTimer = null;

const $ = (id) => document.getElementById(id);
const number = (value) => new Intl.NumberFormat("vi-VN").format(Number(value || 0));

function setCurrentMonth() {
  const now = new Date();
  $("period").value = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

async function getJson(path) {
  const response = await fetch(path, {
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `Yêu cầu thất bại (${response.status}).`);
  return data;
}

async function postJson(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `Yêu cầu thất bại (${response.status}).`);
  return data;
}

async function loadConfiguration() {
  const config = await getJson(`${API}/config`);
  providersConfigured = Boolean(config.ready);
  $("modelName").textContent = config.model || "Chưa cấu hình";
  const modelReady = Boolean(config.model_api_configured);
  const searchReady = Boolean(config.search_api_configured);
  $("keyStatus").textContent = providersConfigured
    ? "Tavily và model đã cấu hình cục bộ. Chưa gửi request."
    : `Cấu hình chưa đủ: ${[
        !searchReady ? "TAVILY_API_KEY" : "",
        !modelReady ? "OPENAI_API_KEY" : "",
        !config.base_url_configured ? "OPENAI_BASE_URL" : "",
      ].filter(Boolean).join(", ")}. Chỉ có thể chuẩn bị job.`;
  updateRunButton();
}

async function loadProvinces() {
  const result = await getJson(`${API}/provinces`);
  for (const name of result.provinces || []) {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    $("province").append(option);
  }
  await loadTargets();
}

async function loadTargets() {
  const province = $("province").value;
  const query = province ? `?province=${encodeURIComponent(province)}` : "";
  const result = await getJson(`${API}/targets${query}`);
  const select = $("target");
  const priorValue = select.value;
  select.replaceChildren(new Option("Toàn bộ phạm vi đã chọn", ""));
  for (const target of result.targets || []) {
    const option = document.createElement("option");
    option.value = target.administrative_code;
    option.textContent = `${target.administrative_name} · ${target.province_name} [${target.administrative_code}]`;
    select.append(option);
  }
  if ([...select.options].some((option) => option.value === priorValue)) select.value = priorValue;
  $("targetScope").textContent = province
    ? `${number(result.count)} địa bàn hiện hành trong ${province}. Chọn một mã để chạy riêng hoặc giữ toàn bộ tỉnh.`
    : `${number(result.count)} xã, phường và đặc khu hiện hành trong snapshot NSO.`;
}

function setStatus(message, isError = false) {
  const status = $("runStatus");
  status.textContent = message;
  status.classList.toggle("error", isError);
}

function updateRunButton() {
  const permitted = providersConfigured && $("confirmLive").checked;
  $("runButton").disabled = !permitted;
  const limit = Math.min(20, Math.max(1, Number($("batchSize").value || 1)));
  $("confirmCount").textContent = number(limit);
}

function statusLabel(status) {
  return ({
    PENDING: "Đang chờ",
    RUNNING: "Đang chạy",
    COMPLETED: "Hoàn tất · có nguồn",
    NO_RESULT: "Chưa có kết quả có nguồn",
    FAILED: "Lỗi",
  })[status] || status || "—";
}

function appendCell(row, value) {
  const cell = document.createElement("td");
  cell.textContent = value == null || value === "" ? "—" : String(value);
  row.append(cell);
}

function renderStatus(result) {
  const counts = result.job_counts || {};
  const total = Number(counts.total || 0);
  const completed = Number(counts.COMPLETED || 0);
  const noResult = Number(counts.NO_RESULT || 0);
  const failed = Number(counts.FAILED || 0);
  const running = Number(counts.RUNNING || 0);
  const done = completed + noResult + failed;
  $("totalCount").textContent = number(total);
  $("pendingCount").textContent = number(counts.PENDING || 0);
  $("completedCount").textContent = number(completed);
  $("otherCount").textContent = number(noResult + failed);
  $("otherDetail").textContent = `${number(noResult)} chưa có · ${number(failed)} lỗi · ${number(running)} đang chạy`;
  $("periodLabel").textContent = `Kỳ ${result.period || $("period").value || "—"}`;
  $("progressBar").style.width = total ? `${Math.round((done / total) * 100)}%` : "0%";

  const rows = $("jobRows");
  rows.replaceChildren();
  for (const job of result.jobs || []) {
    const row = document.createElement("tr");
    appendCell(row, job.administrative_code);
    appendCell(row, job.administrative_name);
    appendCell(row, job.province_name);
    const statusCell = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = `status ${job.status || ""}`;
    badge.textContent = statusLabel(job.status);
    statusCell.append(badge);
    row.append(statusCell);
    appendCell(row, job.attempt_count);
    appendCell(row, job.error_text);
    rows.append(row);
  }

  $("emptyJobs").hidden = total > 0;
  const start = total ? Math.min(currentOffset + 1, total) : 0;
  const end = Math.min(currentOffset + (result.jobs || []).length, total);
  $("pageLabel").textContent = total ? `${number(start)}–${number(end)} / ${number(total)}` : "0 địa bàn";
  $("prevPage").disabled = currentOffset <= 0;
  $("nextPage").disabled = currentOffset + PAGE_SIZE >= total;
  $("downloadLink").href = `${API}/export?period=${encodeURIComponent(result.period || $("period").value)}`;
  const hasExport = Boolean(result.jsonl_path);
  $("downloadLink").classList.toggle("disabled", !hasExport);
  $("downloadLink").setAttribute("aria-disabled", hasExport ? "false" : "true");
  $("outputPath").textContent = hasExport
    ? result.jsonl_path
    : "File JSONL sẽ xuất hiện sau khi hoàn tất tìm kiếm và tóm tắt.";
  updateRunButton();
}

async function refreshStatus() {
  const period = $("period").value;
  if (!period) return;
  const query = new URLSearchParams({ period, offset: String(currentOffset), limit: String(PAGE_SIZE) });
  const result = await getJson(`${API}/status?${query}`);
  renderStatus(result);
}

async function prepareJobs() {
  $("prepareButton").disabled = true;
  setStatus("Đang chuẩn bị danh sách job từ snapshot hành chính cục bộ; chưa gửi request.");
  try {
    const result = await postJson(`${API}/prepare`, {
      period: $("period").value,
      province: $("province").value || null,
      administrative_code: $("target").value || null,
    });
    currentOffset = 0;
    await refreshStatus();
    setStatus(`Đã chuẩn bị ${number(result.target_count)} job cho kỳ ${result.period}. Chưa gửi request ra ngoài.`);
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    $("prepareButton").disabled = false;
  }
}

async function runBatch() {
  if (!$("confirmLive").checked) {
    setStatus("Hãy xác nhận trước khi tìm web và gọi model.", true);
    return;
  }
  const limit = Math.min(20, Math.max(1, Number($("batchSize").value || 1)));
  $("runButton").disabled = true;
  $("prepareButton").disabled = true;
  setStatus(`Đang chạy tối đa ${number(limit)} địa bàn tuần tự: tìm Tavily rồi tóm tắt bằng Gemma.`);
  pollTimer = window.setInterval(() => refreshStatus().catch(() => {}), 2000);
  try {
    const result = await postJson(`${API}/run`, {
      period: $("period").value,
      limit,
      retry_failed: $("retryFailed").checked,
      confirm_live: true,
    });
    currentOffset = 0;
    await refreshStatus();
    setStatus(`Lượt ${result.run_id ?? ""} xong: ${number(result.completed)} có nguồn, ${number(result.no_result)} chưa có kết quả, ${number(result.failed)} lỗi. JSONL đã cập nhật.`);
  } catch (error) {
    setStatus(error.message, true);
    await refreshStatus().catch(() => {});
  } finally {
    if (pollTimer) window.clearInterval(pollTimer);
    pollTimer = null;
    $("prepareButton").disabled = false;
    updateRunButton();
  }
}

async function init() {
  setCurrentMonth();
  $("batchSize").addEventListener("input", updateRunButton);
  $("confirmLive").addEventListener("change", updateRunButton);
  $("province").addEventListener("change", () => loadTargets().catch((error) => setStatus(error.message, true)));
  $("period").addEventListener("change", () => {
    currentOffset = 0;
    refreshStatus().catch((error) => setStatus(error.message, true));
  });
  $("prepareButton").addEventListener("click", prepareJobs);
  $("runButton").addEventListener("click", runBatch);
  $("prevPage").addEventListener("click", () => {
    currentOffset = Math.max(0, currentOffset - PAGE_SIZE);
    refreshStatus().catch((error) => setStatus(error.message, true));
  });
  $("nextPage").addEventListener("click", () => {
    currentOffset += PAGE_SIZE;
    refreshStatus().catch((error) => setStatus(error.message, true));
  });
  $("downloadLink").addEventListener("click", (event) => {
    if ($("downloadLink").getAttribute("aria-disabled") === "true") event.preventDefault();
  });
  try {
    await Promise.all([loadConfiguration(), loadProvinces()]);
    await refreshStatus();
    setStatus("Đã đọc cấu hình và snapshot hành chính. Chưa gửi request.");
  } catch (error) {
    setStatus(error.message, true);
  }
}

init();
