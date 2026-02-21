"""
Generic API schemas — health, pagination, error responses.
"""

from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    apis_configured: dict[str, bool]
    all_apis_ready: bool


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    has_more: bool


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None


class SuccessResponse(BaseModel):
    status: str = "ok"
    message: Optional[str] = None
    data: Optional[Any] = None
