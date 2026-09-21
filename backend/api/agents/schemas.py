from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AgentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=120)
    system_prompt: str = Field(..., min_length=1, max_length=20000)
    description: Optional[str] = Field(None, max_length=1000)
    voice_type: str = Field("default", max_length=100)
    llm_model: str = Field("llama-3.1-8b-instant", max_length=120)
    isActive: bool = True


class AgentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(None, min_length=1, max_length=120)
    system_prompt: Optional[str] = Field(None, min_length=1, max_length=20000)
    description: Optional[str] = Field(None, max_length=1000)
    voice_type: Optional[str] = Field(None, max_length=100)
    llm_model: Optional[str] = Field(None, max_length=120)
    isActive: Optional[bool] = None


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: Optional[str] = None
    text: str = Field(..., min_length=1, max_length=20000)


class ChatResponse(BaseModel):
    reply: str
    session_id: str


class VoiceChatResponse(BaseModel):
    # The transcript rides along so the client can show what was actually
    # heard; without it a misrecognition reads as the agent answering a
    # question the user never asked.
    transcript: str
    reply: str
    session_id: str


class SpeakRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1, max_length=20000)
