# Thuật ngữ

## Mục tiêu

Chuẩn hóa ngôn ngữ dùng trong tài liệu, code và trao đổi với stakeholder.

## Khái niệm chính

Bảng dưới đây là định nghĩa chuẩn dùng trong tài liệu, code và trao đổi với stakeholder. Khi triển khai thực tế, ngưỡng và horizon cụ thể vẫn phải được business/risk phê duyệt.

| Thuật ngữ | Định nghĩa |
| --- | --- |
| **Default** | Khách hàng vỡ nợ hoặc quá hạn nghiêm trọng theo tiêu chí target đã được phê duyệt. |
| **Delinquency** | Tình trạng trả chậm nghĩa vụ tín dụng; đây là trạng thái có thể được đo bằng số ngày quá hạn và các ngưỡng tương ứng. |
| **DPD (Days Past Due)** | Số ngày quá hạn của một nghĩa vụ thanh toán tại thời điểm đo. |
| **DPD30 / DPD60 / DPD90** | Các ngưỡng delinquency từ 30, 60 hoặc 90 ngày quá hạn trở lên. Cần ghi rõ đó là trạng thái tại một thời điểm, số lần chạm ngưỡng hay event trong một window. |
| **PD (Probability of Default)** | Xác suất khách hàng vỡ nợ trong một performance window/horizon đã xác định, có điều kiện theo population và thời điểm dự đoán. |
| **Credit score** | Điểm được chuyển đổi từ mức rủi ro (ví dụ từ PD hoặc log-odds) để xếp hạng và hỗ trợ quyết định tín dụng. |
| **Bad rate** | Tỷ lệ khách hàng xấu trong một tập quan sát: số khách hàng có nhãn bad chia cho tổng số khách hàng đủ điều kiện và đã trưởng thành nhãn. |
| **Approval rate** | Tỷ lệ hồ sơ được phê duyệt trên tổng số hồ sơ đủ điều kiện được đưa ra quyết định trong cùng population và khoảng thời gian. |
| **Observation window** | Khoảng thời gian lấy feature, kết thúc tại observation/as-of/decision time; chỉ dùng thông tin sẵn có tại mốc này. |
| **Performance window** | Khoảng thời gian quan sát target sau observation/as-of/decision time, dùng để xác định khách hàng có trở thành bad hay không. |
| **Application scoring** | Chấm điểm tại thời điểm khách hàng đăng ký vay, sử dụng thông tin có sẵn trước hoặc tại thời điểm ra quyết định. |
| **Behavioral scoring** | Chấm điểm dựa trên hành vi sau khi khách hàng đã sử dụng tín dụng, chẳng hạn lịch sử thanh toán và mức sử dụng hạn mức. |
| **Application time** | Thời điểm thông tin hợp lệ để ra quyết định. |
| **Bad** | Outcome theo target definition; không mặc định đồng nhất với mọi mức delinquency. |
| **OOT (Out-of-time)** | Tập kiểm định ở giai đoạn tương lai so với dữ liệu huấn luyện. |
| **Leakage** | Thông tin không sẵn có tại thời điểm dự đoán nhưng bị dùng làm feature. |
| **PSI (Population Stability Index)** | Chỉ số đo dịch chuyển phân phối của một biến hoặc score theo các bin giữa hai quần thể/thời điểm. |



## Ví dụ trong credit scoring

Không dùng từ “default” nếu target thực tế chỉ là một proxy delinquency mà chưa ghi rõ.

## Điều cần kiểm tra trong project

- [ ] Xác nhận thuật ngữ với business và risk.
- [ ] Gắn định nghĩa với population và thời điểm.
- [ ] Ghi rõ giả định, owner và version.

## Tài liệu liên quan

- [Trang chủ](../index.md)
- [Target](target_definition.md)
- [Window](observation_performance_window.md)
- [Business metrics](business_metrics.md)

## Trạng thái áp dụng trong project

TODO(FPT): cần xác nhận với mentor hoặc data owner.
