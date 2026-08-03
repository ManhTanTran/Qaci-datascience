# Home Credit Default Risk — tổng hợp solution write-ups

## Mục tiêu

Tổng hợp 28 bài viết và repository được chia sẻ sau cuộc thi Home Credit Default
Risk, tách các kỹ thuật có thể tái tạo khỏi các thủ thuật dễ leakage hoặc overfit
leaderboard, và rút ra các ưu tiên phù hợp với baseline hiện có của project.

## Khái niệm chính

Các con số CV, public leaderboard và private leaderboard dưới đây là số do tác giả
tự báo cáo trong bài viết năm 2018. Chúng không phải kết quả đã được tái tạo trong
repository này. Kết quả đã xác minh duy nhất của project vẫn là E01: OOF AUC
`0.768696`, Kaggle `Score` `0.76312` và public `0.76634`.

### Kết luận xuyên suốt

1. **Feature engineering nhiều bảng tạo phần lớn mức tăng.** Các đội mạnh đều đưa
   từng bảng phụ về grain `SK_ID_CURR`, nhưng không chỉ aggregate toàn lịch sử. Họ
   còn tách theo trạng thái, cửa sổ thời gian, bản ghi gần nhất/đầu tiên, recent-k,
   DPD bucket, trend và weighted mean.
2. **Model-derived feature là bước nâng cấp có giá trị cao.** Nhiều đội huấn luyện
   model ở grain `SK_ID_PREV` hoặc `SK_ID_BUREAU`, tạo OOF prediction rồi aggregate
   prediction lên applicant. Nested model, predicted term/interest rate và pseudo
   DPD target là ba biến thể nổi bật.
3. **Feature/model diversity quan trọng hơn hyperparameter tối ưu tuyệt đối.** Các
   đội đầu dùng feature set, seed và algorithm khác nhau; model yếu nhưng khác biệt
   đôi khi vẫn làm ensemble tốt hơn. Nhiều bài nói tuning chỉ đóng vai trò thứ yếu.
4. **OOF discipline quyết định độ tin cậy.** Những đội chọn submission theo CV ổn
   định thường ít bị shake-up. Public leaderboard nhỏ và train/test có distribution
   shift khiến probing hoặc manual correction rất rủi ro.
5. **AUC ensemble cần cùng thang đo.** Rank-percent transform không đổi AUC của một
   model đơn, nhưng giúp predictions từ nhiều model có scale khác nhau đi vào blend
   hoặc stacker ổn định hơn.
6. **Stacking chỉ có ích sau khi base model đủ mạnh.** Nhiều đội top có hàng chục
   hoặc hàng trăm OOF, nhưng đội hạng 1 lưu ý average ba single model tốt nhất đã đủ
   để thắng. Với project hiện tại, một multi-table LightGBM mạnh có ROI cao hơn việc
   dựng stack sâu ngay lập tức.

### Ma trận kỹ thuật được lặp lại

| Nhóm kỹ thuật | Bằng chứng lặp lại trong write-up | Ưu tiên cho project |
|---|---|---|
| Aggregate theo time window/recent-k | Hạng 1, 4, 8, 10, 12, 13, 14, 16, 19 và repo hạng 2 | Rất cao |
| Aggregate theo trạng thái | active/closed bureau, approved/refused previous application, past-due installments | Rất cao |
| Ratio có ý nghĩa tín dụng | debt/credit, utilization, annuity/income, credit/annuity, payment/installment | Rất cao |
| Trend/velocity/lag | installment, POS, credit-card, bureau balance | Cao |
| Nested row-level model → applicant aggregate | Hạng 3, 5, 8, 12, 17, 27 | Cao, nhưng phải cross-fit theo applicant |
| Dự đoán term/interest rate | Hạng 2, 5, 10, 27, 48 | Cao sau conventional aggregates |
| Feature selection | forward Ridge, null importance, gain stability, top-feature subsets | Cao khi feature count tăng |
| Rank blend/linear stack | Hạng 1, 3, 7, 8, 12, 24, 32 | Trung bình sau khi có OOF đa dạng |
| DAE/CNN/RNN | Hạng 1, 2, 5, 12, 13 | Thấp trong giai đoạn đầu; chi phí cao |
| User-ID/target lag hoặc manual LB correction | Hạng 2 và 4 | Loại khỏi plan chính vì leakage/overfit risk |

