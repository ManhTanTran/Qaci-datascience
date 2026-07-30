# Home Credit LightGBM runner

## Mục tiêu

Chuẩn hóa model factory và OOF runner cho application-only Home Credit
baseline.

## Khái niệm chính

`run_lightgbm_cv` dùng StratifiedKFold mặc định 5 folds, early stopping trên
validation fold, ghi OOF prediction đúng index, dự đoán test và tổng hợp
feature importance. Metric chính là ROC-AUC.

Runner không thực hiện feature engineering, target encoding, SMOTE hoặc tuning
theo leaderboard. LightGBM được import lazy để data-loader workflow không cần
model dependency.

## Ví dụ trong credit scoring

Notebook gọi runner như sau:

```python
result = run_lightgbm_cv(
    train_features=X_train,
    target=y,
    test_features=X_test,
    categorical_features=categorical_columns,
    model_config=MODEL_CONFIG,
    validation_config=VALIDATION_CONFIG,
)
```

Kết quả gồm `oof_predictions`, `test_predictions`, fold scores, mean/std AUC,
OOF AUC, best iterations, feature importance, fitted models, runtime và
metadata.

## Điều cần kiểm tra trong project

- [ ] Cài/kiểm tra LightGBM trong môi trường chạy, không giả lập score.
- [ ] Kiểm tra OOF coverage và không có missing predictions.
- [ ] Không dùng test target để tune.
- [ ] Báo cáo calibration, stability và business impact ngoài AUC khi đánh giá
      use case thực tế.
- [ ] Chưa coi model là production-ready khi chưa có model card/phê duyệt.

## Tài liệu liên quan

- [LightGBM và CatBoost](lightgbm_catboost.md)
- [Validation strategy](../evaluation/validation_strategy.md)
- [Model selection](model_selection.md)
- Source: `src/credit_scoring/modeling/lightgbm_model.py`

## Trạng thái áp dụng trong project

Đã có factory và CV runner dùng cho notebook application-only; chưa có
experiment artifact hoặc kết quả verified trong workspace.
