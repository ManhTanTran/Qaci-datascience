from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
DOCS = ROOT / "docs"
CATALOGS = ROOT / "catalogs"
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*]\(([^)]+)\)")
REQUIRED_SECTIONS = (
    "## Mục tiêu",
    "## Khái niệm chính",
    "## Ví dụ trong credit scoring",
    "## Điều cần kiểm tra trong project",
    "## Tài liệu liên quan",
    "## Trạng thái áp dụng trong project",
)


def test_all_documentation_pages_have_required_sections() -> None:
    for path in DOCS.rglob("*.md"):
        content = path.read_text(encoding="utf-8")
        missing = [heading for heading in REQUIRED_SECTIONS if heading not in content]
        assert not missing, f"{path.relative_to(ROOT)} missing sections: {missing}"


def test_internal_markdown_links_resolve() -> None:
    broken: list[str] = []
    for path in [ROOT / "README.md", *DOCS.rglob("*.md")]:
        content = path.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK.finditer(content):
            raw_target = match.group(1).split("#", 1)[0].strip()
            if not raw_target or "://" in raw_target or raw_target.startswith("mailto:"):
                continue
            target = (path.parent / raw_target).resolve()
            if not target.exists():
                broken.append(f"{path.relative_to(ROOT)} -> {raw_target}")
    assert not broken, "Broken internal links:\n" + "\n".join(broken)


def test_yaml_registries_are_parseable_and_nonempty() -> None:
    expected_roots = {
        "dataset_registry.yaml": "datasets",
        "feature_registry.yaml": "features",
        "model_registry.yaml": "models",
        "metric_registry.yaml": "metrics",
    }
    for filename, root_key in expected_roots.items():
        payload = yaml.safe_load((CATALOGS / filename).read_text(encoding="utf-8"))
        assert payload["schema_version"] == "1.0"
        assert payload[root_key], f"{filename} has no {root_key}"


def test_registry_documentation_paths_resolve() -> None:
    broken: list[str] = []
    for path in CATALOGS.glob("*_registry.yaml"):
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        collection = next(value for key, value in payload.items() if key.endswith("s"))
        for item in collection:
            documentation_path = item["documentation_path"]
            if not (ROOT / documentation_path).exists():
                broken.append(f"{path.name} -> {documentation_path}")
    assert not broken, "Broken registry documentation paths:\n" + "\n".join(broken)


def test_fpt_placeholder_does_not_claim_production_readiness() -> None:
    dataset_registry = yaml.safe_load(
        (CATALOGS / "dataset_registry.yaml").read_text(encoding="utf-8")
    )
    fpt_entry = next(
        item for item in dataset_registry["datasets"] if item["name"] == "FPT Internal Dataset"
    )
    assert fpt_entry["status"] == "placeholder"
    assert "TODO(FPT)" in fpt_entry["target"]