## Tóm tắt từng write-up

### Nhóm xếp hạng cao

#### 1. Bojan Tunguz — [“I am speechless”](https://www.kaggle.com/c/home-credit-default-risk/discussion/64480) (hạng 1)

Bài phản tư nhấn mạnh quá trình ghép đội, reverse-engineer feature set Neptune,
giảm còn 287 feature ban đầu, rồi mở rộng diversity bằng XGBoost, LightGBM,
CatBoost, Ridge và neural network. Bài học chính không phải kiến trúc cụ thể mà là
validation: tin CV có kiểm tra, nghi ngờ mọi mức tăng đột biến không đi cùng LB, và
duy trì pipeline stacking nhất quán. Tác giả cũng nêu mean target của 500 nearest
neighbors theo ba `EXT_SOURCE` và credit/annuity ratio như một feature rất mạnh.

#### 2. Home Aloan — [“1st Place Solution”](https://www.kaggle.com/c/home-credit-default-risk/discussion/64821) (hạng 1)

Đội thắng kết hợp khoảng 700 feature phổ biến với recent/first/last slices, các cửa
sổ 60/90/180/365 ngày, lag theo previous applications, time-weighted aggregates và
KPI income/payment/time. Feature selection bằng forward Ridge giảm hơn 1.600 feature
còn khoảng 240; các superset cuối có 1.800–2.000 feature. Base models gồm LGBM,
XGB, CatBoost, linear model và DAE+NN. Hơn 90 OOF được đưa qua nhiều tầng stacker;
final là equal blend của NN, ExtraTrees và hill climber. Tuy nhiên, phân tích sau
cuộc thi cho thấy average ba single model tốt nhất cũng đủ thắng, củng cố kết luận
rằng feature engineering/selection quan trọng hơn stack sâu.

#### 3. ikiri_DS — [“2nd place solution”](https://www.kaggle.com/c/home-credit-default-risk/discussion/64722) (hạng 2)

Đội 12 người tạo diversity bằng PCA/UMAP/t-SNE/LDA, genetic programming, feature
search lớn, CatBoost/LGBM-DART, NN/DAE/CNN/RNN và nhiều feature set. Các đóng góp
thực dụng nhất là aggregate toàn lịch sử + 1/2/3 năm cho từng bảng, first/last
application, interest-rate features, model-derived features và adversarial
validation để chẩn đoán shift. Repository của Kazuki Onodera xác nhận pipeline
tách feature script theo từng bảng và từng cửa sổ thời gian. Brute-force feature
pool và kiến trúc DL không phải điểm bắt đầu hợp lý cho project hiện tại.

#### 4. Giba — [“Congratulations, Thanks and Finding!!!”](https://www.kaggle.com/c/home-credit-default-risk/discussion/64485) (hạng 2)

Giba tìm cách ghép nhiều `SK_ID_CURR` thành cùng một người dùng và dùng lag của
`TARGET` theo lịch sử người dùng. Thảo luận của organizer chỉ ra đây có thể dùng
thông tin target chỉ quan sát được sau thời điểm quyết định của khoản vay kế tiếp.
Vì vậy insight hữu ích là kiểm tra entity duplication và lịch sử applicant, nhưng
`TARGET` lag/user-ID post-processing bị loại khỏi implementation plan trừ khi có
point-in-time proof rõ ràng.

#### 5. alijs và Evgeny — [“3rd place solution”](https://www.kaggle.com/c/home-credit-default-risk/discussion/64596)

