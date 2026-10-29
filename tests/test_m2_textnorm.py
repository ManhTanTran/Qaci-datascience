import pytest

from claims_extractor.textnorm import amount_matches, extract_amounts, normalize_text, quote_in_text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("khoảng 200 - 430 triệu/m²", [200_000_000, 430_000_000]),
        ("12–25 tr/m²", [12_000_000, 25_000_000]),
        ("1,2 tỷ/m²", [1_200_000_000]),
        ("65,5 triệu/m²", [65_500_000]),
        ("402.000.000 đồng/m²", [402_000_000]),
        ("nhà 5 tầng giá 65 triệu", [65_000_000]),
        ("từ 90 triệu đến 1,1 tỷ", [90_000_000, 1_100_000_000]),
        ("không có giá", []),
    ],
)
def test_extract_amounts(text, expected):
    assert extract_amounts(text) == expected


def test_amount_matches_has_tolerance():
    assert amount_matches(402_000_000, [402_000_000])
    assert amount_matches(402_000_000, [401_000_000])
    assert not amount_matches(40_200_000, [402_000_000])


def test_quote_matching_ignores_markdown_and_spacing():
    haystack = normalize_text("* **Chung cư:**   65 - 85 triệu/m².")
    assert quote_in_text("Chung cư: 65 - 85 triệu/m².", haystack)
    assert not quote_in_text("Chung cư: 70 - 85 triệu/m²", haystack)
    assert not quote_in_text("", haystack)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("**500 – 900+ triệu/m²**", [500_000_000, 900_000_000]),
        ("130 - 200+ triệu/m²", [130_000_000, 200_000_000]),
        ("từ **800 triệu đến >1 tỷ/m²**", [800_000_000, 1_000_000_000]),
        ("296 – 307,8 triệu đồng/m²", [296_000_000, 307_800_000]),
    ],
)
def test_extract_amounts_open_ended_and_decimals(text, expected):
    assert extract_amounts(text) == expected


def test_clean_answer_text_removes_chat_ui_noise():
    from claims_extractor.textnorm import clean_answer_text

    raw = (
        "Giá khoảng 50–125 triệu/m².&#x20;\n\n"
        "[image](https://www.google.com/s2/favicons?domain=batdongsan.com.vn\\&sz=32)\n\n\n\n"
        "| Trâu Quỳ | $70 - 100 \\text{ triệu/m}^2$ |"
    )
    cleaned = clean_answer_text(raw)
    assert "&#x20;" not in cleaned and "[image]" not in cleaned
    assert "| Trâu Quỳ | 70 - 100 triệu/m² |" in cleaned
    assert "\n\n\n" not in cleaned
    assert extract_amounts("70 - 100 triệu/m²") == [70_000_000, 100_000_000]


def test_emphasis_markers_do_not_break_quote_matching():
    haystack = normalize_text("* **Đất thương mại (VT1):** Khoảng **106 – 109 triệu đồng/m²**.")
    assert quote_in_text("Đất thương mại (VT1): Khoảng 106 – 109 triệu đồng/m².", haystack)
