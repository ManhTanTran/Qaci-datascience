"""Portable HTML report and aggregate artifacts for DC5 research runs."""

from __future__ import annotations

import base64
import html
import json
from pathlib import Path
from typing import Any

import pandas as pd

from credit_scoring.dc5.analysis import EDAResult
from credit_scoring.dc5.clustering import ClusteringResult
from credit_scoring.dc5.modeling import ExperimentResult


def _load_plotting() -> Any:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError(
            'Report plots require: python -m pip install -e ".[dc5]"'
        ) from exc
    return plt


def _plot_model_comparison(metrics: pd.DataFrame, path: Path) -> None:
    plt = _load_plotting()
    labels = metrics["setting"] + " / " + metrics["model"]
    positions = range(len(metrics))
    figure, axes = plt.subplots(1, 2, figsize=(14, 5))
    axes[0].bar(positions, metrics["roc_auc"], color="#2f6fed")
    axes[0].set_title("OOF ROC-AUC")
    axes[0].set_ylim(max(0.0, float(metrics["roc_auc"].min()) - 0.05), 1.0)
    axes[1].bar(positions, metrics["pr_auc"], color="#13a47b")
    axes[1].axhline(
        float(metrics["positive_rate"].iloc[0]),
        color="#d14",
        linestyle="--",
        label="Random baseline",
    )
    axes[1].set_title("OOF PR-AUC")
    axes[1].legend()
    for axis in axes:
        axis.set_xticks(list(positions), labels, rotation=55, ha="right")
        axis.grid(axis="y", alpha=0.2)
    figure.tight_layout()
    figure.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(figure)


def _plot_importance(importance: pd.DataFrame, path: Path, title: str, top_n: int) -> None:
    plt = _load_plotting()
    selected = importance.head(top_n).sort_values("importance")
    figure, axis = plt.subplots(figsize=(10, max(4.5, len(selected) * 0.35)))
    axis.barh(selected["feature"], selected["importance"], color="#7756d8")
    axis.set_title(title)
    axis.set_xlabel("Mean feature importance across folds")
    axis.grid(axis="x", alpha=0.2)
    figure.tight_layout()
    figure.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(figure)


def _plot_eda(eda: EDAResult, path: Path) -> None:
    plt = _load_plotting()
    figure, axes = plt.subplots(1, 3, figsize=(16, 5))
    coverage = eda.domain_coverage.sort_values("coverage_pct")
    axes[0].barh(coverage["domain"], coverage["coverage_pct"], color="#2f6fed")
    axes[0].set_title("Domain coverage (%)")
    missing = eda.missingness.head(12).sort_values("missing_pct")
    axes[1].barh(missing["feature"], missing["missing_pct"], color="#e59b35")
    axes[1].set_title("Top feature missingness (%)")
    target = eda.target_distribution
    axes[2].bar(target["target"].astype(str), target["share_pct"], color="#13a47b")
    axes[2].set_title("Target distribution (%)")
    for axis in axes:
        axis.grid(axis="x", alpha=0.2)
    figure.tight_layout()
    figure.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(figure)


def _plot_clusters(clustering: ClusteringResult, path: Path) -> None:
    plt = _load_plotting()
    figure, axis = plt.subplots(figsize=(9, 6))
    scatter = axis.scatter(
        clustering.projection["pca_1"],
        clustering.projection["pca_2"],
        c=clustering.projection["cluster"],
        s=10,
        alpha=0.55,
        cmap="tab10",
    )
    axis.set_title("PCA projection of Telco + Pharmacy complete cases")
    axis.set_xlabel("PC1")
    axis.set_ylabel("PC2")
    axis.legend(*scatter.legend_elements(), title="Cluster")
    figure.tight_layout()
    figure.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(figure)


def _format_summary(summary: dict[str, Any]) -> str:
    rows = []
    labels = {
        "n_rows": "Population rows",
        "unique_users": "Unique users",
        "n_positive": "Positive rows",
        "n_negative": "Negative rows",
        "positive_rate": "Positive rate",
        "n_features_available": "Available feature columns",
    }
    for key, label in labels.items():
        value = summary[key]
        if key == "positive_rate":
            rendered = f"{value:.2%}"
        elif isinstance(value, int):
            rendered = f"{value:,}"
        else:
            rendered = str(value)
        rows.append(f"<tr><th>{html.escape(label)}</th><td>{html.escape(rendered)}</td></tr>")
    return "<table class='summary'>" + "".join(rows) + "</table>"