Evgeny xây model riêng cho application, last application, bureau, credit-card và
installment, rồi dùng prediction/metafeature trong model chính. Row-level models
trên bureau/previous applications được average lên applicant và bổ sung prediction
cũng như residual khi dự đoán `EXT_SOURCE`. alijs chọn bảy run ít tương quan từ
khoảng 50 run và stack khoảng 15 level-1 predictions bằng LGBM, Random Forest,
ExtraTrees và linear model. Submission có CV tốt nhất cũng cho private tốt nhất.

#### 6. Shubin — [“4th place sharing and teamwork”](https://www.kaggle.com/c/home-credit-default-risk/discussion/64487)

Đội dùng trend và last 1/3/5/10 records trên installments, POS và bureau; huấn luyện
hơn 200 model trên các feature subset để tạo diversity. Họ giữ OOF từ Bayesian
tuning trials, chọn OOF trước stacker và dùng nhiều stacker khác nhau. Manual
correction cho revolving-loan prediction được tác giả thừa nhận là nguy hiểm; đây
là một leaderboard-specific heuristic, không được đưa vào plan chính.

#### 7. narsil — [“Overview of the 5th solution”](https://www.kaggle.com/c/home-credit-default-risk/discussion/64625)

Đây là write-up giàu ý tưởng nhất sau đội thắng. Khoảng 8.000 handcrafted feature
được giảm còn khoảng 3.000. Đội tạo “user image” 96 tháng để CNN/LSTM trích tương
tác giữa nguồn dữ liệu; nested LGBM trên từng row lịch sử rồi aggregate OOF score;
dự đoán duration/interest rate cho current application từ previous applications;
và thêm logit/probit score theo domain knowledge. Cảnh báo quan trọng: nested model
có thể leak nếu các row của cùng applicant xuất hiện ở cả train và validation.

#### 8. Abdelwahed Assklou và Aguiar — [“7th solution”](https://www.kaggle.com/c/home-credit-default-risk/discussion/64580)

Khoảng 1.200 feature, 11 LGBM trên representation/parameter khác nhau và hai NN
được stack bằng linear regression. Bài này củng cố chiến lược “nhiều cải tiến nhỏ”:
ratio đơn giản, installment delay, `EXT_SOURCE_3` và age là nền; NN riêng lẻ kém
LGBM nhưng hữu ích cho diversity. Đội chỉ theo CV, không tối ưu public LB.

#### 9. Xuan Cao — [“8th Solution Overview”](https://www.kaggle.com/c/home-credit-default-risk/discussion/64474)

Single models đều là LightGBM, khác nhau chủ yếu ở feature engineering. Điểm khác
biệt là aggregate transaction data theo cả applicant và time, bucket DPD theo
30/60/90/120 ngày, dùng single-table OOF làm feature, và rank-percent mọi prediction
trước ensemble. Team rerun model của thành viên trên cùng folds/seed để OOF có thể
so sánh và stack đúng.

#### 10. MichaelP — [“#9 Solution”](https://www.kaggle.com/c/home-credit-default-risk/discussion/64536)

Thông điệp chính là CV governance: mọi thành viên phải dùng cùng phương pháp CV;
feature làm CV tăng nhưng phá quan hệ CV–LB bị loại. Base pool gồm XGB, LGBM,
CatBoost, logistic regression, RF và ExtraTrees. Nhiều model tương đối yếu nhưng
đa dạng làm cho ensemble ổn định hơn. Tác giả cho rằng RNN trên chuỗi lịch sử là
nhánh còn thiếu, không phải bằng chứng rằng nó chắc chắn cải thiện.

#### 11. nlgn và đội — [“10th place writeup”](https://www.kaggle.com/c/home-credit-default-risk/discussion/64598)

Các feature nổi bật: late-payment trong 365 ngày gần nhất, credit utilization hai
tháng gần nhất, bureau debt ratio, reconstructed interest rate và cash-loan model
riêng. Mọi bảng phụ được cắt theo trạng thái, cửa sổ 3/6/18/30/42/54/66 tháng và
latest/earliest fraction trước aggregate. Đội còn thử dự đoán `EXT_SOURCE` missing,
gain-based/null-importance selection và simple tree stacker. Đây là blueprint gần
nhất cho E02–E04 của project.

