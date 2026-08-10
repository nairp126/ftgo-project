"""
Pydantic schemas for chat request/response following OpenAI-compatible format.
Supports Requirements 1.1 (unified endpoint), 1.3 (standardized format), 1.5 (OpenAI schema).
"""

from decimal import Decimal
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field


# --- Request Schemas ---


class Message(BaseModel):
    """A single message in the conversation."""
    role: str = Field(..., description="Role: system, user, assistant, or tool")
    content: str = Field(..., description="Message content")
    name: Optional[str] = Field(None, description="Optional name for the participant")


class ChatRequest(BaseModel):
    """
    OpenAI-compatible chat completion request.
    Supports Requirement 1.5: follow OpenAI request schema.
    """
    model: str = Field(..., description="Model identifier (e.g. gpt-4o, claude-3-5-sonnet)")
    messages: List[Message] = Field(..., description="Conversation messages")
    temperature: Optional[float] = Field(0.7, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: Optional[int] = Field(None, ge=1, description="Maximum tokens to generate")
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0, description="Nucleus sampling")
    stream: Optional[bool] = Field(False, description="Enable streaming response")
    stop: Optional[List[str]] = Field(None, description="Stop sequences")
    presence_penalty: Optional[float] = Field(0.0, ge=-2.0, le=2.0)
    frequency_penalty: Optional[float] = Field(0.0, ge=-2.0, le=2.0)
    routing_tags: Optional[Dict[str, Any]] = Field(None, description="Custom routing tags")
    ensemble_strategy: Optional[str] = Field(None, description="Strategy for model ensembling: 'fastest', 'longest'")
    ensemble_models: Optional[List[str]] = Field(None, description="List of models to ensemble against")


# --- Response Schemas ---


class Choice(BaseModel):
    """A single completion choice."""
    index: int = 0
    message: Message
    finish_reason: Optional[str] = Field("stop", description="Reason generation stopped")


class Usage(BaseModel):
    """Token usage statistics."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class GatewayMetadata(BaseModel):
    """
    Gateway-specific metadata attached to every response.
    Supports Requirements 4.5 (routing metadata), 5.5 (cache status), 9.5 (cost).
    """
    provider: str = Field(..., description="Provider that handled the request")
    cache_status: str = Field("MISS", description="HIT, MISS, or BYPASS")
    latency_ms: int = Field(0, description="Total gateway latency in milliseconds")
    cost_usd: Decimal = Field(Decimal("0.0"), description="Estimated cost in USD")
    request_id: str = Field(..., description="Unique request correlation ID")
    routing_decision: Optional[Dict[str, Any]] = Field(None, description="Routing details")


class ChatResponse(BaseModel):
    """
    OpenAI-compatible chat completion response.
    Supports Requirement 1.3: standardized response format.
    """
    id: str = Field(..., description="Response ID")
    object: str = Field("chat.completion", description="Object type")
    created: int = Field(..., description="Unix timestamp")
    model: str = Field(..., description="Model used")
    choices: List[Choice] = Field(..., description="Completion choices")
    usage: Usage = Field(default_factory=Usage, description="Token usage")
    gateway_metadata: Optional[GatewayMetadata] = Field(None, description="Gateway metadata")


# --- Streaming Schemas ---


class DeltaMessage(BaseModel):
    """Partial message for streaming responses."""
    role: Optional[str] = None
    content: Optional[str] = None


class StreamChoice(BaseModel):
    """A streaming chunk choice."""
    index: int = 0
    delta: DeltaMessage = Field(default_factory=DeltaMessage)
    finish_reason: Optional[str] = None


class ChatStreamResponse(BaseModel):
    """Streaming chunk response (SSE format)."""
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: List[StreamChoice]
