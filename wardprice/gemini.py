"""Gemini researchers: legacy ward valuations plus current listing-level search."""

def make_prompt(ward):
    """Reject the retired ward-average prompt; live research is listing-only now."""
    raise RuntimeError("Ward-average Gemini research is disabled; use listing-level research.")


def make_listing_prompt(ward, tracked_listings, *, max_new_listings):
    tracked = [
        {
            "listing_id": item["listing_id"],
            "property_type": item["property_type"],
            "address": item["address"],
            "source_url": item["source_url"],
            "last_seen_at": item["last_seen_at"],
        }
        for item in tracked_listings
    ]
    district_context = f", {ward.district}" if ward.district else ""
    return f'''Bạn đang thu thập TIN RAO CỤ THỂ, không định giá thị trường.
Chỉ nghiên cứu phường được chỉ định: {ward.name}{district_context}, {ward.province}; ward_code={ward.code}.
Danh sách phường do ứng dụng cấp là whitelist tuyệt đối; không đổi tên/mã và không tìm phường khác.
Quận/huyện chỉ là ngữ cảnh disambiguation lấy từ danh sách người vận hành; không dùng nó để mở rộng
phạm vi sang phường khác hoặc tự đổi tên theo địa giới hành chính mới.

Tìm tối đa {max_new_listings} tin rao mới nếu ứng dụng còn chỗ. Tin đang theo dõi cần được tìm lại để
cập nhật giá, diện tích, trạng thái và nguồn. Không trả tin đã theo dõi nếu không có bằng chứng mới.
Tin đang theo dõi (chỉ dùng để làm mới, không tạo bản sao):
{tracked}

Chỉ trả listing có nguồn cụ thể từ Google Search grounding. Không bịa tin, giá, địa chỉ hay URL.
Giá phải là TỔNG GIÁ BÁN VND của tin, không phải giá/m² hoặc giá trung bình. Diện tích phải là m².
Loại chỉ gồm DAT_O, NHA_RIENG, CHUNG_CU. Không gộp loại.
Nếu chỉ có snippet, đặt evidence_status=SEARCH_SNIPPET_ONLY và trích evidence_excerpt ngắn.
Chỉ đặt SOURCE_PAGE_CONFIRMED nếu bạn đã đọc trang chi tiết và trích dẫn chứng cứ tại trang;
đặt source_page_read=true. Ứng dụng sẽ hạ nhãn nếu không có tín hiệu này.
Phải trích riêng price_evidence và area_evidence từ cùng listing source; không suy ra từ giá khu vực.
Nếu không tìm thấy tin hợp lệ, trả listings=[]; không tạo giá ước tính.

Chỉ xuất JSON, không markdown:
{{"listings":[{{"ward_code":"{ward.code}","ward_name":"{ward.name}",
"province":"{ward.province}","property_type":"DAT_O","price_vnd":0,
"area_m2":0,"address":"địa chỉ cụ thể","source_url":"https://...",
"listed_date":"YYYY-MM-DD hoặc null","evidence_status":"SEARCH_SNIPPET_ONLY",
"source_page_read":false,"price_evidence":"trích nguyên văn đoạn có giá",
"area_evidence":"trích nguyên văn đoạn có diện tích","evidence_excerpt":"trích dẫn nguồn"}}]}}
'''


def extract_listing_json(text):
    """Parse the listing response shape; a truly empty response is a no-listings result."""
    if not text or not text.strip():
        return {"listings": []}
    import json
    import re

    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```\s*$", "", stripped)
    payload = json.loads(stripped)
    if not isinstance(payload, dict) or not isinstance(payload.get("listings"), list):
        raise TypeError('expected object with "listings" array')
    return payload


class GeminiResearcher:
    def __init__(self, api_key: str, model: str):
        if not api_key:
            raise RuntimeError("Missing GEMINI_API_KEY")
        from google import genai

        self.client = genai.Client(api_key=api_key)
        self.model = model

    def research(self, ward):
        """Prevent accidental calls to the retired ward-average endpoint."""
        raise RuntimeError("Ward-average Gemini research is disabled; use research_listings().")

    def research_listings(self, ward, tracked_listings, *, max_new_listings):
        from google.genai import types

        response = self.client.models.generate_content(
            model=self.model,
            contents=make_listing_prompt(
                ward, tracked_listings, max_new_listings=max_new_listings
            ),
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.1,
                max_output_tokens=4500,
            ),
        )
        text = response.text or ""
        payload = extract_listing_json(text)
        metadata = None
        if response.candidates:
            metadata = getattr(response.candidates[0], "grounding_metadata", None)
        queries = list(getattr(metadata, "web_search_queries", None) or []) if metadata else []
        chunks = list(getattr(metadata, "grounding_chunks", None) or []) if metadata else []
        supports = list(getattr(metadata, "grounding_supports", None) or []) if metadata else []
        cited_indices = set()
        for support in supports:
            cited_indices.update(getattr(support, "grounding_chunk_indices", None) or [])
        source_urls = []
        for index, chunk in enumerate(chunks):
            if index not in cited_indices:
                continue
            web = getattr(chunk, "web", None)
            uri = getattr(web, "uri", None) if web else None
            if uri:
                source_urls.append(uri)
        usage = getattr(response, "usage_metadata", None)
        return (
            payload,
            list(dict.fromkeys(source_urls)),
            {
                "grounding_used": bool(queries or chunks),
                "search_queries": len(queries),
                "grounding_chunks": len(chunks),
                "cited_grounding_chunks": len(cited_indices),
                "prompt_tokens": getattr(usage, "prompt_token_count", None) if usage else None,
                "output_tokens": getattr(usage, "candidates_token_count", None) if usage else None,
            },
        )