#### 12. zr và đội — [“#12 solution”](https://www.kaggle.com/c/home-credit-default-risk/discussion/64504)

Statistical features gồm count/max/min/mean/median/std/skew/last/trend/weighted mean,
recent-k và groupby applicant + category. CNN/RNN dự đoán next-loan default và LGBM
row-level tạo model features. Khoảng 2.000 feature được random-subset thành nhiều
LGBM rồi average; sau đó blend với best full-feature model và stack bằng model khác
nhau. Đội ưu tiên bagging/feature fraction hơn feature selection phức tạp.

#### 13. KazAnova và Dmitry — [“13th place — time series features”](https://www.kaggle.com/c/home-credit-default-risk/discussion/64593)

Khoảng 60 chuỗi 96 tháng được tạo từ bureau, credit-card, installment và POS, sau
đó sinh moving average, dispersion, skew/kurtosis, exponential smoothing,
correlation và regression theo thời gian. CNN/LSTM trên chuỗi không vượt LGBM nhưng
tạo diversity cho stack khoảng 100 model. Ý tưởng có giá trị cho phase sau; trước
đó nên dùng slope/delta/weighted mean rẻ hơn để kiểm tra tín hiệu.

#### 14. seaguII, Adri và Tomoyo — [“#14 solution”](https://www.kaggle.com/c/home-credit-default-risk/discussion/64502)

Đội dùng cả one-hot và target encoding trên application, bureau và previous
application; time-window aggregates; bureau debt/credit ratio; DART, GOSS,
CatBoost và XGB. Meta-model là average 30 LGBM/ElasticNet runs. Target encoding ở
row-level chỉ được tái tạo nếu mapping và aggregate được cross-fit theo applicant;
implementation ngây thơ sẽ leak target giữa các row của cùng người.

#### 15. propower và Toaru — [“The 16th Solution”](https://www.kaggle.com/c/home-credit-default-risk/discussion/64505)

Con đường từ CV tự báo cáo khoảng 0.778 lên 0.798 là brute-force aggregates, manual
selection, recent 6/12 tháng, khoảng cách thời gian giữa payments và chọn khoảng
400 feature bằng XGBoost importance. Genetic-programming feature dễ overfit nên
được chia vào các dataset khác nhau, trong khi 400 feature tin cậy xuất hiện ở mọi
model. Cách này gợi ý core-feature + diversity-feature subsets, không khuyến khích
copy GP expressions chưa được giải thích.

#### 16. Qinghui Ge — [“17th place mini writeup”](https://www.kaggle.com/c/home-credit-default-risk/discussion/64503)

Model được huấn luyện trực tiếp trên previous applications với target của current
applicant; credit-card/POS/installment aggregate về `SK_ID_PREV`, không phải
`SK_ID_CURR`. Prediction của từng previous loan sau đó được aggregate mean/max/sum
lên applicant. Bureau được xử lý tương tự. Tác giả báo CV tăng khoảng 0.798 lên
0.801; project cần tái tạo bằng outer-fold cross-fitting theo `SK_ID_CURR`.

#### 17. AllMight — [“#19th solution”](https://www.kaggle.com/c/home-credit-default-risk/discussion/64592)

Hơn 10.000 feature được tạo từ recent 1/2/3 năm và trạng thái approved/active.
Mỗi model dùng top 50 theo importance cộng 50 feature ngẫu nhiên để tạo pool khoảng
200 OOF. Stack hai tầng dùng LGBM, XGB, RF, AdaBoost, logistic regression và
ExtraTrees. Bài này cho thấy feature subset là nguồn diversity, nhưng quy mô đó chỉ
hợp lý sau khi pipeline feature có cache và manifest.

#### 18. Abdel và Arthur Llau — [“24th place — Simple Solution with 7 Models”](https://www.kaggle.com/c/home-credit-default-risk/discussion/64548)

