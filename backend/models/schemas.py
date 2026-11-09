from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Channel = Literal["email", "voice", "chatbot", "social", "web", "other"]


class CustomerFields(BaseModel):
    country: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    age_group: str | None = Field(default=None, max_length=40)
    student_status: str | None = Field(default=None, max_length=40)
    income_bracket: str | None = Field(default=None, max_length=60)


class CustomerCreate(CustomerFields):
    customer_id: str = Field(min_length=1, max_length=100)

    @field_validator("customer_id")
    @classmethod
    def trim_customer_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("customer_id cannot be blank")
        return value


class ComplaintCreate(BaseModel):
    complaint_id: str = Field(min_length=1, max_length=100)
    customer_id: str | None = Field(default=None, max_length=100)
    complaint_text: str = Field(min_length=3, max_length=10000)
    channel: Channel = "other"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    severity: int = Field(default=3, ge=1, le=5)
    customer: CustomerFields = Field(default_factory=CustomerFields)
    customer_aliases: list[str] = Field(default_factory=list, max_length=10)
    customer_identity_verified: bool = False

    @field_validator("complaint_id", "customer_id", mode="before")
    @classmethod
    def trim_ids(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("complaint_text")
    @classmethod
    def clean_complaint_text(cls, value: str) -> str:
        cleaned = " ".join("".join(char for char in value if char.isprintable()).split())
        if len(cleaned) < 3:
            raise ValueError("complaint_text must contain at least 3 visible characters")
        return cleaned


class ComplaintRecord(ComplaintCreate):
    created_at: datetime | str


class CustomerRecord(CustomerCreate):
    created_at: datetime | str


class AnalysisRequest(BaseModel):
    min_cluster_size: int = Field(default=2, ge=2, le=20)
    duplicate_similarity_threshold: float = Field(default=0.92, ge=0.75, le=0.99)
    duplicate_window_days: int = Field(default=30, ge=1, le=180)


class IssueWorkflowUpdate(BaseModel):
    status: Literal["open", "investigating", "resolved"] = "open"
    owner: str | None = Field(default=None, max_length=100)
    notes: str = Field(default="", max_length=4000)
