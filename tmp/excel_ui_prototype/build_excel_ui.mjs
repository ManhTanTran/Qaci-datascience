import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const repo = path.resolve(".");
const rawPath = path.join(repo, "data/raw/research/fpt_reasoning_poc/FPT_credit_scoring_synthetic_10_cases.xlsx");
const profilesPath = path.join(repo, "data/processed/research/fpt_reasoning_poc/profiles.csv");
const featureDefsPath = path.join(repo, "data/raw/research/fpt_reasoning_poc/feature_definitions.csv");
const featureMappingPath = path.join(repo, "configs/research/fpt_reasoning_poc/feature_mapping.yaml");
const validationPath = path.join(repo, "data/processed/research/fpt_reasoning_poc/validation_report.json");
const ruleResultsPath = path.join(repo, "outputs/research/fpt_reasoning_poc/rule_results.jsonl");
const aiResultsPath = path.join(repo, "outputs/research/fpt_reasoning_poc/experiment_results.jsonl");
const outputDir = path.join(repo, "outputs/excel_ui_prototype_20260910");
const outputPath = path.join(outputDir, "fpt_credit_reasoning_ui_prototype.xlsx");

const navy = "#17365D";
const blue = "#D9EAF7";
const paleBlue = "#EEF5FB";
const teal = "#0F766E";
const green = "#E2F0D9";
const amber = "#FFF2CC";
const red = "#FCE4D6";
const gray = "#F3F6F8";
const dark = "#1F2937";
const border = "#D9E2F3";
const font = "Aptos";

function parseJsonl(text) {
  return text.trim().split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line));
}

