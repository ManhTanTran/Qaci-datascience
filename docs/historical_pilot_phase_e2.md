# Phase E2 — pilot dataset lịch sử TiniX AI

**Ngày thực hiện:** 2026-10-14  
**Mục đích:** nghiên cứu/học tập phi thương mại, do project owner xác nhận.  
**Dataset:** [TiniX AI `vietnam-real-estates`](https://huggingface.co/datasets/tinixai/vietnam-real-estates), [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/).  
**Revision:** `ca3fedcbb089bf65f7e4cfb03316cce4bd0d779f`.

## Kết quả chính

| Kiểm tra | Kết quả |
|---|---:|
| Hàng tải qua Dataset Viewer `/rows` | 1.000 |
| Tổng số hàng theo nguồn | 3.500.744 |
| Hàng khớp exact tỉnh + quận/huyện cũ + phường/xã trong Top 50 | 113, trên 43 target rank |
| Ứng viên hợp lệ về địa bàn, tiêu đề, giá, diện tích, ngày đăng | 106 |
| Ứng viên đã lưu trong pilot DB | 106, trên 42 target rank |
| Ứng viên đủ điều kiện thống kê lịch sử | 43, trên 31 target rank |
| Bị quarantine do thiếu giá | 7 |
| Ngoài whitelist Top 50 | 887 |
| Trùng nội dung trong mẫu đầu tiên | 0 |
| Lượt chạy lại | 1.000 source rows được nhận diện lại; candidate/observation vẫn 106/106 |
| Observation lịch sử | 106 |
| Nhóm thống kê theo target + loại + tháng | 40 |

Trong 106 ứng viên, 45 tiêu đề có tín hiệu bán rõ, 1 tiêu đề có tín hiệu cho
thuê và 60 không đủ căn cứ phân biệt giao dịch. Có 16 ứng viên thuộc loại tài
sản chưa ánh xạ rõ; các nhóm này có thể chồng với trạng thái giao dịch. Chỉ 43
ứng viên vừa có tiêu đề bán rõ, vừa thuộc `NHA_RIENG` hoặc `CHUNG_CU`. Dataset
không có transaction-type field; 60 dòng chưa rõ không bị gán bán/thuê theo suy
đoán.

Trong số 113 hàng khớp địa bàn, 7 thiếu giá và không được lưu thành candidate;
106 còn lại có giá, diện tích, tiêu đề và ngày đăng hợp lệ. Mẫu có candidate ở
42/50 target; một target được khớp địa lý nhưng các hàng của nó thiếu giá. Bảy
target không xuất hiện trong mẫu không đồng nghĩa không có tin trên dataset.

## Thống kê — không gộp loại tài sản

Chỉ các tiêu đề nêu rõ bán và property type ánh xạ được mới tính. Giá/m² được
tính bằng Python từ `price / area`.

| Loại | Số tin | Mean (VND/m²) | Median (VND/m²) | Min (VND/m²) | Max (VND/m²) |
|---|---:|---:|---:|---:|---:|
| `NHA_RIENG` | 31 | 141.817.321,48 | 104.166.666,67 | 38.567.493,11 | 333.333.333,33 |
| `CHUNG_CU` | 12 | 76.271.401,64 | 79.396.802,33 | 20.559.646,54 | 123.188.405,80 |
| `DAT_O` | 0 | — | — | — | — |

Nguồn ghi `Đất` nhưng định nghĩa gồm đất ở hoặc đất thương mại, nên không thể
đưa nhóm này vào `DAT_O` khi chưa có dữ liệu phân biệt. Các mức trên là mô tả
mẫu giá rao lịch sử, không phải giá giao dịch hay giá hiện hành.

## Kiểm thử lưu trữ và UI

- Pilot DB: `state/ward_prices.historical_pilot.sqlite3`; riêng biệt với
  `state/ward_prices.sqlite3` và `state/ward_prices.demo.sqlite3`.
- Có 50 dòng trong `historical_target_registry`, 106 candidate, 106
  `historical_observations`, 40 nhóm `historical_monthly_statistics`, 7 quarantine
  và hai bản ghi `historical_import_runs`.
- Tính lại độc lập bằng Python khớp mean/median/min/max và count của cả 40 nhóm
  tháng. Không có sai khác giữa `price / area` và `price_per_m2`.
- Import lại toàn bộ sample không tăng candidate, observation hoặc nhóm thống kê.
- Production và demo DB được đối chiếu SHA-256 trước/sau; không thay đổi. Production
  vẫn giữ 50 target và 0 canonical listing/observation/statistic.
- FastAPI pilot UI/API: `/historical-pilot`, `/api/v1/research/historical/overview`,
  `/targets` và `/lookup` trả HTTP 200. Lookup rank 2, `NHA_RIENG`: 3 candidate,
  2 đủ điều kiện thống kê; mean 147.180.134,68 VND/m². UI có attribution TiniX AI,
  link license, nhãn nghiên cứu phi thương mại và giới hạn “không có URL tin riêng”.
- Đường dẫn UI: `http://127.0.0.1:8768/historical-pilot`.

`CURRENT_VERIFIED`, `DAILY_NEW`, crawler, Gemini live, Gmail và Task Scheduler
không được sử dụng trong pilot.

## Schema và giới hạn provenance

Schema có 19 trường nhưng không có `transaction_type`, `listing_type`, listing
URL hay ID gốc. `name` chỉ đủ để nhận diện một số tiêu đề nêu rõ “bán” hoặc “cho
thuê”; dòng còn lại để `UNCLASSIFIED`. Không có nguồn trang tin riêng để đối
chiếu giá, diện tích và địa chỉ. Tất cả candidate giữ
`HISTORICAL_DATASET_UNVERIFIED`; link dataset không được coi là citation cho một
tin riêng.

Downloader giữ mẫu 1.000 hàng trong `data/historical_pilot/` và metadata có
revision, field schema, offset, cách lấy mẫu, license và attribution. Mẫu được
lấy theo đoạn chỉ số trải đều, không phải mẫu xác suất đại diện thị trường.

## Tiếp tục mở rộng theo batch

Chỉ mở rộng sau khi rà soát pilot và quyền dùng. Nếu được xác nhận tiếp:

1. Lấy batch kế tiếp theo cùng revision, giới hạn 1.000–5.000 hàng mỗi batch qua
   `/rows`; không tải full Parquet trước khi đánh giá lại mức cần thiết.
2. Lưu manifest revision, offset, SHA-256 và attribution từng batch.
3. Import dry-run; xem tỷ lệ exact match, field completeness, duplicate, trạng
   thái deal/property trước khi ghi pilot DB.
4. Giữ chính sách whitelist exact triple và không map `Đất` sang `DAT_O` nếu
   dataset vẫn không phân biệt loại đất.
5. Mở rộng riêng pilot DB; đánh giá bias của mẫu theo địa bàn/thời gian trước khi
   sử dụng thống kê rộng hơn.
6. Không promote sang production/AI context hoặc dùng thương mại nếu chưa có
   review riêng và quyền phù hợp.

## Tài liệu tham khảo

- [Dataset card TiniX AI](https://huggingface.co/datasets/tinixai/vietnam-real-estates)
- [Hugging Face Dataset Viewer `/rows` API](https://huggingface.co/docs/dataset-viewer/en/rows)
- [CC BY-NC 4.0 legal code](https://creativecommons.org/licenses/by-nc/4.0/legalcode.en)
- [Dataset card trong project](datasets/tinixai_vietnam_real_estates.md)
