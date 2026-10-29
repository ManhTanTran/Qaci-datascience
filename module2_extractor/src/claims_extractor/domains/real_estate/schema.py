"""Real-estate claim schemas: what the LLM emits, and what we store after verification."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PropertyType = Literal["DAT_O", "NHA_RIENG", "CHUNG_CU", "TONG_HOP", "KHAC"]
AreaBasis = Literal["LAND_AREA", "FLOOR_AREA"]
PriceBasis = Literal["MARKET", "STATE_TABLE", "UNKNOWN"]
Metric = Literal["median", "typical_range", "min", "max", "avg", "point"]
ConfidenceFlag = Literal["ok", "ambiguous", "implausible"]


class PriceClaim(BaseModel):
    """One price statement made by the chatbot (one number or one range). Prices in VND/m²."""

    model_config = ConfigDict(extra="ignore")

    province: str | None = None
    district: str | None = None  # legacy level; may be absent after the 2025 reorganisation
    ward: str | None = None
    street: str | None = None  # a single street/route when the claim is specific to it
    property_type: PropertyType
    sub_segment: str | None = None  # free text: "mặt phố", "ngõ", "đất đấu giá", project name...
    price_basis: PriceBasis = "UNKNOWN"  # market price vs state land-price table
    metric: Metric
    value_low: int = Field(gt=0)
    value_high: int | None = Field(default=None, gt=0)
    open_ended: bool = False  # True when the top of the range is a floor ("trở lên", "+", "trên")
    unit_original: str
    qualifier: str | None = None  # "giá chào bán", "ước tính"...
    period_text: str | None = None  # period the price refers to, as stated ("Quý 1/2026")
    quote: str = Field(min_length=1)  # verbatim excerpt of the answer supporting this claim

    @model_validator(mode="after")
    def _needs_location(self) -> "PriceClaim":
        if not ((self.district or "").strip() or (self.ward or "").strip()):
            raise ValueError("either district or ward is required")
        return self


class ExtractionResult(BaseModel):
    claims: list[PriceClaim]


class StoredPriceClaim(PriceClaim):
    """A claim after code verification, with provenance. Never a measured statistic."""

    claim_id: str
    answer_id: str
    crawl_run_id: str | None = None
    target_month: str | None = None  # period asked about (YYYY-MM); distinct from crawled_at
    crawled_at: datetime
    chatbot: str
    area_basis: AreaBasis | None  # None when the property type mixes or is unknown
    confidence_flag: ConfidenceFlag
    flag_reasons: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)  # resolved from [n] markers in the quote


CSV_COLUMNS = [
    "claim_id", "answer_id", "crawl_run_id", "target_month", "crawled_at", "chatbot",
    "province", "district", "ward", "street",
    "property_type", "area_basis", "sub_segment", "price_basis",
    "metric", "value_low", "value_high", "open_ended", "unit_original", "qualifier",
    "period_text", "confidence_flag", "flag_reasons", "source_urls", "quote",
]
