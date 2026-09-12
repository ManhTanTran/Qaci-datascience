from __future__ import annotations

import json
import re
from typing import Any

import pandas as pd
from jsonschema import validate

from .common import (
    CONFIG_DIR,
    PROCESSED_DIR,
    clean_scalar,
    ensure_directories,
    is_missing,
    number_or_none,
    write_jsonl,
)


def parse_age_group(value: Any) -> dict[str, Any]:
    if is_missing(value):
        return {"exact": None, "group": None, "min": None, "max": None, "source_type": "missing"}
    text = str(value).strip()
    match = re.fullmatch(r"(\d+)\s*[-–]\s*(\d+)", text)
    if match:
        return {
            "exact": None,
            "group": text,
            "min": int(match.group(1)),
            "max": int(match.group(2)),
            "source_type": "observed",
        }
    plus = re.fullmatch(r">?\s*(\d+)\+?", text)
    if plus:
        lower = int(plus.group(1))
        return {"exact": None, "group": text, "min": lower, "max": None, "source_type": "observed"}
    return {"exact": None, "group": text, "min": None, "max": None, "source_type": "invalid"}


def validated_number(row: pd.Series, field: str, minimum: float, maximum: float) -> tuple[Any, str]:
    raw = row.get(field)
    if is_missing(raw):
        return None, "missing"
    value = number_or_none(raw, minimum=minimum, maximum=maximum)
    return (value, "available") if value is not None else (None, "invalid")


def compact(parts: list[str]) -> str:
    usable = [part for part in parts if part]
    return "; ".join(usable) if usable else "Chưa có dữ liệu"


