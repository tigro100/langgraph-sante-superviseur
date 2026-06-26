from typing import Any, Literal
from pydantic import BaseModel, Field


ReviewMode = Literal['AUTO_LOW_RISK_ONLY', 'APPROVED_BY_HUMAN', 'EDITED_BY_HUMAN', 'REJECT_AND_ESCALATE']


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description='Question ou symptômes du patient')
    session_id: str | None = Field(default=None, description='Identifiant conversationnel')
    review_mode: ReviewMode = 'AUTO_LOW_RISK_ONLY'
    human_review: str | None = None
    reviewer_name: str | None = 'Medical reviewer'


class ChatResponse(BaseModel):
    correlation_id: str
    session_id: str
    answer: str
    selected_agent: str | None = None
    risk_level: str | None = None
    status: str
    human_review_required: bool = False
    latency_ms: int
    cost_usd: float
    token_input: int
    token_output: int
    hallucination_risk: bool = False
    technical_alerts: list[str] = []
    trace: dict[str, Any] = {}


class FeedbackRequest(BaseModel):
    correlation_id: str
    hallucination_reported: bool = False
    comment: str | None = None