Bảy dataset khác nhau (aggregate, binarized, statistics, lag) được ghép với sáu
boosting models và một NN. Logistic/linear stacker nâng kết quả so với từng model.
Điểm đáng học là diversity từ input representation hiệu quả hơn chỉ đổi algorithm
trên cùng một feature matrix.

#### 19. nyanp — [“Pseudo Data Augmentation”](https://www.kaggle.com/c/home-credit-default-risk/discussion/64693) (hạng 27)

Từ định nghĩa target, tác giả tạo pseudo-label cho previous loans dựa trên DPD của
installments đầu, huấn luyện model trên previous application rồi dự đoán current
application. Predicted DPD class và predicted mean DPD được dùng làm feature; tác
giả báo tăng khoảng 0.003 CV. Repository cho thấy code tách feature theo bảng,
cache Feather và module `PrevModel`. Đây là candidate mạnh nhưng cần kiểm tra cutoff,
pseudo-label sensitivity và group-aware cross-fitting.

#### 20. arnowaczynski — [“Story behind the 32nd place”](https://www.kaggle.com/c/home-credit-default-risk/discussion/64609)

Một solo solution với 1.003 handcrafted feature, LightGBM 5/10-fold trên nhiều
seed/split và chỉ hai submissions. Final là average top-30 runs và Ridge trên top-60
runs. Bài học là seed bagging + disciplined CV có thể đạt top 1% mà không cần kiến
trúc phức tạp hoặc leaderboard probing.

#### 21. James Davis — [“Simple feature that made public kernels top 50”](https://www.kaggle.com/c/home-credit-default-risk/discussion/64600)

Tác giả dự đoán binned loan term, tính real interest rate và dùng vài derivative
features trong rank average. Đây là phiên bản gọn của interest-rate proxy ở các đội
hạng 2/5/10; mức độ lặp lại giữa các đội làm nó trở thành candidate ưu tiên cao.

### Các bài bổ sung

#### 22. YuryBolkonskiy — [“Interesting tricks from the leaders”](https://www.kaggle.com/c/home-credit-default-risk/discussion/64513)

Bài tổng hợp năm pattern: time-window aggregates, NN/LGBM trên history rows,
groupby `SK_ID_PREV`, giữ prediction từ Bayesian trials làm OOF, và dự đoán missing
`EXT_SOURCE`. Giá trị của bài là checklist discovery; mỗi kỹ thuật vẫn phải được
kiểm chứng từ write-up gốc và ablation riêng.

#### 23. Yuya Yamamoto — [findings từ đội hạng 2](https://www.kaggle.com/c/home-credit-default-risk/discussion/64784)

Interest rate là proxy của risk model hiện hành nhưng thay đổi theo thời gian.
Tác giả quan sát phase shift train/test, dùng `SK_ID_BUREAU` như time proxy, tạo
market-rate/standardized-rate feature, encode category theo `EXT_SOURCE` thay vì
`TARGET`, và dùng LGBM dự đoán residual của NN. Bài này đặt distribution shift vào
trung tâm và cảnh báo không dùng raw interest rate mà không kiểm tra drift.

#### 24. YU_CHIH — [“A top solution note for everyone”](https://www.kaggle.com/c/home-credit-default-risk/discussion/64830)

Checklist bao phủ null-importance selection, time-series-as-image, nested models,
interest-rate proxy, groupby kết hợp ID/category, time windows, selected lags,
nearest-neighbor target mean và target encoding. Đây là bản index tốt nhưng không
cung cấp validation mới ngoài các nguồn gốc.

#### 25. Wei Wu — [“Reflections from the biggest fall”](https://www.kaggle.com/c/home-credit-default-risk/discussion/64908)

Tác giả rơi từ hạng public 16 xuống private 127. Blend model chính với model bỏ
`EXT_SOURCE` giúp cả public và private, cho thấy model thiếu external scores có thể
là diversity hedge; tuy nhiên base model yếu và public standing tạo cảm giác an
toàn giả. Bài học: một trick tốt không bù được feature/model nền yếu, và public LB
không phải lý do dừng đào sâu.

