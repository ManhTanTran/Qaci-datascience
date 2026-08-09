# E03 Bureau legacy screening archive

## Mục tiêu

This archive preserves the former E03 Bureau/Bureau Balance screening workflow.
It used 32/36 research candidates and family-level screening experiments before
the project adopted the Spark full-bureau-block direction.

## Khái niệm chính

The active direction is Spark full bureau block → full pandas parity → Parquet
feature blocks → application-block merge → table-level ablation. The Spark
candidate has passed full parity against the pandas `bureau-v1` reference.

## Ví dụ trong credit scoring

The archived feature contract is evidence of a historical family-level screen;
it is not a feature-selection input for the Spark full-block workflow.

## Điều cần kiểm tra trong project

The archived notebook, pre-registration and feature contract retain their
original evidence for audit and reproducibility. They must not be used for new
experiments or current feature selection.

## Tài liệu liên quan

- `01_bureau_ablation.ipynb`: historical 32/36-feature family-ablation notebook.
- `e03_screening_preregistration.md`: historical screening decision rule.
- `home_credit_bureau_features.md`: historical 36-feature contract.

## Trạng thái áp dụng trong project

Superseded and historical only; not part of active navigation.
