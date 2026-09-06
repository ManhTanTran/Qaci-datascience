"""Optional notebook-compatible exploratory clustering for DC5."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

CLUSTER_FEATURES = (
    "age_group_ord",
    "income_band_est_ord",
    "active_domain_count_ord",
    "tenure_group_ord",
    "recency_group_ord",
    "app_count_group_ord",
    "app_tenure_group_ord",
    "app_recency_days_ord",
    "loyalty_points_ord",
    "loyalty_tier_ord",
    "telco_inbound_count_180d_ord",
    "telco_outbound_count_180d_ord",
    "telco_ticket_count_180d_ord",
    "telco_internet_usage_group_ord",
    "telco_internet_trend_group_ord",
    "telco_monetary_group_ord",
    "telco_is_cancelled",
    "telco_install_year",
    "healthcare_last_order_date_ord",
    "healthcare_order_count_6m_ord",
    "healthcare_spend_6m_ord",
    "healthcare_aov_6m_ord",
    "healthcare_repeat_purchase_rate_6m_ord",
    "healthcare_vaccine_visit_count_12m_ord",
)


@dataclass(frozen=True)
class ClusteringResult:
    """Aggregate cluster profiles and anonymous 2D projection."""

    profile: pd.DataFrame
    sizes: pd.DataFrame
    projection: pd.DataFrame
    silhouette: float
    pca_explained_variance: float
    n_input_rows: int
    n_complete_rows: int


def validate_clustering_schema(frame: pd.DataFrame) -> None:
    required = {"has_telco", "has_pharmacy", *CLUSTER_FEATURES}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Clustering requires missing columns: {missing}")


def run_clustering(
    frame: pd.DataFrame,
    *,
    n_clusters: int = 4,
    random_state: int = 42,
) -> ClusteringResult:
    """Run complete-case KMeans and PCA without exporting identifiers."""

    validate_clustering_schema(frame)
    candidates = frame.loc[frame["has_telco"].eq(1) & frame["has_pharmacy"].eq(1)]
    complete = candidates.loc[:, CLUSTER_FEATURES].dropna().copy()
    if len(complete) <= n_clusters:
        raise ValueError(
            f"Clustering needs more than {n_clusters} complete rows; found {len(complete)}."
        )
    scaled = StandardScaler().fit_transform(complete)
    model = KMeans(n_clusters=n_clusters, random_state=random_state, n_init="auto")
    labels = model.fit_predict(scaled)
    pca = PCA(n_components=2, random_state=random_state)
    projection_values = pca.fit_transform(scaled)
    labeled = complete.assign(cluster=labels)
    profile = labeled.groupby("cluster", as_index=False)[list(CLUSTER_FEATURES)].mean()
    sizes = (
        pd.Series(labels, name="cluster")
        .value_counts()
        .sort_index()
        .rename("count")
        .rename_axis("cluster")
        .reset_index()
    )
    sizes["share_pct"] = sizes["count"] / len(complete) * 100
    projection = pd.DataFrame(
        {
            "pca_1": projection_values[:, 0],
            "pca_2": projection_values[:, 1],
            "cluster": labels,
        }
    )
    return ClusteringResult(
        profile=profile,
        sizes=sizes,
        projection=projection,
        silhouette=float(
            silhouette_score(
                scaled,
                labels,
                sample_size=min(5_000, len(complete)),
                random_state=random_state,
            )
        ),
        pca_explained_variance=float(pca.explained_variance_ratio_.sum()),
        n_input_rows=len(candidates),
        n_complete_rows=len(complete),
    )
