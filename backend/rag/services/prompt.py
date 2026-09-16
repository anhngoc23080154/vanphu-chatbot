"""Xây dựng system prompt và ngữ cảnh gửi cho Gemini."""

from __future__ import annotations

from typing import Any

from ..ingest.units import describe_db_row
from ..schemas import HistoryItem
from .query_analyzer import QueryIntent
from .retriever import RetrievalBundle
from .supabase_repo import Doc

# Giới hạn để không vượt ngân sách token và thời gian phản hồi.
MAX_HISTORY_TURNS = 10
MAX_HISTORY_CHARS = 1200
MAX_CONTEXT_CHARS = 14000

SYSTEM_PROMPT = """Bạn là "Trợ lý ảo Văn Phú", trợ lý bán hàng trực tuyến hỗ trợ khách hàng tìm hiểu dự án bất động sản Vlasta Premier - Phú Thuận (đường Đào Trí, phường Phú Thuận, TP Hồ Chí Minh) do Công ty Cổ phần Đầu tư Xây dựng New Tech - thành viên hệ thống Văn Phú - làm chủ đầu tư.

PHẠM VI HỖ TRỢ
- Thông tin dự án: chủ đầu tư, đối tác, quy mô, tiện ích, thiết kế, xây dựng, pháp lý, tiến độ, kết nối vùng.
- Tra cứu sản phẩm: căn hộ, penthouse, shophouse, sàn thương mại dịch vụ; mã căn, tầng, tháp, diện tích, số phòng ngủ, hướng.
- Hình ảnh, mặt bằng, bản đồ 360 độ và tài liệu bán hàng của dự án.
- Hướng dẫn khách để lại thông tin và liên hệ đội ngũ tư vấn.

NGUYÊN TẮC TRẢ LỜI
1. Chỉ dùng thông tin trong phần NGỮ CẢNH được cung cấp. Tuyệt đối không tự suy đoán hay bịa số liệu, giá bán, chính sách.
2. Nếu ngữ cảnh không có thông tin, hãy nói rõ là chưa có dữ liệu và mời khách liên hệ đội ngũ tư vấn để được cập nhật. Không nói "theo tài liệu tôi được cung cấp" hay nhắc tới cơ sở dữ liệu.
3. Câu hỏi ngoài phạm vi bất động sản và dự án: từ chối lịch sự trong một câu rồi mời khách quay lại chủ đề dự án.
4. Khi ngữ cảnh có mục "DỮ LIỆU GIỎ HÀNG", ưu tiên dùng số liệu ở đó cho câu hỏi về mã căn, diện tích, hướng, số phòng ngủ. Nếu ghi chú cho biết chỉ hiển thị một phần, hãy nêu tổng số căn phù hợp và gợi ý khách lọc thêm theo tháp, tầng hoặc số phòng ngủ.
5. Khi ngữ cảnh có mục "HÌNH ẢNH - TÀI LIỆU", có thể nhắc khách xem hình hoặc liên kết đính kèm ngay dưới câu trả lời. Không tự tạo hay đoán đường dẫn.
6. Khi nói về giá bán, chính sách bán hàng, tiến độ hoặc pháp lý, nhắc ngắn gọn rằng thông tin có thể thay đổi và khách nên liên hệ để cập nhật mới nhất.

CÁCH TRÌNH BÀY
- Trả lời bằng tiếng Việt, xưng "em", gọi khách là "anh/chị", giọng thân thiện và chuyên nghiệp.
- Viết văn bản thuần. Không dùng Markdown: không có dấu **, ##, bảng hay liên kết dạng [chữ](link).
- Đoạn ngắn, xuống dòng để tách ý. Khi liệt kê thì mỗi dòng bắt đầu bằng dấu gạch ngang và khoảng trắng.
- Độ dài khoảng 80 đến 150 từ, trừ khi khách yêu cầu liệt kê nhiều căn.
- Giữ nguyên số liệu và đơn vị như trong ngữ cảnh, dùng "m2" cho diện tích.
- Kết thúc bằng một câu hỏi gợi mở hoặc lời mời hỗ trợ tiếp, trừ khi câu trả lời đã là lời từ chối."""

NO_CONTEXT_REPLY = (
    "Dạ, hiện em chưa có thông tin về nội dung anh/chị hỏi trong dữ liệu dự án.\n"
    "Anh/chị vui lòng để lại số điện thoại hoặc liên hệ đội ngũ tư vấn của Văn Phú "
    "để được hỗ trợ chi tiết và cập nhật mới nhất ạ.\n"
    "Em có thể giúp anh/chị tìm hiểu về vị trí, tiện ích, diện tích căn hộ hoặc pháp lý "
    "của dự án Vlasta Premier - Phú Thuận."
)

