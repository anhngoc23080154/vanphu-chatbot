"""Lỗi nghiệp vụ của backend.

Mỗi lỗi mang sẵn HTTP status và `detail` bằng tiếng Việt vì frontend hiển thị
nguyên văn `detail` cho khách hàng (xem frontend/src/lib/chatApi.ts).
"""

from __future__ import annotations


class AppError(Exception):
    """Lỗi có thông điệp thân thiện để trả thẳng cho người dùng."""

    status_code: int = 500
    detail: str = "Đã xảy ra lỗi hệ thống. Bạn vui lòng thử lại sau."

    def __init__(self, detail: str | None = None, status_code: int | None = None) -> None:
        if detail:
            self.detail = detail
        if status_code:
            self.status_code = status_code
        super().__init__(self.detail)


class ConfigurationError(AppError):
    status_code = 503
    detail = "Trợ lý chưa được cấu hình đầy đủ. Bạn vui lòng liên hệ quản trị viên."


class UpstreamRateLimited(AppError):
    status_code = 503
    detail = "Trợ lý đang quá tải, bạn vui lòng thử lại sau ít phút."


class UpstreamTimeout(AppError):
    status_code = 504
    detail = "Trợ lý phản hồi quá lâu, bạn vui lòng thử lại."


class UpstreamUnavailable(AppError):
    status_code = 503
    detail = "Trợ lý tạm thời không kết nối được tới hệ thống dữ liệu. Bạn vui lòng thử lại sau ít phút."