function asText(value) {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return value.map(asText).join(" | ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function flattenObject(value) {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return value.map(asText).join(" | ");
  if (typeof value === "object") return JSON.stringify(value);
  return value;
}

function stripYamlValue(value) {
  return value.trim().replace(/^["']|["']$/g, "");
}

function parseYamlInlineList(value) {
  const trimmed = value.trim();
  if (!trimmed.startsWith("[") || !trimmed.endsWith("]")) return null;
  const body = trimmed.slice(1, -1).trim();
  if (!body) return [];
  return body.split(",").map((item) => stripYamlValue(item)).filter(Boolean);
}

function parseFeatureMapping(text) {
  const mappings = [];
  let inFields = false;
  let current = null;
  let currentList = null;

  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.replace(/\s+#.*$/, "");
    if (!line.trim()) continue;
    if (/^fields:\s*$/.test(line)) {
      inFields = true;
      continue;
    }
    if (!inFields) continue;

    const fieldMatch = /^  ([A-Za-z0-9_]+):\s*$/.exec(line);
    if (fieldMatch) {
      current = {
        field: fieldMatch[1],
        sources: [],
        missing_sources: [],
        source_type: "",
        transform: "",
        note: "",
      };
      mappings.push(current);
      currentList = null;
      continue;
    }

    if (!current) continue;
    const propertyMatch = /^    ([A-Za-z0-9_]+):\s*(.*)$/.exec(line);
    if (propertyMatch) {
      const [, key, rawValue] = propertyMatch;
      const inlineList = parseYamlInlineList(rawValue);
      if (inlineList !== null) {
        current[key] = inlineList;
        currentList = null;
      } else if (rawValue.trim() === "") {
        current[key] = [];
        currentList = key;
      } else {
        current[key] = stripYamlValue(rawValue);
        currentList = null;
      }
      continue;
    }

    const listMatch = /^      -\s*(.+)$/.exec(line);
    if (listMatch && currentList) {
      current[currentList].push(stripYamlValue(listMatch[1]));
    }
  }

  return mappings;
}

const profileColumnByField = {
  user_id: "id người dùng",
  age: "tuổi",
  local_context: "thu nhập bình quân địa phương",
  location: "địa chỉ",
  device_usage: "hành vi sử dụng thiết bị",
  payment_history_12m: "lịch sử đóng cước internet/truyền hình",
  shopping_installment: "lịch sử mua sắm, trả góp",
  orders: "giá trị và tần suất đơn hàng",
  healthcare_spending: "chi tiêu thuốc, thực phẩm chức năng",
  fpt_education: "có cho con học ở FPT không / ngành gì",
};

const keepReasonByField = {
  user_id: "Khóa truy vết từ raw sang profile, rule và AI response.",
  age: "Dùng cho rule tuổi > 23. Không tự sinh tuổi chính xác khi chỉ có nhóm tuổi.",
  local_context: "Bối cảnh khu vực. Đây là contextual_proxy, không phải thu nhập cá nhân.",
  location: "Giữ tỉnh/thành, quận/huyện, phường/xã để bổ sung urban/rural ở vòng sau.",
  device_usage: "Tín hiệu sử dụng dịch vụ và mức gắn bó hệ sinh thái FPT.",
  payment_history_12m: "Tín hiệu chính cho lịch sử đóng cước: số tháng quan sát, trễ hạn và ngày trễ tối đa.",
  shopping_installment: "Giữ chỗ cho lịch sử mua sắm/trả góp. Phần trả góp hiện chưa có trong dataset.",
  orders: "Tóm tắt tần suất và giá trị đơn hàng thay vì đưa toàn bộ raw retail feature vào AI.",
  healthcare_spending: "Chỉ dùng tổng hợp hành vi mua hàng, không suy luận tình trạng sức khỏe.",
  fpt_education: "Chưa có dữ liệu nguồn, giữ là missing để test AI không bịa thông tin giáo dục FPT.",
};

function policyForMapping(mapping) {
  if (mapping.source_type === "missing") return "missing: chưa có trong dataset, không bịa giá trị.";
  if (mapping.source_type === "contextual_proxy") return "contextual_proxy: không diễn giải là thu nhập/chi tiêu cá nhân.";
  if (mapping.missing_sources?.length) return "Giữ missing cho cột chưa có. Invalid giữ là invalid, không đổi thành 0.";
  return "Missing giữ là missing. Invalid giữ là invalid, không đổi thành 0.";
}

function sampleRawValues(mapping, rawHeaderIndex, rawRow) {
  const sources = mapping.sources ?? [];
  if (!sources.length) return "Không có raw source trong dataset hiện tại.";
  return sources.map((source) => {
    const index = rawHeaderIndex.get(source);
    if (index === undefined) return `${source}=not_in_raw_file`;
    const value = rawRow[index];
    return `${source}=${value === null || value === undefined || value === "" ? "missing" : asText(value)}`;
  }).join(" | ");
}

function colLetter(n) {
  let s = "";
  let x = n;
  while (x > 0) {
    const r = (x - 1) % 26;
    s = String.fromCharCode(65 + r) + s;
    x = Math.floor((x - 1) / 26);
  }
  return s;
}

function styleTitle(sheet, range, fill = navy) {
  sheet.getRange(range).format = {
    fill,
    font: { name: font, bold: true, color: "#FFFFFF", size: 15 },
    horizontalAlignment: "center",
    verticalAlignment: "center",
  };
  sheet.getRange(range).format.rowHeight = 30;
}

function styleHeader(sheet, range, fill = navy) {
  sheet.getRange(range).format = {
    fill,
    font: { name: font, bold: true, color: "#FFFFFF" },
    wrapText: true,
    verticalAlignment: "center",
    borders: { preset: "all", style: "thin", color: border },
  };
}

function styleBody(sheet, range) {
  sheet.getRange(range).format = {
    font: { name: font, color: dark },
    verticalAlignment: "center",
    borders: { preset: "all", style: "thin", color: border },
  };
}

function addTable(sheet, address, name) {
  const table = sheet.tables.add(address, true, name);
  table.style = "TableStyleMedium2";
  table.showFilterButton = true;
  return table;
}

function setupDataSheet(sheet, title, usedAddress, headerAddress, tableName) {
  sheet.showGridLines = false;
  sheet.freezePanes.freezeRows(1);
  styleHeader(sheet, headerAddress);
  styleBody(sheet, usedAddress);
  addTable(sheet, usedAddress, tableName);
  sheet.getRange(headerAddress).format.rowHeight = 32;
  sheet.getUsedRange().format.autofitColumns();
  sheet.getUsedRange().format.autofitRows();
  sheet.getRange(usedAddress).format.font = { name: font, size: 10, color: dark };
  // Re-apply header styling after body font styling so table headers stay readable.
  styleHeader(sheet, headerAddress);
  sheet.getRange(headerAddress).format.font = { name: font, bold: true, size: 11, color: "#FFFFFF" };
  sheet.getRange(headerAddress).format.rowHeight = 38;
}

async function csvValues(csvPath) {
  const csv = await fs.readFile(csvPath, "utf8");
  const wb = await Workbook.fromCSV(csv, { sheetName: "Import" });
  return wb.worksheets.getItem("Import").getUsedRange().values;
}

async function main() {
  const rawBlob = await FileBlob.load(rawPath);
  const wb = await SpreadsheetFile.importXlsx(rawBlob);
  const rawSheet = wb.worksheets.getItem("Synthetic_Customers");
  const rawValues = rawSheet.getUsedRange().values;
  const rawRows = rawValues.length - 1;
  const rawCols = rawValues[0].length;
  const rawLastCol = colLetter(rawCols);

  const profiles = await csvValues(profilesPath);
  const featureDefs = await csvValues(featureDefsPath);
  const featureMappings = parseFeatureMapping(await fs.readFile(featureMappingPath, "utf8"));
  const validation = JSON.parse(await fs.readFile(validationPath, "utf8"));
  const ruleRecords = parseJsonl(await fs.readFile(ruleResultsPath, "utf8"));
  const aiRecords = parseJsonl(await fs.readFile(aiResultsPath, "utf8"));
  const testCaseCount = new Set(aiRecords.map((r) => r.case_id).filter(Boolean)).size;
  const mappedRawColumns = new Set(featureMappings.flatMap((mapping) => mapping.sources ?? []));
  const configuredMissingColumns = new Set(featureMappings.flatMap((mapping) => mapping.missing_sources ?? []));
  const rawHeaderIndex = new Map(rawValues[0].map((header, index) => [String(header), index]));
  const sampleRawRow = rawValues.slice(1).find((row) => row[rawHeaderIndex.get("user_id")] === "customer_1") ?? rawValues[1];
  const sampleProfileRow = profiles.slice(1).find((row) => row[0] === "customer_1") ?? profiles[1];

  const existingNames = new Set(wb.worksheets.items.map((s) => s.name));
  const addSheet = (name) => existingNames.has(name) ? wb.worksheets.getItem(name) : wb.worksheets.add(name);

  const readme = addSheet("00_README");
  const dash = addSheet("01_DASHBOARD");
  const rawToImportant = addSheet("02_RAW_TO_IMPORTANT");
  const profile = addSheet("03_PROFILE_FEATURES");
  const validationSheet = addSheet("04_VALIDATION");
  const ruleSheet = addSheet("05_RULE_RESULTS");
  const aiSheet = addSheet("06_AI_RESPONSE");
  const dictSheet = addSheet("07_FEATURE_DICTIONARY");
  const nextSheet = addSheet("08_NEXT_STEPS");

  for (const sheet of [readme, dash, rawToImportant, profile, validationSheet, ruleSheet, aiSheet, dictSheet, nextSheet]) {
    sheet.showGridLines = false;
  }

  // Raw source remains intact. Add light navigation-friendly formatting only.
  rawSheet.showGridLines = false;
  rawSheet.freezePanes.freezeRows(1);
  styleHeader(rawSheet, `A1:${rawLastCol}1`);
  rawSheet.getRange(`A1:${rawLastCol}${rawValues.length}`).format.font = { name: font, size: 9, color: dark };
  styleHeader(rawSheet, `A1:${rawLastCol}1`);
  rawSheet.getRange(`A1:${rawLastCol}1`).format.font = { name: font, bold: true, size: 10, color: "#FFFFFF" };
  rawSheet.getRange(`A1:${rawLastCol}1`).format.rowHeight = 38;
  rawSheet.getRange(`A1:${rawLastCol}1`).format.font = { name: font, bold: true, color: "#FFFFFF", size: 9 };
  rawSheet.getRange(`A1:${rawLastCol}${rawValues.length}`).format.wrapText = false;

  // README / navigation.
  readme.getRange("A1:H1").merge();
  readme.getRange("A1").values = [["FPT Credit Reasoning PoC — Excel UI prototype"]];
  styleTitle(readme, "A1:H1");
  readme.getRange("A3:H3").merge();
  readme.getRange("A3").values = [["Mục đích: xem luồng từ dữ liệu raw gần 200 cột → profile nghiệp vụ → rule engine → response AI → việc cần xác nhận."]];
  readme.getRange("A3").format = { fill: paleBlue, font: { name: font, italic: true, color: dark }, wrapText: true };
  readme.getRange("A5:C5").values = [["Sheet", "Vai trò", "Cách dùng"]];
  readme.getRange("A6:C15").values = [
    ["01_DASHBOARD", "Tổng quan PoC", "Bắt đầu từ đây; xem số lượng và phân bổ kết quả."],
    ["02_RAW_TO_IMPORTANT", "Raw → feature quan trọng", "Màn đầu tiên cho UI: file raw nhiều cột được gom thành feature cần dùng."],
    ["Synthetic_Customers", "Raw source", "194 cột dữ liệu gốc; không chỉnh sửa giá trị nguồn."],
    ["03_PROFILE_FEATURES", "Feature quan trọng", "10 nhóm nghiệp vụ dễ đọc, có thể dùng làm input cho UI."],
    ["04_VALIDATION", "Cảnh báo dữ liệu", "Theo dõi invalid/missing; không tự đổi invalid thành 0."],
    ["05_RULE_RESULTS", "Kết quả quyết định", "Hard rule là nguồn quyết định; AI không được phá hard rule."],
    ["06_AI_RESPONSE", "Response AI", "Xem reason, evidence, risk, missing data và JSON gốc."],
    ["07_FEATURE_DICTIONARY", "Từ điển feature", "Tra cứu mapping raw → nhóm nghiệp vụ và policy."],
    ["08_NEXT_STEPS", "Lộ trình tiếp theo", "Checklist xác nhận data owner, test và tích hợp UI."],
    ["", "Lưu ý", "Đây là research PoC, không phải hệ thống xét duyệt tín dụng thật."],
  ];
  styleHeader(readme, "A5:C5");
  styleBody(readme, "A6:C15");
  readme.getRange("A6:C15").format.wrapText = true;
  addTable(readme, "A5:C15", "ReadmeNavigation");
  readme.getRange("A16:H19").values = [
    ["Ranh giới thiết kế", "Rule engine quyết định; AI chỉ giải thích, phát hiện mâu thuẫn và dữ liệu thiếu.", "", "", "", "", "", ""],
    ["Nguồn", "Synthetic_Customers + feature_definitions.csv + profiles.csv + validation_report.json + rule/AI JSONL.", "", "", "", "", "", ""],
    ["Đơn vị", "Thu nhập/chi tiêu cần data owner xác nhận trước khi diễn giải như tiền tệ thực.", "", "", "", "", "", ""],
    ["Cập nhật", "Workbook sinh từ trạng thái repo hiện tại; chạy lại pipeline/experiment rồi tạo lại workbook để refresh.", "", "", "", "", "", ""],
  ];
  readme.getRange("A16:A19").format = { fill: blue, font: { name: font, bold: true, color: dark } };
  readme.getRange("B16:H19").merge(true);
  readme.getRange("B16:H19").format = { fill: gray, font: { name: font, color: dark }, wrapText: true };
  readme.getRange("A1:H19").format.font = { name: font };
  readme.getRange("A:A").format.columnWidth = 23;
  readme.getRange("B:B").format.columnWidth = 55;
  readme.getRange("C:C").format.columnWidth = 62;
  readme.getRange("A1:H19").format.autofitRows();

  // Dashboard.
  dash.getRange("A1:H1").merge();
  dash.getRange("A1").values = [["FPT Credit Reasoning PoC — Dashboard"]];
  styleTitle(dash, "A1:H1", teal);
  dash.getRange("A3:H3").values = [["Raw file → important features → rule → AI explanation", "", "", "", "", "", "", ""]];
  dash.getRange("A3:H3").merge();
  dash.getRange("A3").format = { fill: paleBlue, font: { name: font, italic: true, color: dark } };
  dash.getRange("A5:B5").values = [["Raw records", "Raw feature columns"]];
  dash.getRange("C5:D5").values = [["Processed profiles", "Validation warnings"]];
  dash.getRange("E5:F5").values = [["AI response rows", "Test cases"]];
  dash.getRange("G5:H5").values = [["Last refreshed", "Status"]];
  dash.getRange("A5:H5").format = { fill: navy, font: { name: font, bold: true, color: "#FFFFFF" }, wrapText: true, horizontalAlignment: "center" };
  dash.getRange("A6:F6").formulas = [[
    `=COUNTA('Synthetic_Customers'!A2:A${rawRows + 1})`,
    `=${rawCols}`,
    `=COUNTA('03_PROFILE_FEATURES'!A2:A${profiles.length})`,
    `=COUNTA('04_VALIDATION'!A2:A${Math.max(2, validation.warnings.length + 1)})`,
    `=COUNTA('06_AI_RESPONSE'!A2:A${Math.max(2, aiRecords.length + 1)})`,
    `=${testCaseCount}`,
  ]];
  dash.getRange("G6:H6").values = [[new Date().toISOString().slice(0, 10), "PoC / research"]];
  dash.getRange("A6:H6").format = { fill: paleBlue, font: { name: font, bold: true, size: 16, color: teal }, horizontalAlignment: "center", verticalAlignment: "center", borders: { preset: "all", style: "thin", color: border } };
  dash.getRange("A8:D8").values = [["Rule decision", "Count", "Interpretation", "Hard-rule note"]];
  dash.getRange("A9:A11").values = [["ELIGIBLE"], ["MANUAL_REVIEW"], ["NOT_ELIGIBLE"]];
  dash.getRange("B9:B11").formulas = [[`=COUNTIF('05_RULE_RESULTS'!B2:B${ruleRecords.length + 1},A9)`], [`=COUNTIF('05_RULE_RESULTS'!B2:B${ruleRecords.length + 1},A10)`], [`=COUNTIF('05_RULE_RESULTS'!B2:B${ruleRecords.length + 1},A11)`]];
  dash.getRange("C9:D11").values = [
    ["Passed hard rules", "AI must not change this"],
    ["Needs review / uncertain", "AI can flag conflicts"],
    ["Hard rule failed", "AI cannot override"],
  ];
  styleHeader(dash, "A8:D8");
  styleBody(dash, "A9:D11");
  dash.getRange("A9:D11").format.wrapText = true;
  addTable(dash, "A8:D11", "DashboardRuleSummary");
  const chart = dash.charts.add("bar", dash.getRange("A8:B11"));
  chart.title = "Rule decisions";
  chart.hasLegend = false;
  chart.setPosition("F8", "H20");
  dash.getRange("A14:D14").merge();
  dash.getRange("A14").values = [["Luồng sử dụng workbook"]];
  dash.getRange("A14").format = { fill: navy, font: { name: font, bold: true, color: "#FFFFFF" } };
  dash.getRange("A15:D19").values = [
    ["1", "Xem raw source", "Synthetic_Customers", "Không sửa dữ liệu gốc"],
    ["2", "Chọn feature quan trọng", "02_RAW_TO_IMPORTANT", "Raw nhiều cột → nhóm field cần cho UI"],
    ["3", "Xem profile theo khách hàng", "03_PROFILE_FEATURES", "Dùng làm lớp trung gian cho UI"],
    ["4", "Kiểm tra quyết định", "04_VALIDATION + 05_RULE_RESULTS", "Tách data quality khỏi rule"],
    ["5", "Đọc reasoning AI", "06_AI_RESPONSE", "AI giải thích, không quyết định"],
  ];
  styleBody(dash, "A15:D19");
  dash.getRange("A15:A19").format = { fill: blue, font: { name: font, bold: true, color: dark }, horizontalAlignment: "center" };
  dash.getRange("A15:D19").format.wrapText = true;
  dash.getRange("A:A").format.columnWidth = 18;
  dash.getRange("B:B").format.columnWidth = 22;
  dash.getRange("C:C").format.columnWidth = 29;
  dash.getRange("D:D").format.columnWidth = 33;
  dash.getRange("E:E").format.columnWidth = 18;
  dash.getRange("F:G").format.columnWidth = 16;
  dash.getRange("H:H").format.columnWidth = 20;
  dash.getRange("A1:H20").format.autofitRows();

  // Main UI handoff: raw feature dump to selected important features.
  rawToImportant.getRange("A1:J1").merge();
  rawToImportant.getRange("A1").values = [["02_RAW_TO_IMPORTANT — từ raw nhiều cột sang feature quan trọng"]];
  styleTitle(rawToImportant, "A1:J1", teal);
  rawToImportant.getRange("A3:J3").merge();
  rawToImportant.getRange("A3").values = [["Màn này trả lời câu hỏi đầu tiên của UI: người dùng đưa file raw, pipeline giữ lại field nào, lấy từ cột raw nào, và policy missing/invalid là gì."]];
  rawToImportant.getRange("A3").format = { fill: paleBlue, font: { name: font, italic: true, color: dark }, wrapText: true };
  rawToImportant.getRange("A5:H5").values = [["Raw columns", "Raw rows", "Important fields", "Profile rows", "Mapped raw columns", "Configured missing columns", "Example customer", "Current output"]];
  rawToImportant.getRange("A6:H6").values = [[rawCols, rawRows, featureMappings.length, profiles.length - 1, mappedRawColumns.size, configuredMissingColumns.size, "customer_1", "03_PROFILE_FEATURES"]];
  styleHeader(rawToImportant, "A5:H5");
  styleBody(rawToImportant, "A6:H6");
  rawToImportant.getRange("A6:H6").format = { fill: paleBlue, font: { name: font, bold: true, size: 13, color: teal }, horizontalAlignment: "center", borders: { preset: "all", style: "thin", color: border } };

  const mappingHeaders = [
    "feature_quan_trong",
    "cot_profile",
    "source_type",
    "raw_columns_dung",
    "raw_columns_chua_co",
    "transform",
    "missing_invalid_policy",
    "ly_do_giu",
    "profile_sample_customer_1",
    "raw_sample_customer_1",
  ];
  const mappingRows = [mappingHeaders];
  for (const mapping of featureMappings) {
    const profileColumn = profileColumnByField[mapping.field] ?? mapping.field;
    const profileIndex = profiles[0].indexOf(profileColumn);
    mappingRows.push([
      mapping.field,
      profileColumn,
      mapping.source_type ?? "",
      (mapping.sources ?? []).join(", ") || "Không có trong dataset hiện tại",
      (mapping.missing_sources ?? []).join(", ") || "",
      mapping.transform ?? "",
      policyForMapping(mapping),
      keepReasonByField[mapping.field] ?? mapping.note ?? "",
      profileIndex >= 0 ? sampleProfileRow[profileIndex] ?? "" : "",
      sampleRawValues(mapping, rawHeaderIndex, sampleRawRow),
    ]);
  }
  rawToImportant.getRange(`A8:J${mappingRows.length + 7}`).values = mappingRows;
  setupDataSheet(rawToImportant, "02_RAW_TO_IMPORTANT", `A8:J${mappingRows.length + 7}`, "A8:J8", "RawToImportantMapping");
  rawToImportant.getRange("A5:H5").format.fill = teal;
  rawToImportant.getRange("A5:H5").format.font = { name: font, bold: true, size: 11, color: "#FFFFFF" };
  rawToImportant.getRange("A5:H5").format.rowHeight = 38;
  rawToImportant.getRange("A8:J8").format.fill = teal;
  rawToImportant.getRange("A8:J8").format.font = { name: font, bold: true, size: 11, color: "#FFFFFF" };
  rawToImportant.getRange("A8:J8").format.rowHeight = 52;
  rawToImportant.getRange(`A9:J${mappingRows.length + 7}`).format.wrapText = true;
  rawToImportant.getRange("A:A").format.columnWidth = 24;
  rawToImportant.getRange("B:B").format.columnWidth = 32;
  rawToImportant.getRange("C:C").format.columnWidth = 18;
  rawToImportant.getRange("D:E").format.columnWidth = 42;
  rawToImportant.getRange("F:F").format.columnWidth = 18;
  rawToImportant.getRange("G:H").format.columnWidth = 42;
  rawToImportant.getRange("I:J").format.columnWidth = 55;
  rawToImportant.getRange(`C9:C${mappingRows.length + 7}`).conditionalFormats.add("containsText", { text: "missing", format: { fill: amber, font: { color: "#9C6500", bold: true } } });
  rawToImportant.getRange(`C9:C${mappingRows.length + 7}`).conditionalFormats.add("containsText", { text: "contextual_proxy", format: { fill: blue, font: { color: navy, bold: true } } });
  rawToImportant.freezePanes.freezeRows(8);

  // Profile features.
  profile.getRange("A1:J1").values = [profiles[0]];
  profile.getRange(`A2:J${profiles.length}`).values = profiles.slice(1);
  setupDataSheet(profile, "03_PROFILE_FEATURES", `A1:J${profiles.length}`, "A1:J1", "ProfileFeatures");
  profile.getRange("A1:J1").format = { fill: teal, font: { name: font, bold: true, color: "#FFFFFF" }, wrapText: true, borders: { preset: "all", style: "thin", color: border } };
  profile.getRange(`A2:J${profiles.length}`).format.wrapText = true;
  profile.getRange("A:A").format.columnWidth = 18;
  profile.getRange("B:J").format.columnWidth = 19;
  profile.getRange(`A1:J${profiles.length}`).format.autofitRows();

  // Validation warnings.
  const validationRows = [["severity", "type", "customer_id", "feature", "observed_value", "expected_range", "message"]];
  for (const warning of validation.warnings ?? []) {
    const customerId = warning.customer_id ?? warning.user_id ?? warning.entity ?? "";
    const feature = warning.feature ?? warning.column ?? warning.feature_name ?? "";
    const observedValue = flattenObject(warning.observed_value ?? warning.value);
    const expectedRange = warning.expected_range ?? warning.expected ?? "";
    const message = warning.message
      ?? `${feature} has value ${observedValue}, outside expected range ${expectedRange}`;
    validationRows.push([
      warning.severity ?? "warning",
      warning.type ?? "",
      customerId,
      feature,
      observedValue,
      expectedRange,
      message,
    ]);
  }
  validationSheet.getRange(`A1:G${validationRows.length}`).values = validationRows;
  setupDataSheet(validationSheet, "04_VALIDATION", `A1:G${validationRows.length}`, "A1:G1", "ValidationWarnings");
  validationSheet.getRange("A2:G2").format = { fill: amber, font: { name: font, color: dark } };
  validationSheet.getRange(`A2:G${validationRows.length}`).format.wrapText = true;
  validationSheet.getRange("A:A").format.columnWidth = 12;
  validationSheet.getRange("B:B").format.columnWidth = 18;
  validationSheet.getRange("C:C").format.columnWidth = 16;
  validationSheet.getRange("D:D").format.columnWidth = 28;
  validationSheet.getRange("E:F").format.columnWidth = 22;
  validationSheet.getRange("G:G").format.columnWidth = 55;
  validationSheet.getRange(`A1:G${validationRows.length}`).format.autofitRows();

  // Rule results.
  const profileByUserId = new Map(
    profiles.slice(1).map((row) => [String(row[0] ?? ""), row]),
  );
  const profileAgeIndex = profiles[0].indexOf("tuổi");
  const summarizeRules = (rules) => (rules ?? [])
    .map((rule) => `${rule.rule_id}: ${rule.outcome}`)
    .join(" | ");
  const describeRules = (rules) => (rules ?? [])
    .map((rule) => `${rule.rule_id}: ${rule.description}`)
    .join(" | ");
  const ruleRows = [["customer_id", "rule_result", "recommendation", "age_profile", "hard_rule_outcomes", "soft_rule_outcomes", "rule_notes"]];
  for (const r of ruleRecords) {
    const customerId = r.customer_id ?? r.user_id ?? r.case_id ?? "";
    const rules = r.rules ?? [];
    const profileRow = profileByUserId.get(String(customerId)) ?? [];
    const hardRules = rules.filter((rule) => rule.type === "hard");
    const softRules = rules.filter((rule) => rule.type === "soft");
    ruleRows.push([
      customerId,
      r.rule_result ?? r.decision ?? r.result ?? "",
      r.recommendation ?? "",
      profileAgeIndex >= 0 ? profileRow[profileAgeIndex] ?? "" : "",
      summarizeRules(hardRules),
      summarizeRules(softRules),
      describeRules(rules),
    ]);
  }
  ruleSheet.getRange(`A1:G${ruleRows.length}`).values = ruleRows;
  setupDataSheet(ruleSheet, "05_RULE_RESULTS", `A1:G${ruleRows.length}`, "A1:G1", "RuleResults");
  ruleSheet.getRange(`A2:G${ruleRows.length}`).format.wrapText = true;
  ruleSheet.getRange("A:A").format.columnWidth = 16;
  ruleSheet.getRange("B:B").format.columnWidth = 18;
  ruleSheet.getRange("C:C").format.columnWidth = 18;
  ruleSheet.getRange("D:E").format.columnWidth = 32;
  ruleSheet.getRange("F:G").format.columnWidth = 42;
  ruleSheet.getRange(`A1:G${ruleRows.length}`).format.autofitRows();
  ruleSheet.getRange(`B2:B${ruleRows.length}`).conditionalFormats.add("containsText", { text: "ELIGIBLE", format: { fill: green, font: { color: "#006100", bold: true } } });
  ruleSheet.getRange(`B2:B${ruleRows.length}`).conditionalFormats.add("containsText", { text: "MANUAL_REVIEW", format: { fill: amber, font: { color: "#9C6500", bold: true } } });
  ruleSheet.getRange(`B2:B${ruleRows.length}`).conditionalFormats.add("containsText", { text: "NOT_ELIGIBLE", format: { fill: red, font: { color: "#9C0006", bold: true } } });

  // AI response rows.
  const aiHeaders = ["case_id", "repeat_index", "model", "rule_engine_decision", "expected_rule_result", "expected_recommendation", "expected_conflict", "ai_rule_result", "ai_financial_assessment", "ai_conflict_detected", "ai_recommendation", "ai_confidence", "ai_reason", "ai_supporting_evidence", "ai_risk_evidence", "ai_missing_data", "error", "response_json"];
  const aiRows = [aiHeaders];
  for (const r of aiRecords) {
    const response = r.response ?? r.response_json ?? {};
    aiRows.push([
      r.case_id ?? "",
      r.repeat_index ?? "",
      r.model ?? "",
      r.rule_engine_decision ?? "",
      r.expected_rule_result ?? "",
      r.expected_recommendation ?? "",
      r.expected_conflict ?? "",
      response.rule_result ?? r.ai_rule_result ?? "",
      response.financial_assessment ?? r.ai_financial_assessment ?? "",
      response.conflict_detected ?? r.ai_conflict_detected ?? "",
      response.recommendation ?? r.ai_recommendation ?? "",
      response.confidence ?? r.ai_confidence ?? "",
      response.reason ?? r.ai_reason ?? "",
      flattenObject(response.supporting_evidence ?? r.ai_supporting_evidence),
      flattenObject(response.risk_evidence ?? r.ai_risk_evidence),
      flattenObject(response.missing_data ?? r.ai_missing_data),
      r.error ?? "",
      JSON.stringify(response),
    ]);
  }
  aiSheet.getRange(`A1:R${aiRows.length}`).values = aiRows;
  setupDataSheet(aiSheet, "06_AI_RESPONSE", `A1:R${aiRows.length}`, "A1:R1", "AIResponses");
  aiSheet.getRange(`A2:R${aiRows.length}`).format.wrapText = true;
  aiSheet.getRange("A:A").format.columnWidth = 24;
  aiSheet.getRange("B:B").format.columnWidth = 10;
  aiSheet.getRange("C:C").format.columnWidth = 22;
  aiSheet.getRange("D:L").format.columnWidth = 20;
  aiSheet.getRange("M:P").format.columnWidth = 48;
  aiSheet.getRange("Q:Q").format.columnWidth = 32;
  aiSheet.getRange("R:R").format.columnWidth = 55;
  aiSheet.getRange(`H2:H${aiRows.length}`).conditionalFormats.add("containsText", { text: "PASS", format: { fill: green, font: { color: "#006100", bold: true } } });
  aiSheet.getRange(`H2:H${aiRows.length}`).conditionalFormats.add("containsText", { text: "FAIL", format: { fill: red, font: { color: "#9C0006", bold: true } } });
  aiSheet.getRange(`K2:K${aiRows.length}`).conditionalFormats.add("containsText", { text: "APPROVE", format: { fill: green, font: { color: "#006100", bold: true } } });
  aiSheet.getRange(`K2:K${aiRows.length}`).conditionalFormats.add("containsText", { text: "REJECT", format: { fill: red, font: { color: "#9C0006", bold: true } } });

  // Feature dictionary: preserve source definition table and add a simple PoC role column.
  const fdHeaders = featureDefs[0] ?? [];
  const fdRows = [ [...fdHeaders, "poc_role"] ];
  for (const row of featureDefs.slice(1)) {
    const joined = row.map(asText).join(" ").toLowerCase();
    let role = "raw support / traceability";
    if (/(age|income|spend|debt|late|telco|employment|asset|financial)/.test(joined)) role = "candidate for profile/rule";
    fdRows.push([...row, role]);
  }
  dictSheet.getRangeByIndexes(0, 0, fdRows.length, fdRows[0].length).values = fdRows;
  const fdEnd = `${colLetter(fdRows[0].length)}${fdRows.length}`;
  setupDataSheet(dictSheet, "07_FEATURE_DICTIONARY", `A1:${fdEnd}`, `A1:${colLetter(fdRows[0].length)}1`, "FeatureDictionary");
  dictSheet.getRange(`A2:${fdEnd}`).format.wrapText = true;
  dictSheet.getRange("A:Z").format.columnWidth = 18;
  dictSheet.getRange(`${colLetter(fdRows[0].length)}:${colLetter(fdRows[0].length)}`).format.columnWidth = 28;

  // Next steps and ownership.
  nextSheet.getRange("A1:F1").merge();
  nextSheet.getRange("A1").values = [["08_NEXT_STEPS — từ PoC sang UI tích hợp"]];
  styleTitle(nextSheet, "A1:F1", navy);
  nextSheet.getRange("A3:F3").values = [["priority", "step", "why", "owner", "status", "evidence / output"]];
  nextSheet.getRange("A4:F11").values = [
    ["P0", "Chốt đơn vị avg_monthly_income / avg_monthly_spend", "Tránh diễn giải sai thang đo", "Data owner", "TODO", "Decision record + cập nhật docs"],
    ["P0", "Review 15 validation warnings", "Invalid range không được biến thành 0", "Data owner + DS", "TODO", "Quy tắc cleaning hoặc giữ invalid"],
    ["P0", "Xác nhận age > 23 là hard rule", "Hard rule ảnh hưởng kết quả quyết định", "Product / risk", "TODO", "Rule decision record"],
    ["P1", "Chạy 8 case x 3 repeats qua OpenRouter", "Đo consistency và conflict detection", "DS/AI", "READY", "evaluation_report.json + AI sheet"],
    ["P1", "Tạo API service dùng profile + rule engine", "Tách research khỏi user application", "Backend", "NEXT", "src/credit_scoring/application"],
    ["P1", "Dựng UI nhập dữ liệu theo feature quan trọng", "Không bắt người dùng nhập 194 cột", "Frontend", "NEXT", "Form → profile request"],
    ["P2", "Bổ sung mapping urban/rural và rule mới", "Mở rộng coverage theo domain", "DS + data owner", "BACKLOG", "Config + unit tests"],
    ["P2", "Code review + test + docs trước demo", "Đảm bảo tái lập và không lẫn pipeline", "Team", "BACKLOG", "ruff + pytest + mkdocs"],
  ];
  styleHeader(nextSheet, "A3:F3");
  styleBody(nextSheet, "A4:F11");
  nextSheet.getRange("A4:F11").format.wrapText = true;
  addTable(nextSheet, "A3:F11", "NextSteps");
  nextSheet.getRange("A:A").format.columnWidth = 10;
  nextSheet.getRange("B:B").format.columnWidth = 42;
  nextSheet.getRange("C:C").format.columnWidth = 40;
  nextSheet.getRange("D:D").format.columnWidth = 20;
  nextSheet.getRange("E:E").format.columnWidth = 14;
  nextSheet.getRange("F:F").format.columnWidth = 34;
  nextSheet.getRange("E4:E11").dataValidation = { rule: { type: "list", values: ["TODO", "READY", "NEXT", "IN_PROGRESS", "DONE", "BACKLOG"] } };
  nextSheet.getRange("E4:E11").conditionalFormats.add("containsText", { text: "TODO", format: { fill: amber, font: { color: "#9C6500", bold: true } } });
  nextSheet.getRange("E4:E11").conditionalFormats.add("containsText", { text: "READY", format: { fill: green, font: { color: "#006100", bold: true } } });
  nextSheet.getRange("E4:E11").conditionalFormats.add("containsText", { text: "BACKLOG", format: { fill: gray, font: { color: dark } } });
  nextSheet.freezePanes.freezeRows(3);

  // A few explicit notes as cells so machine readers can see the same context as humans.
  readme.getRange("E5:H14").values = [
    ["Design rule", "Rule engine quyết định", "AI role", "Explain / conflict / missing"],
    ["Raw fields", rawCols, "Profile fields", profiles[0].length - 1],
    ["Source rows", rawRows, "Warnings", validation.warnings?.length ?? 0],
    ["AI rows", aiRecords.length, "Cases", new Set(aiRecords.map((r) => r.case_id)).size],
    ["Scope", "Synthetic PoC", "Not for", "Production lending decision"],
    ["Missing", "missing", "Invalid", "invalid (not zero)"],
    ["Age rule", "18–23 FAIL", "23–30", "UNKNOWN"],
    ["Age rule", "31–40+ PASS", "Exact age", "direct comparison"],
    ["Output", "Excel UI prototype", "Refresh", "rebuild after pipeline"],
    ["Security", "No API key stored", "Provider", "OpenRouter via env var"],
  ];
  styleHeader(readme, "E5:H5", teal);
  styleBody(readme, "E6:H14");
  readme.getRange("E5:H14").format.wrapText = true;
  readme.getRange("E:E").format.columnWidth = 18;
  readme.getRange("F:F").format.columnWidth = 25;
  readme.getRange("G:G").format.columnWidth = 18;
  readme.getRange("H:H").format.columnWidth = 25;

  // Recalculate and verify before export.
  wb.recalculate();
  const formulaCheck = await wb.inspect({ kind: "formula", sheetId: "01_DASHBOARD", range: "A1:H20", maxChars: 6000, options: { maxResults: 100 } });
  const errorCheck = await wb.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 100 }, maxChars: 4000 });
  console.log("FORMULA_CHECK", formulaCheck.ndjson ?? formulaCheck);
  console.log("ERROR_CHECK", errorCheck.ndjson ?? errorCheck);

  await fs.mkdir(outputDir, { recursive: true });
  const rawToImportantCheck = await wb.inspect({ kind: "table", sheetId: "02_RAW_TO_IMPORTANT", range: "A1:J20", include: "values,formulas", maxChars: 6000, tableMaxRows: 20, tableMaxCols: 10, tableMaxCellChars: 120 });
  console.log("RAW_TO_IMPORTANT_CHECK", rawToImportantCheck.ndjson ?? rawToImportantCheck);

  for (const name of ["00_README", "01_DASHBOARD", "02_RAW_TO_IMPORTANT", "03_PROFILE_FEATURES", "04_VALIDATION", "05_RULE_RESULTS", "06_AI_RESPONSE", "07_FEATURE_DICTIONARY", "08_NEXT_STEPS"]) {
    const preview = await wb.render({ sheetName: name, autoCrop: "all", scale: 1, format: "png" });
    await fs.writeFile(path.join(outputDir, `${name}.png`), new Uint8Array(await preview.arrayBuffer()));
  }
  const xlsx = await SpreadsheetFile.exportXlsx(wb);
  await xlsx.save(outputPath);
  const summary = await wb.inspect({ kind: "workbook,sheet,table", maxChars: 12000, tableMaxRows: 4, tableMaxCols: 8, tableMaxCellChars: 80 });
  await fs.writeFile(path.join(outputDir, "workbook_inspect.txt"), summary.ndjson ?? String(summary), "utf8");
  console.log(JSON.stringify({ outputPath, rawRows, rawCols, importantFields: featureMappings.length, mappedRawColumns: mappedRawColumns.size, profileRows: profiles.length - 1, validationWarnings: validation.warnings?.length ?? 0, ruleRows: ruleRecords.length, aiRows: aiRecords.length }, null, 2));
}

await main();
