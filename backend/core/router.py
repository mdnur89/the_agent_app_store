from __future__ import annotations

import json
import logging

from db.messages.crud import get_session_history, save_message
from db.sessions.crud import get_active_session
from db.users.crud import get_or_create_user
# Shared with the voice service, which needs the same client for Whisper and
# Orpheus. Lives in services/ because a service importing from core/ would
# invert the layering.
from services.groq.service import get_groq_client

logger = logging.getLogger(__name__)

CAP_SEARCH = "search_experts"
CAP_DELEGATE = "delegate_task"
CAP_TRANSFER = "transfer_to_agent"

TOOL_SPECS = {
    CAP_SEARCH: {
        "type": "function", "function": {
            "name": CAP_SEARCH,
            "description": "Finds visible specialist agents whose capabilities match a query.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        },
    },
    CAP_DELEGATE: {
        "type": "function", "function": {
            "name": CAP_DELEGATE,
            "description": "Delegates a sub-task to a visible specialist and waits for its response.",
            "parameters": {"type": "object", "properties": {
                "agent_id": {"type": "string"}, "task_description": {"type": "string"},
            }, "required": ["agent_id", "task_description"]},
        },
    },
    CAP_TRANSFER: {
        "type": "function", "function": {
            "name": CAP_TRANSFER,
            "description": "Permanently transfers the conversation to a visible specialist.",
            "parameters": {"type": "object", "properties": {
                "agent_id": {"type": "string"}, "reason": {"type": "string"},
            }, "required": ["agent_id", "reason"]},
        },
    },
}




def _tools_for(agent) -> list[dict] | None:
    granted = set(agent.capabilities or [])
    tools = [TOOL_SPECS[name] for name in (CAP_SEARCH, CAP_DELEGATE, CAP_TRANSFER) if name in granted]
    return tools or None


def _tool_messages(tool_call, content: str) -> list[dict]:
    return [
        {"role": "assistant", "content": None, "tool_calls": [{
            "id": tool_call.id, "type": "function", "function": {
                "name": tool_call.function.name, "arguments": tool_call.function.arguments,
            },
        }]},
        {"role": "tool", "tool_call_id": tool_call.id, "name": tool_call.function.name, "content": content},
    ]


class MessageRouter:
    @staticmethod
    async def process_telegram_message(telegram_id: str, username: str, text: str) -> str:
        user = await get_or_create_user(str(telegram_id), username or "Telegram User")
        session = await get_active_session(user.id)
        if not session:
            return "You don't have an active agent session right now. Send /store to select one!"
        try:
            reply, _ = await MessageRouter.process_web_message(session.id, text)
            return reply
        except Exception as exc:
            logger.exception("Telegram message routing failed")
            return f"Agent encountered an error: {exc}"

    @staticmethod
    async def process_web_message(session_id: str, text: str) -> tuple[str, str]:
        from db.agents.crud import get_visible_agent, list_visible_agents
        from db.client import db
        from db.sessions.crud import switch_user_agent

        session = await db.session.find_unique(where={"id": session_id}, include={"agent": True, "user": True})
        if not session:
            return "Session not found.", session_id
        agent = session.agent
        viewer_id = session.user.id
        visible = await list_visible_agents(viewer_id, active_only=True)
        agents_list = ", ".join(f"'{item.name}' (id: {item.id})" for item in visible if item.id != agent.id)
        system_prompt = agent.system_prompt
        tools = _tools_for(agent)
        if tools and agents_list:
            system_prompt += f"\n\nVisible agents available for routing: {agents_list}."

        await save_message(session.id, "user", text)
        history = await get_session_history(session.id, limit=10)
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend({"role": item.role, "content": item.content} for item in history)

        for _turn in range(3):
            try:
                kwargs = {"messages": messages, "model": agent.llm_model or "llama-3.1-8b-instant"}
                if tools:
                    kwargs.update({"tools": tools, "tool_choice": "auto"})
                message = (await get_groq_client().chat.completions.create(**kwargs)).choices[0].message
                if message.tool_calls:
                    call = message.tool_calls[0]
                    args = json.loads(call.function.arguments)
                    if call.function.name == CAP_SEARCH:
                        from db.search import search_agents_by_capability

                        matches = await search_agents_by_capability(
                            args.get("query", ""), exclude_agent_id=agent.id, viewer_user_id=viewer_id,
                        )
                        details = "\n".join(
                            f"- {m.name} ({m.id}): {m.description} [score={m.score:.3f}, {m.match_type}]" for m in matches
                        ) or "No visible experts found."
                        messages.extend(_tool_messages(call, details))
                        continue
                    if call.function.name in {CAP_DELEGATE, CAP_TRANSFER}:
                        target = await get_visible_agent(args.get("agent_id", ""), viewer_id)
                        if not target or not target.isActive:
                            messages.extend(_tool_messages(call, "That agent is unavailable or not visible."))
                            continue
                        if call.function.name == CAP_TRANSFER:
                            new_session = await switch_user_agent(viewer_id, target.id)
                            return f"🔄 Transferring you to {target.name}.\nReason: {args.get('reason', '')}", new_session.id
                        reply = await MessageRouter.run_agent_headless(
                            target.id, args.get("task_description", ""), viewer_user_id=viewer_id, depth=1,
                        )
                        messages.extend(_tool_messages(call, f"Specialist reply: {reply}"))
                        continue
                reply = message.content or ""
                await save_message(session.id, "assistant", reply)
                return reply, session.id
            except Exception as exc:
                return f"Agent error: {exc}", session_id
        return "Sorry, I took too long to think.", session_id

    @staticmethod
    async def run_agent_headless(
        agent_id: str,
        prompt: str,
        *,
        viewer_user_id: str | None = None,
        depth: int = 0,
    ) -> str:
        from db.agents.crud import get_visible_agent

        if depth >= 2:
            return "Delegation depth exceeded."
        agent = await get_visible_agent(agent_id, viewer_user_id)
        if not agent or not agent.isActive:
            return "Error: Specialist agent is unavailable or not visible."
        messages = [{"role": "system", "content": agent.system_prompt}, {"role": "user", "content": prompt}]
        tools = _tools_for(agent)
        for _turn in range(3):
            try:
                kwargs = {"messages": messages, "model": agent.llm_model or "llama-3.1-8b-instant"}
                if tools:
                    kwargs.update({"tools": tools, "tool_choice": "auto"})
                message = (await get_groq_client().chat.completions.create(**kwargs)).choices[0].message
                if message.tool_calls:
                    call = message.tool_calls[0]
                    args = json.loads(call.function.arguments)
                    if call.function.name == CAP_DELEGATE:
                        target = await get_visible_agent(args.get("agent_id", ""), viewer_user_id)
                        if not target or not target.isActive:
                            result = "That agent is unavailable or not visible."
                        else:
                            result = await MessageRouter.run_agent_headless(
                                target.id, args.get("task_description", ""),
                                viewer_user_id=viewer_user_id, depth=depth + 1,
                            )
                        messages.extend(_tool_messages(call, result))
                        continue
                    messages.extend(_tool_messages(call, "This tool is unavailable during delegated work."))
                    continue
                return message.content or ""
            except Exception as exc:
                return f"Agent failed to complete task: {exc}"
        return "Delegation took too long to complete."
