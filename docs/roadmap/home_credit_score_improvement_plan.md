# Kế hoạch nâng điểm Home Credit Default Risk

## Mục tiêu

Nâng Home Credit competition score từ baseline application-only E01 bằng một chuỗi
experiment có thể tái lập: multi-table aggregates → domain features → model-derived
features → diverse base models → rank blend/stacking. Ưu tiên OOF AUC ổn định;
leaderboard chỉ dùng làm external sanity check.

## Khái niệm chính

Baseline hiện có dùng 5-fold StratifiedKFold, seed 42, LightGBM trên application
table với OOF AUC `0.768696`. Kế hoạch giữ nguyên metric, folds và population trong
các ablation đầu để mọi chênh lệch có thể quy cho feature/model thay đổi. Các mốc
`0.79` và `0.80+` dưới đây là **target**, không phải kết quả đã đạt.

### Nguyên tắc quyết định

- Một feature block chỉ được giữ khi OOF tăng trên cùng folds, không làm một fold
  xấu đi bất thường và có lineage/test đầy đủ.
- So paired fold delta, OOF prediction delta và runtime; không chỉ nhìn mean fold.
- Public/late-submission score không dùng để chọn giữa nhiều phiên bản gần nhau.
- Không mở stack sâu khi best single multi-table model chưa đạt target trung gian.
- Mọi experiment thật phải có ID, config, artifact và dòng trong experiment log.

### Target ladder

| Mốc | Artifact | Target competition CV | Điều kiện chuyển phase |
|---|---|---:|---|
| E01 hiện tại | Application-only LightGBM | `0.768696` đã xác minh | Baseline khóa |
| M1 | Conventional all-table aggregates | `>= 0.790` | Tất cả join/cardinality tests pass |
| M2 | Recent/state/domain features | `>= 0.797` | Có ablation theo từng feature family |
| M3 | Nested + interest/pseudo-DPD features | `>= 0.800` | Group-aware cross-fitting, không leakage |
| M4 | Diverse models + rank ensemble | `> best single` và hướng tới `0.803+` | Gain OOF ổn định, residual correlation giảm |

Target lấy từ khoảng performance tự báo cáo của các solution công khai và dùng để
định hướng effort. Không được ghi chúng vào baseline results nếu chưa có artifact
thật trong workspace.

### Phase 0 — khóa protocol và artifact contract

1. Lưu folds E01 theo `SK_ID_CURR`, target và seed; mọi experiment sau reuse đúng
   fold assignment.
2. Chuẩn hóa output: config, feature manifest, fold AUC, OOF AUC, best iterations,
   runtime, feature importance, OOF/test predictions và submission checksum.
3. Thêm comparison report: delta OOF so với parent run, paired fold delta, OOF
   correlation, train/test missingness delta và memory/time.
4. Chạy lại E01 từ source hiện tại trước E02. Nếu không tái tạo được, dừng feature
   work và sửa reproducibility trước.

### Phase 1 — conventional multi-table mart

Triển khai reusable modules, không đặt logic quan trọng chỉ trong notebook:

| Block | Feature tối thiểu | Kiểm tra bắt buộc |
|---|---|---|
| Bureau + bureau balance | active/closed counts, debt/credit ratio, overdue, credit type mix, DPD status, recency | unique `SK_ID_BUREAU`, aggregate hai tầng, status semantics |
| Previous application | approved/refused/canceled, amount ratios, last/first, recency, product mix | unique `SK_ID_PREV`, state filter, missing history flag |
| Installments | late days, payment ratio/difference, count/severity/recency of late payments | duplicate installment key, zero denominator, payment timing |
| POS cash | DPD/DPD_DEF, future installments, completion/active status, trend | month ordering, repeated `SK_ID_PREV` |
| Credit card | balance/limit utilization, drawing/payment ratios, DPD, active months | zero credit limit, month ordering |

Mỗi block tạo đúng một dòng per `SK_ID_CURR`, assert uniqueness trước/sau join, và
có unit test cho no-history applicant. Chạy ablation riêng từng block rồi mới chạy
E02 all-table; không gộp mọi thay đổi vào một run.

### Phase 2 — recent, state và domain features

Theo thứ tự ROI:

1. Cửa sổ 90/180/365 ngày và 1/2/3 năm trên cột thời gian thích hợp.
2. Last/first và last 3/5/10 records; recent-k chỉ áp dụng sau sort ổn định.
3. Approved/refused/canceled; active/closed; past-due/not-past-due subsets.
4. DPD buckets 30/60/90/120 và count/max/recency theo bucket.
5. Trend/slope, last-minus-mean, recent-minus-long-term và time-weighted mean.
6. Affordability/utilization: total annuity/income, debt/credit, balance/limit,
   credit/annuity, payment/installment.

Experiment plan:

- E03a recent windows;
- E03b state-conditioned aggregates;
- E03c delinquency/payment ratios;
- E03d trend/weighted features;
- E03e union của các block vượt gate.

Nếu feature count tăng nhanh, dùng gain stability giữa folds và null/permutation
importance để giảm feature; không chọn feature bằng test/leaderboard.

### Phase 3 — model-derived features

#### Nested previous-application và bureau scores

Với mỗi outer fold:

