"""Generate the auxiliary-feature documentation from the aggregation specs.

The registry rule allows registering features by family only when the linked
document lists every feature with its source column, formula and missing policy.
Writing 261 rows by hand would drift from the code on the first edit, so the page
is generated from the same Aggregation declarations the builders execute.
"""

import json
import re
from pathlib import Path

from credit_scoring.features import home_credit_bureau as bureau
from credit_scoring.features import home_credit_credit_card as credit_card
from credit_scoring.features import home_credit_installments as installments
from credit_scoring.features import home_credit_pos_cash as pos_cash
from credit_scoring.features import home_credit_previous_application as previous

OUT = Path(r"D:\Work\FPT\Data science\docs\features\home_credit_auxiliary_features.md")

STAT_FORMULA = {
    "count": "Đếm số dòng trong nhóm",
    "last": "Giá trị của dòng cuối sau khi sắp xếp",
    "max": "Giá trị lớn nhất",
    "mean": "Trung bình các giá trị quan sát được",
    "min": "Giá trị nhỏ nhất",
    "nunique": "Số giá trị khác nhau",
    "std": "Độ lệch chuẩn",
    "sum": "Tổng chỉ báo; nhóm không có dòng nào là 0",
    "sum_observed": "`sum(min_count=1)`; không quan sát được giá trị nào thì NaN",
    "var": "Phương sai",
}
STAT_MISSING = {
    "count": "Fill 0",
    "sum": "Fill 0",
    "sum_observed": "NaN nếu không có giá trị quan sát được",
}

BLOCKS = [
    (
        "bureau",
        bureau,
        "`bureau.csv`, `bureau_balance.csv`",
        [
            ("_BALANCE_AGGREGATIONS", "SK_ID_BUREAU", ""),
            ("_RECENT_BALANCE_AGGREGATIONS", "SK_ID_BUREAU (6 tháng gần nhất)", ""),
            ("_BUREAU_AGGREGATIONS", "SK_ID_CURR", "BUREAU_"),
            ("_ACTIVE_AGGREGATIONS", "SK_ID_CURR (chỉ loan Active)", "BUREAU_"),
        ],
    ),
    (
        "previous_application",
        previous,
        "`previous_application.csv`",
        [
            ("_AGGREGATIONS", "SK_ID_CURR", "PREV_"),
            ("_APPROVED_AGGREGATIONS", "SK_ID_CURR (chỉ đơn Approved)", "PREV_"),
        ],
    ),
    (
        "installments",
        installments,
        "`installments_payments.csv`",
        [
            ("_LOAN_AGGREGATIONS", "SK_ID_PREV", ""),
            ("_CLIENT_AGGREGATIONS", "SK_ID_CURR", "INST_"),
            ("_LIFETIME_AGGREGATIONS", "SK_ID_CURR", ""),
        ],
    ),
    (
        "credit_card",
        credit_card,
        "`credit_card_balance.csv`",
        [
            ("_CARD_AGGREGATIONS", "SK_ID_PREV", ""),
            ("_CLIENT_AGGREGATIONS", "SK_ID_CURR", "CC_"),
            ("_RECENT_AGGREGATIONS", "SK_ID_CURR (6 tháng gần nhất)", "CC_"),
        ],
    ),
    (
        "pos_cash",
        pos_cash,
        "`POS_CASH_balance.csv`",
        [
            ("_CONTRACT_AGGREGATIONS", "SK_ID_PREV", ""),
            ("_CLIENT_AGGREGATIONS", "SK_ID_CURR", "POS_"),
            ("_RECENT_AGGREGATIONS", "SK_ID_CURR (6 tháng gần nhất)", "POS_"),
        ],
    ),
]

