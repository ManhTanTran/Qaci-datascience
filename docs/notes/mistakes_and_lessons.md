# Sai lầm và bài học

## Mục tiêu

Lưu failure pattern có thể tái sử dụng mà không ghi dữ liệu nhạy cảm hoặc kết quả giả.

## Khái niệm chính

Mỗi entry nên có bối cảnh, dấu hiệu, nguyên nhân, cách phát hiện, cách ngăn tái diễn và link tới test/decision.

## Mẫu ghi chép

- **Ngày/Stage:**
- **Hiện tượng:**
- **Nguyên nhân:**
- **Ảnh hưởng:**
- **Cách phát hiện:**
- **Cách khắc phục:**
- **Regression test hoặc tài liệu liên quan:**

Các failure pattern ưu tiên: leakage sau decision, duplicate grain, fit preprocessing trước split, dùng test để chọn feature, đánh đồng missing với zero và đọc importance như causality.

## Ví dụ trong credit scoring

Nếu join installments làm tăng số dòng application, bài học phải ghi cardinality assumption và thêm uniqueness test trước/sau join.

## Điều cần kiểm tra trong project

- [ ] Không ghi PII hoặc raw customer value.
- [ ] Link tới artifact có thể kiểm chứng.
- [ ] Không bịa metric hoặc kết luận.

## Tài liệu liên quan

- [Leakage checklist](../features/leakage_checklist.md)
- [Reproducibility](../governance/reproducibility.md)
- [Experiment log](../experiments/experiment_log.md)

## Trạng thái áp dụng trong project

Chưa có entry thực nghiệm; chỉ có template và failure patterns cần theo dõi.