#### 26. James Dellinger — [beginner solo hạng 561](https://www.kaggle.com/c/home-credit-default-risk/discussion/64890)

Một single LightGBM end-to-end bao phủ preprocessing, feature engineering, CV,
training, prediction và submission; target encoding được đặt trong CV để tránh
leak. Giá trị chính là reproducibility và memory-aware workflow, phù hợp như bước
chuyển từ notebook sang source module hơn là nguồn feature mới.

#### 27. Chia-Ta Tsai — [pipeline-first solution](https://www.kaggle.com/c/home-credit-default-risk/discussion/64684)

Repository tách `DataProvider`, `FeatureTransformer`, Bayesian optimization,
`AutoStacker`, config và HDF5 cache. Code stacker rank-normalize external OOF trước
khi ghép. Điểm số tự báo cáo không cao, nhưng kiến trúc config/cache/artifact phù
hợp với hướng của repository hiện tại và giảm chi phí khi thử nhiều feature block.

#### 28. Mamy Ratsimbazafy — [fast, scalable and maintainable architecture](https://www.kaggle.com/c/home-credit-default-risk/discussion/64555)

Pipeline dùng SQL feature engineering, caching, logging CV/feature manifest và
diff feature importance giữa experiments. Tác giả ưu tiên procedural functions dễ
cache/parallel hơn một sklearn Pipeline duy nhất. Bài này không phải top scorer,
nhưng đưa ra yêu cầu engineering cần có trước khi mở rộng hàng nghìn feature.

## Ví dụ trong credit scoring

Một feature block có giá trị cao và diễn giải được là hành vi trả nợ gần đây:

- `late_days = DAYS_ENTRY_PAYMENT - DAYS_INSTALMENT`;
- `payment_ratio = AMT_PAYMENT / AMT_INSTALMENT`;
- aggregate toàn lịch sử, 90/180/365 ngày và last 3/5 installments;
- thêm count past-due, max/mean severity, recency và slope;
- tạo cờ phân biệt “không có lịch sử installment” với “có lịch sử nhưng giá trị
  thiếu”.

Mọi output phải có đúng một dòng cho mỗi `SK_ID_CURR`, không sử dụng `TARGET`, và
được so sánh với E01 trên cùng folds trước khi được giữ lại.

## Điều cần kiểm tra trong project

- [ ] Không dùng user-ID target lag, target của row cùng applicant ngoài outer fold,
  hoặc manual leaderboard correction.
- [ ] Nested/pseudo-label features phải cross-fit theo `SK_ID_CURR`; không random
  split các history rows độc lập.
- [ ] Mỗi time window phải có event-time semantics, cutoff và test boundary.
- [ ] Không diễn giải score tự báo cáo trong write-up như kết quả của project.
- [ ] Dùng cùng folds/seed khi so feature blocks và lưu OOF để phân tích correlation.
- [ ] Chỉ đăng ký feature vào registry khi source module và test đã tồn tại.

## Tài liệu liên quan

- [Kế hoạch nâng điểm Home Credit](../roadmap/home_credit_score_improvement_plan.md)
- [Home Credit multi-table](../learning/04_home_credit_default_risk.md)
- [Home Credit validation](../evaluation/home_credit_validation.md)
- [Feature engineering](../features/feature_engineering.md)
- [Experiment log](../experiments/experiment_log.md)
- [1st Place Solution](https://www.kaggle.com/c/home-credit-default-risk/discussion/64821)
- [2nd place repository](https://github.com/KazukiOnodera/Home-Credit-Default-Risk)
- [27th place repository](https://github.com/nyanp/kaggle-homecredit)
- [Pipeline-first repository](https://github.com/cttsai1985/Kaggle-Home-Credit-Default-Risk-Pipeline)

## Trạng thái áp dụng trong project

Đã đọc và tổng hợp 28 nguồn ngày 2026-08-03. Chưa triển khai feature mới và chưa
chạy experiment mới; E01 vẫn là baseline duy nhất được xác minh.
