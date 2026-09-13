# Home Credit bureau Spark parity

## Mục tiêu

Ghi nhận đường dẫn tài liệu cho module Spark parity được tham chiếu bởi các tài
liệu bureau hiện có.

## Khái niệm chính

Module Spark là research/engineering support cho kiểm tra parity với implementation
Pandas; nó không thay thế validation hoặc governance của model.

## Ví dụ trong credit scoring

Có thể đối chiếu schema, cardinality và aggregate ở grain `SK_ID_CURR` trước khi
đưa block feature vào experiment.

## Điều cần kiểm tra trong project

- [ ] Kiểm tra source/cut-off và cardinality sau mỗi aggregate.
- [ ] Không coi kết quả parity là metric model hoặc production approval.
- [ ] Ghi experiment/decision record khi thay đổi validation.

## Tài liệu liên quan

- [Feature store](feature_store.md)
- [Bureau features](bureau_features.md)
- [Feature engineering](feature_engineering.md)

## Trạng thái áp dụng trong project

Đây là tài liệu tham chiếu kỹ thuật. Mọi quyết định production của FPT vẫn là
`TODO(FPT): cần xác nhận với mentor hoặc data owner.`
