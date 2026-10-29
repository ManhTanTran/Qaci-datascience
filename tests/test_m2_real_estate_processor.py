import pytest

from claims_extractor.domains.real_estate.processor import normalize_place, process_claim
from claims_extractor.textnorm import normalize_text
from support import make_claim


def run(raw, answer):
    return process_claim(raw, answer, normalize_text(answer.answer_text))


def test_good_claim_is_stored_with_provenance(answer):
    result = run(make_claim(), answer)
    claim = result.stored
    assert result.rejected is None
    assert claim["confidence_flag"] == "ok" and claim["flag_reasons"] == []
    assert claim["area_basis"] == "LAND_AREA"
    assert claim["answer_id"] == answer.answer_id and claim["chatbot"] == "gemini"
    assert len(claim["claim_id"]) == 16


def test_apartment_uses_floor_area(answer):
    raw = make_claim(property_type="CHUNG_CU", sub_segment=None, value_low=65_000_000,
                     value_high=85_000_000, quote="Chung cư:** 65 - 85 triệu/m²")
    assert run(raw, answer).stored["area_basis"] == "FLOOR_AREA"


def test_quote_not_in_answer_is_rejected(answer):
    result = run(make_claim(quote="khoảng giá 999 triệu/m²"), answer)
    assert result.stored is None and result.rejected["reason"] == "quote_not_in_answer"


def test_value_not_matching_quote_is_ambiguous(answer):
    result = run(make_claim(value_low=20_000_000), answer)
    assert result.stored["confidence_flag"] == "ambiguous"
    assert "value_low_not_in_quote" in result.stored["flag_reasons"]


def test_implausible_value_is_flagged_not_dropped(answer):
    raw = make_claim(property_type="DAT_O", metric="point", value_low=3_500_000_000, value_high=None,
                     quote="đôi nơi được rao 3,5 tỷ/m² (ước tính)", unit_original="tỷ/m²")
    claim = run(raw, answer).stored
    assert claim["confidence_flag"] == "implausible"
    assert "outside_plausible_range" in claim["flag_reasons"]


def test_old_quarter_prices_up_to_billions_are_plausible(answer):
    raw = make_claim(metric="point", value_low=1_300_000_000, value_high=None,
                     quote="khoảng 402 triệu/m²")
    assert "outside_plausible_range" not in run(raw, answer).stored["flag_reasons"]


def test_swapped_range_is_fixed_and_flagged(answer):
    claim = run(make_claim(value_low=430_000_000, value_high=200_000_000), answer).stored
    assert (claim["value_low"], claim["value_high"]) == (200_000_000, 430_000_000)
    assert claim["confidence_flag"] == "ambiguous" and "range_swapped" in claim["flag_reasons"]


def test_range_metric_without_high_is_ambiguous(answer):
    claim = run(make_claim(value_high=None, quote="khoảng giá phổ biến 200"), answer)
    assert claim.rejected or "range_without_high" in claim.stored["flag_reasons"]


def test_schema_errors_are_rejected_with_reason(answer):
    for bad in (make_claim(property_type="VILLA"), make_claim(district=None, ward=None),
                make_claim(value_low=-5), make_claim(metric="mode")):
        result = run(bad, answer)
        assert result.stored is None and result.rejected["reason"] == "schema_error"


def test_names_are_normalized_and_claim_id_is_stable(answer):
    first = run(make_claim(district="Quận Long Biên", ward="P. Bồ Đề"), answer).stored
    second = run(make_claim(district="long biên", ward="Phường Bồ Đề"), answer).stored
    assert (first["district"], first["ward"]) == ("Long Biên", "Bồ Đề")
    assert first["claim_id"] == second["claim_id"]


@pytest.mark.parametrize(
    ("raw", "prefix", "expected"),
    [
        ("Quận Long Biên", "", "Long Biên"),
        ("P. Bồ Đề", "", "Bồ Đề"),
        ("Phú Lợi", "", "Phú Lợi"),
        ("Phường Phú Lợi", "", "Phú Lợi"),
        ("Xã Sóc Sơn", "", "Sóc Sơn"),
        ("Q1", "Quận", "Quận 1"),
        ("phường 12", "Phường", "Phường 12"),
        ("LONG BIÊN", "", "Long Biên"),
        ("TP.HCM", "", "HCM"),
        ("Thành phố Hà Nội", "", "Hà Nội"),
        ("   ", "", None),
        (None, "", None),
    ],
)
def test_normalize_place(raw, prefix, expected):
    assert normalize_place(raw, prefix) == expected


def test_mixed_property_type_has_no_area_basis(answer):
    claim = run(make_claim(property_type="TONG_HOP"), answer).stored
    assert claim["area_basis"] is None


def test_new_fields_are_kept_and_distinguish_claims(answer):
    base = run(make_claim(), answer).stored
    other_period = run(make_claim(period_text="Quý 1/2026"), answer).stored
    state = run(make_claim(price_basis="STATE_TABLE", street=" Giảng Võ "), answer).stored
    assert other_period["period_text"] == "Quý 1/2026"
    assert state["price_basis"] == "STATE_TABLE" and state["street"] == "Giảng Võ"
    assert len({base["claim_id"], other_period["claim_id"], state["claim_id"]}) == 3
    assert base["price_basis"] == "UNKNOWN" and base["open_ended"] is False


def test_open_ended_range_is_checked_against_quote(answer):
    raw = make_claim(metric="min", value_low=1_500_000_000, value_high=None, open_ended=True,
                     unit_original="tỷ/m²", quote="đôi nơi được rao 3,5 tỷ/m²")
    claim = run(raw, answer).stored
    assert claim["open_ended"] is True and "value_low_not_in_quote" in claim["flag_reasons"]


def test_total_price_per_house_is_flagged(answer):
    raw = make_claim(value_low=3_500_000_000, value_high=None, metric="point",
                     unit_original="tỷ/căn", quote="đôi nơi được rao 3,5 tỷ/m² (ước tính)")
    assert "total_price_in_quote" not in run(raw, answer).stored["flag_reasons"]  # has /m²

    from claims_extractor.models import AnswerRecord
    house = AnswerRecord(crawled_at="2026-10-27T09:00:00+07:00", chatbot="gemini",
                         answer_text="Tòa nhà văn phòng giá 120 – 350 tỷ / căn.")
    raw = make_claim(property_type="KHAC", value_low=120_000_000_000, value_high=350_000_000_000,
                     unit_original="tỷ / căn", quote="giá 120 – 350 tỷ / căn")
    claim = process_claim(raw, house, normalize_text(house.answer_text)).stored
    assert "total_price_in_quote" in claim["flag_reasons"] and claim["confidence_flag"] == "implausible"
