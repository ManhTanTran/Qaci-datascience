# Stage 00 — Credit scoring foundation

## Mục tiêu

Nắm ngôn ngữ và cấu trúc thời gian của bài toán trước khi mở dataset hoặc xây model.

## Khái niệm chính

Cần giải thích được default, delinquency, DPD30/60/90, PD, credit score, bad rate, approval rate, observation window, performance window, application scoring và behavioral scoring.

## Kiến thức và điều kiện hoàn thành

- Phân biệt default với delinquency và từng ngưỡng DPD.
- Mô tả target bằng event, horizon, population, observation point và exclusions.
- Trả lời một dòng dữ liệu đại diện cho ai/cái gì và ở thời điểm nào.
- Chỉ ra feature nào sẵn có tại decision time và target được quan sát trong khoảng nào.
- Phân biệt PD với score và phân biệt ranking metric với calibration/business metric.

## Ví dụ trong credit scoring

Một DPD phát sinh sau ngày quyết định có thể dùng để tạo target trong performance window nhưng không được dùng làm feature của application model.

## Điều cần kiểm tra trong project

- [ ] Hoàn thành [stage 00 checklist](../checklists/stage_00_foundation.md).
- [ ] Không dùng “default” thay cho một proxy delinquency chưa được định nghĩa.
- [ ] Không tự chọn target hoặc DPD threshold cho dữ liệu FPT.

## Tài liệu liên quan

- [Glossary](../domain/glossary.md)
- [Target definition](../domain/target_definition.md)
- [Observation/performance window](../domain/observation_performance_window.md)
- [Credit score và PD](../domain/credit_score_vs_pd.md)

## Trạng thái áp dụng trong project

TODO(FPT): cần xác nhận với mentor hoặc data owner.