FALLBACK_REPLY = (
    "Dạ, em xin lỗi vì hiện chưa trả lời được câu hỏi này.\n"
    "Anh/chị vui lòng thử hỏi lại hoặc liên hệ đội ngũ tư vấn của Văn Phú để được hỗ trợ trực tiếp ạ."
)


def _format_docs(docs: list[Doc]) -> str:
    lines: list[str] = []
    for index, doc in enumerate(docs, start=1):
        header = doc.section or doc.source
        lines.append(f"({index}) [{header}] {doc.content}")
    return "\n\n".join(lines)


def _format_units(bundle: RetrievalBundle) -> str:
    lines: list[str] = []
    if bundle.units_total > len(bundle.units):
        lines.append(
            f"Ghi chú: có tổng cộng {bundle.units_total} căn phù hợp, "
            f"dưới đây chỉ liệt kê {len(bundle.units)} căn đầu tiên."
        )
    else:
        lines.append(f"Có {bundle.units_total} căn phù hợp:")
    for row in bundle.units:
        lines.append(f"- {describe_db_row(row)}")
    return "\n".join(lines)


def _format_media(docs: list[Doc]) -> str:
    lines: list[str] = []
    for doc in docs:
        kind = "Hình ảnh" if doc.metadata.get("type", "image") == "image" else "Liên kết"
        lines.append(f"- {kind}: {doc.title or doc.content[:60]}. Mô tả: {doc.content}")
    return "\n".join(lines)


def build_context(
    bundle: RetrievalBundle, attachments: list[Doc], intent: QueryIntent | None = None
) -> str:
    """Ghép các khối ngữ cảnh, cắt bớt nếu vượt giới hạn ký tự."""
    blocks: list[str] = []
    if bundle.docs:
        blocks.append("THÔNG TIN DỰ ÁN\n" + _format_docs(bundle.docs))
    if bundle.units:
        blocks.append("DỮ LIỆU GIỎ HÀNG\n" + _format_units(bundle))
    elif intent is not None and intent.needs_units():
        # Khách hỏi theo mã căn hoặc bộ lọc nhưng không có căn nào khớp.
        blocks.append(
            "DỮ LIỆU GIỎ HÀNG\n"
            "Không tìm thấy căn nào khớp tiêu chí khách hỏi trong bảng hàng của dự án. "
            "Hãy nói rõ điều này và gợi ý khách kiểm tra lại mã căn hoặc đổi tiêu chí tìm kiếm."
        )
    if attachments:
        blocks.append("HÌNH ẢNH - TÀI LIỆU\n" + _format_media(attachments))

    context = "\n\n".join(blocks)
    if len(context) > MAX_CONTEXT_CHARS:
        context = context[:MAX_CONTEXT_CHARS] + "\n[...]"
    return context


def build_contents(
    types: Any,
    history: list[HistoryItem],
    message: str,
    context: str,
    intent: QueryIntent,
) -> list[Any]:
    """Dựng danh sách `contents` cho Gemini: lịch sử hội thoại + lượt hỏi hiện tại."""
    contents: list[Any] = []
    for item in history[-MAX_HISTORY_TURNS:]:
        text = (item.content or "").strip()
        if not text:
            continue
        if len(text) > MAX_HISTORY_CHARS:
            text = text[:MAX_HISTORY_CHARS] + "..."
        role = "user" if item.role == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part(text=text)]))

    if context:
        final_text = (
            "NGỮ CẢNH (dữ liệu nội bộ, không nhắc tới sự tồn tại của phần này khi trả lời):\n"
            f"{context}\n\n"
            f"CÂU HỎI CỦA KHÁCH: {message}"
        )
    else:
        final_text = (
            "NGỮ CẢNH: không tìm thấy dữ liệu liên quan.\n\n"
            f"CÂU HỎI CỦA KHÁCH: {message}"
        )

    if intent.wants_image:
        final_text += (
            "\n\nLưu ý: khách đang hỏi về hình ảnh hoặc tài liệu. "
            "Nếu có mục HÌNH ẢNH - TÀI LIỆU thì hãy mời khách xem nội dung đính kèm bên dưới."
        )

    contents.append(types.Content(role="user", parts=[types.Part(text=final_text)]))
    return contents