1. Chỉ dùng applicants thuộc outer-train để fit row-level model.
2. Giữ tất cả rows của một `SK_ID_CURR` trong cùng phía của split.
3. Predict rows của outer-validation và test.
4. Aggregate prediction mean/max/min/std/last lên `SK_ID_CURR`.
5. Ghép feature OOF vào application mart.

Thiết kế này tái tạo insight của hạng 3/5/12/17 mà không để rows của cùng applicant
rò target qua folds.

#### Loan term và interest-rate proxy

- Tính interest rate trên previous applications có `CNT_PAYMENT` hợp lệ.
- Fit model dự đoán term/rate chỉ từ các cột tồn tại ở cả previous và current
  application.
- Tạo predicted term, predicted rate, feasible-rate statistics và rate residual so
  với cohort/time proxy.
- Ablate raw rate và standardized rate vì train/test có time/distribution shift.

#### Pseudo DPD target

- Tạo nhiều định nghĩa từ first-Y installments và DPD threshold X.
- Khóa X/Y từ inner CV, không chọn bằng leaderboard.
- Kiểm tra event cutoff và sensitivity; nếu không chứng minh được point-in-time
  availability, giữ feature ở competition-only scope.

### Phase 4 — diversity và ensemble

1. Huấn luyện LGBM trên full feature set và 2–4 core+subset representations.
2. Thêm XGBoost/CatBoost chỉ khi cùng folds và artifact contract được hỗ trợ đầy đủ.
3. Bag seed/feature fraction; không giữ run chỉ vì khác seed nếu OOF gần như trùng.
4. Rank-percent OOF và test predictions theo từng model.
5. Chọn pool bằng hai tiêu chí: AUC đủ mạnh và residual/OOF correlation bổ sung.
6. So sánh theo thứ tự: equal rank average → Ridge/logistic/non-negative linear
   blend → shallow ExtraTrees/LGBM stacker.
7. Mọi stacker chỉ fit trên OOF; test prediction là fold-consistent prediction,
   không train level-2 trên in-sample level-1 predictions.

### Phase 5 — distribution-shift safeguards

- Chạy adversarial validation để tìm feature phân biệt train/test; dùng như
  diagnostic, không làm target chính.
- Báo OOF theo `NAME_CONTRACT_TYPE`, missingness của `EXT_SOURCE`, history/no-history
  và các cohort thời gian suy ra từ bảng lịch sử.
- So model có/không `EXT_SOURCE` như diversity hedge; không thay model chính nếu
  base AUC giảm lớn.
- Cấm manual correction theo public leaderboard và user-ID target lag.
- Chỉ tạo late submission khi OOF experiment đã khóa; lưu submission checksum và
  không dùng nhiều probes để tune weights.

### Kế hoạch thực hiện theo sprint

| Sprint | Deliverable | Experiment dự kiến |
|---|---|---|
| Tuần 1 | Fold artifact, feature API, bureau/bureau-balance và previous-application blocks | Reproduce E01, E02a, E02b |
| Tuần 2 | Installment, POS, credit-card blocks; all-table mart | E02c–E02f, M1 |
| Tuần 3 | Recent/state/domain blocks và feature selection | E03a–E03e, M2 |
| Tuần 4 | Nested scores, predicted term/rate, pseudo DPD | E04a–E04c, M3 |
| Tuần 5 | XGB/CatBoost diversity, rank blend, simple stacker | E05a–E05d, M4 |

Nếu compute hạn chế, bỏ DAE/CNN/RNN và stack nhiều tầng. Thứ tự không đổi: strong
single model trước, diverse OOF sau.

## Ví dụ trong credit scoring

E03c có thể kiểm tra giả thuyết: “late-payment severity trong 365 ngày gần nhất bổ
sung tín hiệu ngoài application-only baseline”. Parent là E02 all-table. Chỉ thay
feature block installment recent-window, reuse folds E01, xuất OOF và paired fold
delta. Kết luận chỉ được ghi sau khi run thật hoàn tất.

## Điều cần kiểm tra trong project

- [ ] Tái tạo E01 trước khi bắt đầu E02.
- [ ] Mỗi feature có source, formula, owner, cutoff và test.
- [ ] Cập nhật `catalogs/feature_registry.yaml` khi feature được triển khai.
- [ ] Cập nhật `docs/experiments/experiment_log.md` sau mỗi run thật.
- [ ] Tạo decision record nếu metric hoặc validation strategy thay đổi.
- [ ] Chạy `ruff check .`, `pytest` và `mkdocs build --strict` trước bàn giao code.
- [ ] Không commit raw Home Credit data, predictions chứa PII hoặc dữ liệu FPT.

## Tài liệu liên quan

- [Tổng hợp solution write-ups](../references/home_credit_solution_writeups.md)
- [Home Credit dataset card](../datasets/home_credit_default_risk.md)
- [Home Credit application features](../features/home_credit_application_features.md)
- [Home Credit validation](../evaluation/home_credit_validation.md)
- [Multi-table checklist](../checklists/stage_03_multitable_features.md)
- [Experiment log](../experiments/experiment_log.md)

## Trạng thái áp dụng trong project

Plan được tạo ngày 2026-08-03 từ 28 write-ups và baseline E01. Chưa có feature hoặc
experiment mới được triển khai; các target M1–M4 đang ở trạng thái planned.
