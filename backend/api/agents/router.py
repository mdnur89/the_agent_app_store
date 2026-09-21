from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from prisma.models import User

import db.agents.crud as crud
from api.auth.dependencies import get_current_user, get_current_user_optional
from services.tts.service import VoiceUnavailable, synthesize, transcribe
from .schemas import AgentCreate, AgentUpdate, ChatRequest, ChatResponse, SpeakRequest, VoiceChatResponse

router = APIRouter()


def _agent_out(agent, viewer: User | None) -> dict:
    owner = bool(viewer and agent.owner_id == viewer.id)
    result = {
        "id": agent.id, "name": agent.name, "description": agent.description,
        "voice_type": agent.voice_type, "llm_model": agent.llm_model,
        "isActive": agent.isActive, "is_system": agent.is_system,
        "category": agent.category, "visibility": agent.visibility,
        "published_at": agent.published_at, "createdAt": agent.createdAt,
        "is_owner": owner,
    }
    if owner:
        result["system_prompt"] = agent.system_prompt
    return result


async def _owned_agent(agent_id: str, user: User):
    """Resolve an agent this caller is allowed to mutate, or raise.

    Resolves through the visibility filter first so that an agent the caller
    cannot see is indistinguishable from one that does not exist. Looking it
    up unfiltered and answering 403 would confirm the id is real, which is an
    enumeration oracle over other people's private agent ids: the whole point
    of private agents is that their existence is not observable.

    The is_system check lives here rather than in each caller because system
    agents are platform-owned (owner_id NULL), so the ownership check below
    would already reject them -- but with a misleading "you do not own this
    agent" rather than saying they are not user-editable at all. Callers that
    repeated the check after this function could never reach it.
    """
    agent = await crud.get_visible_agent(agent_id, user.id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.is_system:
        raise HTTPException(status_code=403, detail="System agents are managed by the platform")
    if agent.owner_id != user.id:
        raise HTTPException(status_code=403, detail="You do not own this agent")
    return agent


@router.get("/")
async def get_all_agents(user: User | None = Depends(get_current_user_optional)):
    agents = await crud.list_visible_agents(user.id if user else None)
    return [_agent_out(agent, user) for agent in agents]


@router.get("/active")
async def get_active_agents(user: User | None = Depends(get_current_user_optional)):
    agents = await crud.list_visible_agents(user.id if user else None, active_only=True)
    return [_agent_out(agent, user) for agent in agents]


@router.get("/{agent_id}")
async def get_agent(agent_id: str, user: User | None = Depends(get_current_user_optional)):
    agent = await crud.get_visible_agent(agent_id, user.id if user else None)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _agent_out(agent, user)


@router.post("/", status_code=201)
async def create_agent(agent: AgentCreate, user: User = Depends(get_current_user)):
    created = await crud.create_agent(**agent.model_dump(), owner_id=user.id)
    return _agent_out(created, user)


@router.put("/{agent_id}")
async def update_agent(agent_id: str, patch: AgentUpdate, user: User = Depends(get_current_user)):
    await _owned_agent(agent_id, user)
    data = patch.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    updated = await crud.update_agent(agent_id, data)
    return _agent_out(updated, user)


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str, user: User = Depends(get_current_user)):
    await _owned_agent(agent_id, user)
    foreign = await crud.count_foreign_sessions(agent_id, user.id)
    if foreign:
        raise HTTPException(
            status_code=409,
            detail=f"{foreign} other people have conversations with this agent. Unpublish it instead.",
        )
    await crud.delete_agent(agent_id)
    return {"status": "success", "message": "Agent deleted"}


@router.post("/{agent_id}/publish")
async def publish_agent(agent_id: str, user: User = Depends(get_current_user)):
    await _owned_agent(agent_id, user)
    return _agent_out(await crud.set_published(agent_id, True), user)


@router.post("/{agent_id}/unpublish")
async def unpublish_agent(agent_id: str, user: User = Depends(get_current_user)):
    await _owned_agent(agent_id, user)
    return _agent_out(await crud.set_published(agent_id, False), user)


async def _resolve_chat_session(agent_id: str, session_id: str | None, user: User) -> str:
    """Shared by the text and voice chat routes so they cannot drift apart.

    The session-ownership check in particular must be identical in both: it is
    the only thing stopping one user resuming another's conversation, and a
    voice route that forgot it would reopen the IDOR the text route closes.
    """
    import db.sessions.crud as session_crud

    if session_id:
        session = await session_crud.get_session(session_id)
        if not session or session.user_id != user.id:
            raise HTTPException(status_code=404, detail="Session not found")
        if session.agent_id != agent_id:
            raise HTTPException(status_code=409, detail="That session belongs to a different agent")
        return session.id
    if not await crud.get_visible_agent(agent_id, user.id):
        raise HTTPException(status_code=404, detail="Agent not found")
    return (await session_crud.switch_user_agent(user.id, agent_id)).id


@router.post("/{agent_id}/chat/voice", response_model=VoiceChatResponse)
async def chat_with_agent_by_voice(
    agent_id: str,
    audio: UploadFile = File(..., description="Recorded speech (webm, ogg, mp3, wav, m4a...)"),
    session_id: str | None = Form(None),
    user: User = Depends(get_current_user),
):
    """Speech in, text reply out (fetch the audio separately from /speak).

    The transcript is returned alongside the reply so the client can show what
    was actually heard. Without it a misrecognition looks like the agent
    answering a question nobody asked.
    """
    from core.router import MessageRouter

    resolved = await _resolve_chat_session(agent_id, session_id, user)
    try:
        transcript = await transcribe(await audio.read(), filename=audio.filename or "audio.webm")
    except VoiceUnavailable as exc:
        # 422, not 500: the request was well-formed, the audio was not usable.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    reply, new_session_id = await MessageRouter.process_web_message(session_id=resolved, text=transcript)
    return {"transcript": transcript, "reply": reply, "session_id": new_session_id}


@router.post("/{agent_id}/speak")
async def speak_agent_reply(agent_id: str, req: SpeakRequest, user: User = Depends(get_current_user)):
    """Text -> WAV in the agent's configured voice.

    Separate from the chat routes so speech is opt-in per message: returning
    audio inline would force every caller to pay for synthesis they may never
    play, and base64 in a JSON body roughly triples the transfer.
    """
    agent = await crud.get_visible_agent(agent_id, user.id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        audio = await synthesize(req.text, agent.voice_type)
    except VoiceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return Response(content=audio, media_type="audio/wav")


@router.post("/{agent_id}/chat", response_model=ChatResponse)
async def chat_with_agent(agent_id: str, req: ChatRequest, user: User = Depends(get_current_user)):
    from core.router import MessageRouter

    session_id = await _resolve_chat_session(agent_id, req.session_id, user)
    reply, new_session_id = await MessageRouter.process_web_message(session_id=session_id, text=req.text)
    return {"reply": reply, "session_id": new_session_id}