def build_profile(row: pd.Series) -> dict[str, Any]:
    age = parse_age_group(row.get("age_group"))
    observed_months, observed_status = validated_number(row, "payment_month_count_12M", 0, 12)
    late_months, late_status = validated_number(row, "is_late_sum_12M", 0, 12)
    max_late_days, max_late_status = validated_number(row, "total_late_day_max_12M", 0, 366)
    total_paid, paid_status = validated_number(row, "telco_monetary_sum_12M", 0, 1_000_000_000)
    mean_paid, mean_status = validated_number(row, "telco_monetary_mean_12M", 0, 100_000_000)

    fplay_devices, fplay_status = validated_number(row, "fplay_device_id_nunique_30D", 0, 10_000)
    fplay_events, _ = validated_number(row, "fplay_device_id_count_30D", 0, 10_000_000)
    internet_devices, internet_status = validated_number(row, "internet_device_id_nunique_30D", 0, 10_000)
    internet_events, _ = validated_number(row, "internet_device_id_count_30D", 0, 10_000_000)

    local_income = number_or_none(row.get("avg_monthly_income"), minimum=0, maximum=1_000_000)
    local_spend = number_or_none(row.get("avg_monthly_spend"), minimum=0, maximum=1_000_000)

    retail_fields = [
        "retail_last_order_date",
        "retail_tradein_count_24m",
        "retail_product_group",
        "retail_max_device_product_price_segment_24m",
    ]
    has_retail_detail = any(not is_missing(row.get(field)) for field in retail_fields)

    order_count = clean_scalar(row.get("retail_order_count_12m"))
    order_gmv = clean_scalar(row.get("retail_gmv_12m"))
    order_aov = clean_scalar(row.get("retail_aov_12m"))
    has_orders = any(not is_missing(value) for value in (order_count, order_gmv, order_aov))

    healthcare_values = {
        "order_count_6m": clean_scalar(row.get("healthcare_order_count_6m")),
        "spend_6m": clean_scalar(row.get("healthcare_spend_6m")),
        "average_order_value_6m": clean_scalar(row.get("healthcare_aov_6m")),
        "repeat_purchase_rate_6m": clean_scalar(row.get("healthcare_repeat_purchase_rate_6m")),
    }
    has_healthcare = any(not is_missing(value) for value in healthcare_values.values())

    profile: dict[str, Any] = {
        "user_id": str(row.get("user_id")),
        "age": age,
        "local_context": {
            "avg_monthly_income_source_value": local_income,
            "avg_monthly_spend_source_value": local_spend,
            "source_unit": "nghìn VND/tháng (giả định cần xác nhận với data owner)",
            "source_type": "contextual_proxy",
            "warning": "Không phải thu nhập hoặc chi tiêu của cá nhân.",
        },
        "location": {
            "profile_city": clean_scalar(row.get("city")),
            "installation_city": clean_scalar(row.get("city_install")),
            "district": clean_scalar(row.get("district")),
            "ward": clean_scalar(row.get("ward")),
            "area_type": "unknown",
            "source_type": "observed",
        },
        "device_usage": {
            "fplay_unique_devices_30d": fplay_devices,
            "fplay_events_30d": fplay_events,
            "internet_unique_devices_30d": internet_devices,
            "internet_events_30d": internet_events,
            "monthly_usage_band": clean_scalar(row.get("telco_internet_usage_group")),
            "usage_trend": clean_scalar(row.get("telco_internet_trend_group")),
            "status": "available" if fplay_status == "available" or internet_status == "available" else "missing",
        },
        "payment_history_12m": {
            "total_paid_vnd": total_paid,
            "average_paid_vnd": mean_paid,
            "observed_months": observed_months,
            "late_months": late_months,
            "max_late_days": max_late_days,
            "field_status": {
                "total_paid_vnd": paid_status,
                "average_paid_vnd": mean_status,
                "observed_months": observed_status,
                "late_months": late_status,
                "max_late_days": max_late_status,
            },
        },
        "shopping_installment": {
            "last_order_date": clean_scalar(row.get("retail_last_order_date")),
            "tradein_count_24m": clean_scalar(row.get("retail_tradein_count_24m")),
            "product_group": clean_scalar(row.get("retail_product_group")),
            "highest_price_segment_24m": clean_scalar(row.get("retail_max_device_product_price_segment_24m")),
            "installment_history": None,
            "status": "partial" if has_retail_detail else "missing",
            "missing_fields": ["installment_count_24m", "installment_late_count_24m"],
        },
        "orders": {
            "order_count_12m": order_count,
            "total_value_12m": order_gmv,
            "average_order_value_12m": order_aov,
            "highest_product_name_24m": None,
            "status": "partial" if has_orders else "missing",
            "missing_fields": ["order_count_24m", "total_value_24m", "highest_product_name_24m"],
        },
        "healthcare_spending": {
            **healthcare_values,
            "product_groups": None,
            "status": "partial" if has_healthcare else "missing",
            "missing_fields": ["product_groups"],
        },
        "fpt_education": {
            "child_studies_at_fpt": None,
            "major": None,
            "status": "missing",
        },
        "evidence_trace": [
            {"output": "age", "sources": ["age_group"]},
            {"output": "local_context", "sources": ["avg_monthly_income", "avg_monthly_spend"]},
            {"output": "location", "sources": ["city", "city_install", "district", "ward"]},
            {"output": "device_usage", "sources": ["fplay_device_id_nunique_30D", "internet_device_id_nunique_30D", "telco_internet_usage_group"]},
            {"output": "payment_history_12m", "sources": ["telco_monetary_sum_12M", "payment_month_count_12M", "is_late_sum_12M", "total_late_day_max_12M"]},
        ],
    }
    return profile