lines = [
    "# Home Credit auxiliary-table research features",
    "",
    "## Mục tiêu",
    "",
    "Đăng ký toàn bộ research candidate sinh từ năm bảng phụ Home Credit tại grain",
    "`SK_ID_CURR`. Trang này được **sinh tự động từ khai báo `Aggregation` trong",
    "source**, nên công thức ở đây luôn khớp với code đang chạy. Đây là research",
    "candidate, không phải feature production.",
    "",
    "## Khái niệm chính",
    "",
    "Mỗi feature sinh ra từ một cột nguồn và một thống kê. Tên cột đầu ra ghép theo",
    "quy tắc `{prefix}{tên}_{THỐNG_KÊ}`.",
    "",
    "Hai loại tổng được phân biệt rõ:",
    "",
    "- `SUM` cộng cột chỉ báo. Nhóm không có dòng nào cho 0, vì \"không có bản ghi",
    "  nào\" là sự thật chứ không phải thiếu dữ liệu.",
    "- `SUM_OBSERVED` cộng đại lượng đo được bằng `sum(min_count=1)`. Nhóm không",
    "  quan sát được giá trị nào giữ `NaN`, để \"không biết nợ bao nhiêu\" không bị",
    "  nhập làm một với \"nợ bằng 0\".",
    "",
    "Ratio dùng `credit_scoring.numeric.safe_divide`: mẫu số bằng 0 hoặc missing đều",
    "trả `NaN`, không clip, không tạo cờ denominator.",
    "",
    "Danh sách category là cố định, khai trong source. Giá trị ngoài danh sách gom",
    "vào `OTHER`. Nhờ vậy tập cột đầu ra giống nhau khi chạy trên mẫu và trên full",
    "data — đã kiểm chứng: cả năm block cho đúng cùng số cột ở 7.000 khách và ở hơn",
    "300.000 khách.",
    "",
]

total = 0
documented_names: set[str] = set()
for name, module, sources, groups in BLOCKS:
    lines += [
        f"## Block `{name}`",
        "",
        f"Nguồn: {sources}. `builder_version`: `{module.BUILDER_VERSION}`.",
        "",
    ]
    for attr, grain, prefix in groups:
        specs = getattr(module, attr, None)
        if not specs:
            continue
        lines += [
            f"### Gom theo {grain}",
            "",
            "| Feature | Cột nguồn | Công thức | Missing policy | Family |",
            "|---|---|---|---|---|",
        ]
        for spec in specs:
            for stat, output in zip(spec.stats, spec.output_names(prefix), strict=True):
                policy = STAT_MISSING.get(stat, "Giữ NaN nếu không có giá trị")
                lines.append(
                    f"| `{output}` | `{spec.column}` | {STAT_FORMULA[stat]} "
                    f"| {policy} | {spec.family} |"
                )
                documented_names.add(output)
                total += 1
        lines.append("")

