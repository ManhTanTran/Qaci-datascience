# Checklist stage 00 — Foundation

## Mục tiêu

Xác nhận người học hiểu đúng bài toán credit scoring trước khi xử lý dữ liệu.

## Khái niệm chính

Stage chỉ hoàn thành khi có thể giải thích target, grain, observation point, performance horizon và feature availability bằng ngôn ngữ nghiệp vụ.

## Checklist hoàn thành

- [ ] Phân biệt default, delinquency và DPD30/60/90.
- [ ] Phân biệt PD, credit score, bad rate và approval rate.
- [ ] Phân biệt application scoring với behavioral scoring.
- [ ] Viết target specification gồm event, horizon, population và exclusions.
- [ ] Vẽ timeline observation window → decision time → performance window.
- [ ] Nêu ba ví dụ leakage và cách ngăn chặn.

## Ví dụ trong credit scoring

Giải thích được vì sao một khoản 30 DPD không mặc định đồng nghĩa default nếu target định nghĩa 90+ DPD.

## Điều cần kiểm tra trong project

- [ ] Không tự điền chính sách FPT.
- [ ] Dùng glossary thống nhất trong code và docs.
- [ ] Ghi câu hỏi chưa rõ vào notes.

## Tài liệu liên quan

- [Stage 00](../learning/00_credit_scoring_foundation.md)
- [Glossary](../domain/glossary.md)
- [Target](../domain/target_definition.md)
- [Window](../domain/observation_performance_window.md)

## Trạng thái áp dụng trong project

TODO(FPT): cần xác nhận với mentor hoặc data owner.
