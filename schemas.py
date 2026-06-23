from typing import Any, Optional

from pydantic import BaseModel, field_validator


class AskRequest(BaseModel):
    question: str

    @field_validator("question")
    @classmethod
    def validate_question(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question must not be empty")
        if len(v) > 2000:
            raise ValueError("question must not exceed 2000 characters")
        return v


class Source(BaseModel):
    text: str
    origin: str         # "seeded" or "uploaded"
    filename: str
    page_number: Optional[int] = None
    section: Optional[str] = None


class AskResponse(BaseModel):
    answer: str
    intent: str    # "knowledge" | "action" | "clarify"
    action_taken: Optional[str] = None
    action_result: Optional[dict] = None
    sources: list[Source] = []


class DocRequest(BaseModel):
    title: str
    content: str

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title must not be empty")
        if len(v) > 200:
            raise ValueError("title must not exceed 200 characters")
        return v

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("content must not be empty")
        if len(v) > 50_000:
            raise ValueError("content must not exceed 50,000 characters")
        return v


class DocResponse(BaseModel):
    id: str
    title: str
    filename: str
    origin: str