# ── Derived columns computed after aggregation ────────────────────────────────
# These are not Aggregation specs, so they are described by rule. Every manifest
# column must match exactly one rule; an unmatched column fails the run rather
# than quietly leaving a feature undocumented.
NAN = "Mẫu số 0 hoặc missing → NaN"
DERIVED_RULES: list[tuple[str, str, str, str]] = [
    (
        r"^BUREAU_CTYPE_(.+)_COUNT$",
        "`CREDIT_TYPE`",
        "Đếm loan có `CREDIT_TYPE` bằng `{0}`; giá trị ngoài danh sách khai báo gom vào `OTHER`",
        "Fill 0",
    ),
    (
        r"^PREV_CONTRACT_(.+)_COUNT$",
        "`NAME_CONTRACT_TYPE`",
        "Đếm đơn có `NAME_CONTRACT_TYPE` bằng `{0}`; ngoài danh sách gom vào `OTHER`",
        "Fill 0",
    ),
    (
        r"^PREV_YIELD_(.+)_COUNT$",
        "`NAME_YIELD_GROUP`",
        "Đếm đơn có `NAME_YIELD_GROUP` bằng `{0}`; ngoài danh sách gom vào `OTHER`",
        "Fill 0",
    ),
    (
        r"^BUREAU_LOANS_WITH_DPD_COUNT$",
        "`STATUS` qua `SK_ID_BUREAU`",
        "Đếm loan có ít nhất một tháng DPD",
        "Fill 0",
    ),
    (
        r"^BUREAU_ACTIVE_LOAN_RATIO$",
        "Hai count phía trên",
        "`safe_divide(ACTIVE_LOAN_COUNT, LOAN_COUNT)`",
        NAN,
    ),
    (
        r"^BUREAU_ACTIVE_UTILIZATION$",
        "Debt/credit của loan Active",
        "`safe_divide(ACTIVE_DEBT_SUM, ACTIVE_CREDIT_SUM)`",
        NAN,
    ),
    (
        r"^BUREAU_DEBT_CREDIT_RATIO_TOTAL$",
        "Tổng debt và tổng credit",
        "`safe_divide(AMT_CREDIT_SUM_DEBT_SUM, AMT_CREDIT_SUM_SUM)`",
        NAN,
    ),
    (
        r"^BUREAU_OVERDUE_DEBT_RATIO_TOTAL$",
        "Tổng overdue và tổng debt",
        "`safe_divide(AMT_CREDIT_SUM_OVERDUE_SUM, AMT_CREDIT_SUM_DEBT_SUM)`",
        NAN,
    ),
    (
        r"^CC_PORTFOLIO_(BALANCE|LIMIT)$",
        "`AMT_BALANCE`, `AMT_CREDIT_LIMIT_ACTUAL`",
        "`sum(min_count=1)` trên snapshot cuối của mỗi thẻ",
        "NaN nếu không có giá trị quan sát được",
    ),
    (
        r"^CC_PORTFOLIO_UTILIZATION$",
        "Hai cột portfolio phía trên",
        "`safe_divide(PORTFOLIO_BALANCE, PORTFOLIO_LIMIT)`; ratio của tổng, không phải trung bình của ratio",
        NAN,
    ),
    (
        r"^POS_CONTRACTS_WITH_DPD_COUNT$",
        "`SK_DPD` qua `SK_ID_PREV`",
        "Đếm hợp đồng có ít nhất một tháng DPD",
        "Fill 0",
    ),
    (
        r"^POS_COMPLETION_RATE$",
        "Hai count hợp đồng",
        "`safe_divide(COMPLETED_SUM, CONTRACT_COUNT)`",
        NAN,
    ),
    (
        r"^POS_DPD_CONTRACT_RATIO$",
        "Hai count hợp đồng",
        "`safe_divide(CONTRACTS_WITH_DPD_COUNT, CONTRACT_COUNT)`",
        NAN,
    ),
    (
        r"^INST_LOANS_WITH_LATE_COUNT$",
        "`IS_LATE` qua `SK_ID_PREV`",
        "Đếm khoản vay có ít nhất một kỳ trả trễ",
        "Fill 0",
    ),
    (
        r"^INST_LATE_RATE_LIFETIME$",
        "`IS_LATE`, `NUM_INSTALMENT_NUMBER`",
        "`safe_divide(LATE_LIFETIME_SUM, COUNT_LIFETIME_COUNT)`",
        NAN,
    ),
    (
        r"^INST_LATE_RATE_(\d+)D$",
        "`IS_LATE`, `NUM_INSTALMENT_NUMBER`",
        "`safe_divide` số kỳ trễ trên số kỳ, trong cửa sổ {0} ngày gần nhất",
        NAN,
    ),
    (
        r"^INST_DPD_RECENT_MINUS_LIFE_(\d+)D$",
        "`DPD`",
        "DPD trung bình {0} ngày gần nhất trừ DPD trung bình toàn bộ; dương là xấu đi",
        "NaN nếu thiếu một trong hai vế",
    ),
    (
        r"^INST_LATE_RATE_RECENT_MINUS_LIFE_(\d+)D$",
        "`IS_LATE`",
        "Tỷ lệ trễ {0} ngày gần nhất trừ tỷ lệ trễ toàn bộ; dương là xấu đi",
        "NaN nếu thiếu một trong hai vế",
    ),
    (
        r"^INST_(DPD|PAYMENT_RATIO|LATE|UNDERPAYMENT)_(\d+)D_(MEAN|MAX|SUM)$",
        "`DPD`, `PAYMENT_RATIO`, `IS_LATE`, `UNDERPAYMENT`",
        "Thống kê `{2}` của `{0}` trong cửa sổ {1} ngày gần nhất",
        "Fill 0 với SUM chỉ báo; còn lại NaN",
    ),
    (
        r"^INST_(\d+)D_COUNT$",
        "`NUM_INSTALMENT_NUMBER`",
        "Số kỳ trả trong cửa sổ {0} ngày gần nhất",
        "Fill 0",
    ),
    (
        r"^INST_LAST(\d+)_(DPD|PAYMENT_RATIO|LATE)_(MEAN|MAX|SUM)$",
        "`DPD`, `PAYMENT_RATIO`, `IS_LATE`",
        "Thống kê `{2}` của `{1}` trên {0} kỳ trả gần nhất",
        "NaN nếu không có kỳ nào",
    ),
    (
        r"^INST_(DPD|PAYMENT_RATIO)_TREND_SLOPE$",
        "`{0}`",
        "Hệ số góc OLS trên 20 kỳ gần nhất, sắp xếp cũ trước; dương nghĩa là tăng dần theo thời gian",
        "NaN nếu dưới hai quan sát",
    ),
    (
        r"^INST_DAYS_SINCE_LAST_LATE$",
        "`DAYS_INSTALMENT`, `IS_LATE`",
        "`-MAX(DAYS_INSTALMENT)` trên các kỳ trả trễ",
        "NaN nếu chưa từng trả trễ",
    ),
    (
        r"^PREV_RECENT_REFUSAL_COUNT$",
        "`NAME_CONTRACT_STATUS`, `DAYS_DECISION`",
        "Đếm đơn bị từ chối trong 365 ngày gần nhất",
        "Fill 0",
    ),
    (
        r"^PREV_HAS_RECENT_REFUSAL$",
        "Count phía trên",
        "`RECENT_REFUSAL_COUNT > 0`",
        "Không có missing",
    ),
    (
        r"^PREV_AMT_APPLICATION_TREND$",
        "`AMT_APPLICATION`, `DAYS_DECISION`",
        "Hệ số góc OLS trên 5 đơn gần nhất, sắp xếp cũ trước; dương là xin vay ngày càng nhiều",
        "NaN nếu dưới hai đơn",
    ),
]