def flatten_profile(profile: dict[str, Any]) -> dict[str, Any]:
    age = profile["age"]
    location = profile["location"]
    local = profile["local_context"]
    devices = profile["device_usage"]
    payments = profile["payment_history_12m"]
    shopping = profile["shopping_installment"]
    orders = profile["orders"]
    health = profile["healthcare_spending"]
    education = profile["fpt_education"]

    return {
        "id người dùng": profile["user_id"],
        "tuổi": age.get("exact") or age.get("group") or "Chưa có dữ liệu",
        "thu nhập bình quân địa phương": compact([
            f"{local['avg_monthly_income_source_value']} nghìn VND/tháng" if local.get("avg_monthly_income_source_value") is not None else "",
            "proxy khu vực, không phải thu nhập cá nhân",
        ]),
        "địa chỉ": compact([location.get("ward") or "", location.get("district") or "", location.get("installation_city") or location.get("profile_city") or ""]),
        "hành vi sử dụng thiết bị": compact([
            f"FPT Play: {devices['fplay_unique_devices_30d']} thiết bị, {devices['fplay_events_30d']} lượt/30 ngày" if devices.get("fplay_unique_devices_30d") is not None else "",
            f"Internet: {devices['internet_unique_devices_30d']} thiết bị, {devices['internet_events_30d']} lượt/30 ngày" if devices.get("internet_unique_devices_30d") is not None else "",
            f"Mức dùng: {devices['monthly_usage_band']}" if devices.get("monthly_usage_band") else "",
            f"Xu hướng: {devices['usage_trend']}" if devices.get("usage_trend") else "",
        ]),
        "lịch sử đóng cước internet/truyền hình": compact([
            f"Tổng tiền 12 tháng: {payments['total_paid_vnd']:,.0f} VND" if payments.get("total_paid_vnd") is not None else "",
            f"Số tháng quan sát: {payments['observed_months']}" if payments.get("observed_months") is not None else "",
            f"Số tháng trả chậm: {payments['late_months']}" if payments.get("late_months") is not None else "",
            f"Trễ tối đa: {payments['max_late_days']} ngày" if payments.get("max_late_days") is not None else "",
        ]),
        "lịch sử mua sắm, trả góp": compact([
            f"Lần mua gần nhất: {shopping['last_order_date']}" if shopping.get("last_order_date") else "",
            f"Nhóm sản phẩm: {shopping['product_group']}" if shopping.get("product_group") else "",
            "Chưa có dữ liệu trả góp",
        ]),
        "giá trị và tần suất đơn hàng": compact([
            f"Số đơn 12 tháng: {orders['order_count_12m']}" if orders.get("order_count_12m") is not None else "",
            f"Tổng giá trị 12 tháng: {orders['total_value_12m']}" if orders.get("total_value_12m") is not None else "",
            f"Giá trị đơn trung bình: {orders['average_order_value_12m']}" if orders.get("average_order_value_12m") is not None else "",
            "Chưa có tên sản phẩm đắt nhất",
        ]),
        "chi tiêu thuốc, thực phẩm chức năng": compact([
            f"Số đơn 6 tháng: {health['order_count_6m']}" if health.get("order_count_6m") is not None else "",
            f"Tổng chi 6 tháng: {health['spend_6m']}" if health.get("spend_6m") is not None else "",
            "Chưa có nhóm sản phẩm",
        ]),
        "có cho con học ở FPT không / ngành gì": "Chưa có dữ liệu" if education["status"] == "missing" else compact([str(education.get("child_studies_at_fpt")), education.get("major") or ""]),
    }


def build(frame: pd.DataFrame) -> list[dict[str, Any]]:
    ensure_directories()
    schema = json.loads((CONFIG_DIR / "profile_schema.json").read_text(encoding="utf-8"))
    profiles = [build_profile(row) for _, row in frame.iterrows()]
    for profile in profiles:
        validate(instance=profile, schema=schema)
    write_jsonl(PROCESSED_DIR / "profiles.jsonl", profiles)
    pd.DataFrame([flatten_profile(profile) for profile in profiles]).to_csv(
        PROCESSED_DIR / "profiles.csv", index=False, encoding="utf-8-sig"
    )
    return profiles


def main() -> None:
    from .validate_data import run

    frame, report = run()
    if not report["valid_for_profile_build"]:
        raise SystemExit("Dữ liệu có lỗi cấu trúc; xem validation_report.json")
    profiles = build(frame)
    print(f"Đã tạo {len(profiles)} profile tại {PROCESSED_DIR}")


if __name__ == "__main__":
    main()