def _image_data_uri(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _dashboard_insights(
    metrics: pd.DataFrame,
    importance: pd.DataFrame,
    eda: EDAResult,
    clustering: ClusteringResult | None,
) -> list[str]:
    """Return factual, run-specific observations for the dashboard.

    These are descriptive statements only; they deliberately avoid causal or
    production-credit claims.
    """

    best_roc = metrics.loc[metrics["roc_auc"].idxmax()]
    best_pr = metrics.loc[metrics["pr_auc"].idxmax()]
    top_feature = importance.iloc[0]["feature"] if not importance.empty else "chưa có"
    highest_missing = eda.missingness.sort_values("missing_pct", ascending=False).iloc[0]
    insights = [
        f"ROC-AUC cao nhất trong run: {best_roc['setting']} / {best_roc['model']} ({best_roc['roc_auc']:.3f}).",
        f"PR-AUC cao nhất trong run: {best_pr['setting']} / {best_pr['model']} ({best_pr['pr_auc']:.3f}); so sánh với positive rate {best_pr['positive_rate']:.2%}.",
        f"Feature đứng đầu bảng importance là <code>{html.escape(str(top_feature))}</code>; đây là mức đóng góp của mô hình, không phải quan hệ nhân quả.",
        f"Missingness cao nhất thuộc về <code>{html.escape(str(highest_missing['feature']))}</code> ({highest_missing['missing_pct']:.2f}%).",
    ]
    if clustering is not None:
        insights.append(
            f"Clustering giữ lại {clustering.n_complete_rows:,}/{clustering.n_input_rows:,} dòng complete case; silhouette = {clustering.silhouette:.3f}.",
        )
    return insights


def write_run_artifacts(
    results: list[ExperimentResult],
    *,
    eda: EDAResult,
    clustering: ClusteringResult | None,
    population_summary: dict[str, Any],
    metadata: dict[str, Any],
    run_dir: Path,
    top_n_importance: int,
) -> tuple[Path, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Write metrics, plots and a self-contained navigable HTML report."""

    run_dir.mkdir(parents=True, exist_ok=True)
    plot_dir = run_dir / "plots"
    plot_dir.mkdir(exist_ok=True)
    metrics = pd.DataFrame([result.summary_row() for result in results])
    importance = pd.concat(
        [
            result.importance.assign(setting=result.setting, model=result.model_name)
            for result in results
        ],
        ignore_index=True,
    )
    fold_metrics = pd.concat([result.fold_metrics for result in results], ignore_index=True)
    metrics.to_csv(run_dir / "metrics.csv", index=False)
    importance.to_csv(run_dir / "feature_importance.csv", index=False)
    fold_metrics.to_csv(run_dir / "fold_metrics.csv", index=False)
    eda.domain_coverage.to_csv(run_dir / "domain_coverage.csv", index=False)
    eda.missingness.to_csv(run_dir / "feature_missingness.csv", index=False)
    eda.target_distribution.to_csv(run_dir / "target_distribution.csv", index=False)
    if clustering is not None:
        clustering.profile.to_csv(run_dir / "cluster_profile.csv", index=False)
        clustering.sizes.to_csv(run_dir / "cluster_sizes.csv", index=False)
    (run_dir / "run_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    comparison_name = "model_comparison.png"
    comparison_path = plot_dir / comparison_name
    _plot_model_comparison(metrics, comparison_path)
    eda_path = plot_dir / "eda_overview.png"
    _plot_eda(eda, eda_path)
    cluster_section = ""
    if clustering is not None:
        cluster_path = plot_dir / "cluster_projection.png"
        _plot_clusters(clustering, cluster_path)
        cluster_section = f"""
  <section class="card"><h2>Exploratory clustering</h2>
    <p>Complete cases: {clustering.n_complete_rows:,}/{clustering.n_input_rows:,};
       silhouette: {clustering.silhouette:.4f}; PCA 2D variance:
       {clustering.pca_explained_variance:.2%}.</p>
    {clustering.sizes.to_html(index=False, border=0)}
    <img src="{_image_data_uri(cluster_path)}" alt="Cluster PCA projection"></section>"""
    importance_sections: list[str] = []
    for result in results:
        safe_name = f"importance_{result.setting}_{result.model_name}".lower()
        safe_name = "_".join(safe_name.replace("/", " ").split()) + ".png"
        _plot_importance(
            result.importance,
            plot_dir / safe_name,
            f"{result.setting} / {result.model_name}",
            top_n_importance,
        )
        importance_sections.append(
            "<article class='card'>"
            f"<h3>{html.escape(result.setting)} / {html.escape(result.model_name)}</h3>"
            f"<img src='{_image_data_uri(plot_dir / safe_name)}' alt='Feature importance'>"
            "</article>"
        )

    metrics_display = metrics.copy()
    for column in ("roc_auc", "pr_auc", "positive_rate", "pr_lift"):
        metrics_display[column] = metrics_display[column].map(lambda value: f"{value:.4f}")
    metrics_display["runtime_seconds"] = metrics_display["runtime_seconds"].map(
        lambda value: f"{value:.1f}"
    )
    report_path = run_dir / "report.html"
    dashboard_insights = _dashboard_insights(metrics, importance, eda, clustering)
    dashboard_cards = "".join(
        [
            f"<div class='kpi'><span>{label}</span><strong>{value}</strong></div>"
            for label, value in (
                ("Rows", f"{population_summary['n_rows']:,}"),
                ("Positive rate", f"{population_summary['positive_rate']:.2%}"),
                ("Best ROC-AUC", f"{metrics['roc_auc'].max():.3f}"),
                ("Best PR-AUC", f"{metrics['pr_auc'].max():.3f}"),
            )
        ]
    )
    insight_list = "".join(f"<li>{insight}</li>" for insight in dashboard_insights)
    report_path.write_text(
        f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DC5 Customer Analysis Report</title>
  <style>
    :root {{ color-scheme: light; --ink:#182033; --muted:#647084; --panel:#fff; --bg:#f4f7fb; }}
    body {{ margin:0; font-family:Segoe UI,Arial,sans-serif; color:var(--ink); background:var(--bg); }}
    main {{ max-width:1180px; margin:auto; padding:28px; }}
    h1 {{ margin-bottom:4px; }} .muted {{ color:var(--muted); }}
    .card {{ background:var(--panel); padding:20px; margin:18px 0; border-radius:14px;
             box-shadow:0 3px 18px rgba(26,44,78,.08); overflow:auto; }}
    table {{ border-collapse:collapse; width:100%; }} th,td {{ padding:10px; border-bottom:1px solid #e6eaf0; text-align:left; }}
    .summary th {{ width:260px; }} img {{ width:100%; height:auto; }}
    .dashboard {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; }}
    .kpi {{ background:#eef4fb; border-radius:10px; padding:14px; }}
    .kpi span {{ display:block; color:var(--muted); font-size:12px; }} .kpi strong {{ display:block; font-size:24px; margin-top:5px; }}
    .charts {{ display:grid; grid-template-columns:1fr 1fr; gap:18px; }}
    .insights {{ background:#fff8e7; border-left:4px solid #e59b35; padding:12px 18px; }}
    @media(max-width:760px) {{ .dashboard,.charts {{ grid-template-columns:1fr 1fr; }} }}
    @media(max-width:520px) {{ .dashboard,.charts {{ grid-template-columns:1fr; }} }}
    .links a {{ margin-right:16px; }} code {{ background:#eef2f7; padding:2px 5px; border-radius:4px; }}
  </style>
</head>
<body><main>
  <h1>DC5 Customer Analysis</h1>
  <p class="muted">Research candidate — không phải mô hình production hoặc credit-risk target.</p>
  <section class="card"><h2>Dashboard tổng quan</h2>
    <div class="dashboard">{dashboard_cards}</div>
    <div class="charts"><img src="{_image_data_uri(comparison_path)}" alt="Biểu đồ so sánh ROC-AUC và PR-AUC">
      <img src="{_image_data_uri(eda_path)}" alt="Biểu đồ EDA tổng quan"></div>
    <div class="insights"><h3>Rút ra từ dashboard</h3><ul>{insight_list}</ul>
      <p class="muted">Các insight trên chỉ mô tả run hiện tại; cần kiểm tra stability, leakage và review của data/risk owner trước khi sử dụng.</p></div>
  </section>
  <section class="card"><h2>Population</h2>{_format_summary(population_summary)}</section>
  <section class="card"><h2>EDA overview</h2>
    <img src="{_image_data_uri(eda_path)}" alt="EDA overview"></section>
  <section class="card"><h2>Model comparison</h2>{metrics_display.to_html(index=False, border=0)}
    <img src="{_image_data_uri(comparison_path)}" alt="Model comparison"></section>
  <section><h2>Feature importance</h2>{''.join(importance_sections)}</section>
  {cluster_section}
  <section class="card links"><h2>Artifacts</h2>
    <a href="metrics.csv">Metrics</a><a href="fold_metrics.csv">Fold metrics</a>
    <a href="feature_importance.csv">Feature importance</a>
    <a href="domain_coverage.csv">Domain coverage</a>
    <a href="feature_missingness.csv">Missingness</a>
    <a href="run_metadata.json">Run metadata</a></section>
  <section class="card"><h2>Giới hạn</h2><ul>
    <li>Target là nhóm Telco monetary cao, không phải default hoặc bad debt.</li>
    <li>Feature và target nội bộ vẫn cần mentor/data owner xác nhận.</li>
    <li>Không đưa user_id hoặc dữ liệu cấp khách hàng vào báo cáo.</li>
  </ul></section>
</main></body></html>""",
        encoding="utf-8",
    )
    return report_path.resolve(), metrics, importance, fold_metrics