lines += ["## Cột phái sinh tính sau khi aggregate", ""]
undocumented: list[str] = []
for name, module, _sources, _groups in BLOCKS:
    manifest = json.loads(
        (Path(r"D:\Work\FPT\Data science\data\feature_store") / f"{name}.manifest.json").read_text(
            encoding="utf-8"
        )
    )
    already = {n for n in documented_names}
    rows = []
    for entry in manifest["features"]:
        if entry["name"] in already:
            continue
        for pattern, source, formula, policy in DERIVED_RULES:
            match = re.match(pattern, entry["name"])
            if match:
                rows.append(
                    f"| `{entry['name']}` | {source} | "
                    f"{formula.format(*match.groups())} | {policy} | {entry['family']} |"
                )
                total += 1
                break
        else:
            undocumented.append(entry["name"])
    if rows:
        lines += [
            f"### Block `{name}`",
            "",
            "| Feature | Cột nguồn | Công thức | Missing policy | Family |",
            "|---|---|---|---|---|",
            *rows,
            "",
        ]

if undocumented:
    raise SystemExit(f"Features with no documentation rule: {undocumented}")

lines += [
    "## Ví dụ trong credit scoring",
    "",
    "`BUREAU_AMT_CREDIT_SUM_DEBT_SUM` dùng `SUM_OBSERVED`. Trong 5.000 khách lấy",
    "mẫu có 157 khách mà mọi bản ghi Bureau đều không ghi dư nợ; họ giữ `NaN` ở cả",
    "`SUM`, `MEAN` và `MAX`. Nếu `SUM` trả `0` thì cùng một khách sẽ vừa \"nợ bằng",
    "0\" theo cột tổng vừa \"không rõ\" theo cột trung bình, và model học được một",
    "quan hệ do lỗi tạo ra chứ không có thật.",
    "",
    "## Điều cần kiểm tra trong project",
    "",
    "- [x] Mỗi feature có cột nguồn, công thức, missing policy và family.",
    "- [x] Schema không đổi giữa mẫu nhỏ và full data, có test bảo vệ.",
    "- [x] Cardinality `SK_ID_CURR` duy nhất sau mỗi builder, có test bảo vệ.",
    "- [x] Tên feature không chứa ký tự LightGBM từ chối.",
    "- [ ] Chạy paired ablation trước khi kết luận feature nào đáng giữ.",
    "- [ ] Promote lên production cần review riêng và owner.",
    "",
    "## Tài liệu liên quan",
    "",
    "- [Feature store](feature_store.md)",
    "- [Home Credit Bureau features](home_credit_bureau_features.md)",
    "- [Feature engineering](feature_engineering.md)",
    "- [ADR-0004](../decisions/0004-auxiliary-feature-modules-in-source.md)",
    "",
    "## Trạng thái áp dụng trong project",
    "",
    "Research candidate. Đã build trên full data thành năm block Parquet; chưa có",
    "paired ablation nên chưa feature nào được chọn hay loại. Không thuộc E03.",
    "",
]

OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"wrote {OUT} — {total} feature rows")
