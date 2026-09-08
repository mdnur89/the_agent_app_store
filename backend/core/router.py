import os
from groq import AsyncGroq
from db.users.crud import get_or_create_user
from db.sessions.crud import get_active_session
from db.messages.crud import save_message, get_session_history

# Built on first use rather than at module scope.
#
# AsyncGroq raises if it is handed no api_key, so constructing it here meant a
# missing GROQ_API_KEY was an *import* error: `import main` died with a
# GroqError before FastAPI existed, taking down the health endpoint, the agent
# CRUD routes and the whole test suite along with the LLM calls -- none of
# which need the key. It also made the app depend on .env being loaded before
# this line, which nothing guaranteed (see config.py).
#
# Deferring means a missing key degrades to a per-request error inside the
# handlers below, which already catch exceptions and return them as the agent's
# reply. The client is cached because it holds a connection pool; rebuilding it
# per request would leak sockets.
_groq_client: AsyncGroq | None = None


def get_groq_client() -> AsyncGroq:
    global _groq_client
    if _groq_client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Add it to backend/.env for local runs, "
                "or to the service's environment variables when deployed."
            )
        _groq_client = AsyncGroq(api_key=api_key)
    return _groq_client

class MessageRouter:
    @staticmethod
    async def process_telegram_message(telegram_id: str, username: str, text: str) -> str:
        # 1. Get or create user based on Telegram ID
        user = await get_or_create_user(telegram_id=str(telegram_id), username=username or "Telegram User")
        
        # 2. Get the active session for this user
        session = await get_active_session(user_id=user.id)
        if not session:
            return "You don't have an active agent session right now. Send /store to select one!"
            
        # 3. Use the unified swarm pipeline
        try:
            reply, _ = await MessageRouter.process_web_message(session.id, text)
            return reply
        except Exception as e:
            import logging
            logging.error(f"Error in MessageRouter: {e}")
            return f"Agent encountered an error: {str(e)}"
            
    @staticmethod
    async def process_web_message(session_id: str, text: str) -> tuple[str, str]:
        """The single swarm pipeline; the Telegram transport wraps this too.

        Returns (reply, session_id) rather than a bare reply because
        `transfer_to_agent` retires the current session and opens a new one, so
        the caller cannot assume the session it passed in is the session that
        answered. Web clients must persist the returned id or the next turn
        resumes a dead session. This return shape is load-bearing: EVERY exit
        path below must yield a 2-tuple. It previously did not (see the
        `if not session` branch), and callers unpacking two values raised
        ValueError -> HTTP 500 instead of surfacing the real problem.
        """
        from db.client import db
        from db.agents.crud import get_active_agents
        from db.sessions.crud import switch_user_agent
        import json
        
        session = await db.session.find_unique(where={"id": session_id}, include={"agent": True, "user": True})
        if not session:
            # Tuple, not a bare string: this is the branch that used to break the
            # contract documented above. Reachable whenever a client holds an id
            # this database does not know -- a browser resuming from stale state
            # after the DB was reset, or a `prisma db push` that dropped rows.
            #
            # Callers should reject unknown ids before they reach here (the chat
            # route now 404s), so this is defence in depth for any future caller
            # that forgets. Echoing session_id back unchanged is deliberate: we
            # have no valid session to offer instead, and inventing one would
            # silently migrate the user onto a different convo.
            return ("Session not found.", session_id)
            
        agent = session.agent
        
        # Inject available agents for routing
        active_agents = await get_active_agents()
        agents_list = ", ".join([f"'{a.name}' (id: {a.id})" for a in active_agents if a.id != agent.id])
        
        system_prompt = agent.system_prompt
        tools = None
        
        if agent.id == "sys-orchestrator" and agents_list:
            system_prompt += f"\n\nYou are part of a swarm. If a request requires expertise you don't have, you can use the 'delegate_task' tool to assign a sub-task to another agent and synthesize their response. If you want to permanently hand off the user to another agent, use 'transfer_to_agent'. Available agents: {agents_list}."

            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "search_experts",
                        "description": "Searches the network of millions of agents for an expert matching your query. Use this to find an agent's ID before delegating a task.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": { "type": "string", "description": "The expertise you are looking for (e.g. 'web design', 'Python optimization')" }
                            },
                            "required": ["query"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "transfer_to_agent",
                        "description": "Permanently transfers the conversation to another specialized agent.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "agent_id": { "type": "string" },
                                "reason": { "type": "string" }
                            },
                            "required": ["agent_id", "reason"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "delegate_task",
                        "description": "Delegates a specific sub-task to a specialist agent and waits for their response to synthesize your final answer.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "agent_id": { "type": "string", "description": "The ID of the specialist agent" },
                                "task_description": { "type": "string", "description": "Detailed description of the task for the specialist" }
                            },
                            "required": ["agent_id", "task_description"]
                        }
                    }
                }
            ]
            
        await save_message(session_id=session.id, role="user", content=text)
        
        history = await get_session_history(session_id=session.id, limit=10)
        messages = [{"role": "system", "content": system_prompt}]
        for msg in history:
            messages.append({"role": msg.role, "content": msg.content})
            
        max_turns = 3
        for turn in range(max_turns):
            try:
                kwargs = {
                    "messages": messages,
                    "model": agent.llm_model or "llama-3.1-8b-instant"
                }
                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = "auto"
                    
                chat_completion = await get_groq_client().chat.completions.create(**kwargs)
                
                message = chat_completion.choices[0].message
                
                if message.tool_calls:
                    tool_call = message.tool_calls[0]
                    
                    if tool_call.function.name == "search_experts":
                        args = json.loads(tool_call.function.arguments)
                        query = args.get("query")
                        
                        from db.search import search_agents_by_capability
                        found_experts = await search_agents_by_capability(query)
                        
                        expert_details = ""
                        for e in found_experts:
                            expert_details += f"- Name: {e.name}, ID: {e.id}, Description: {e.description}\n"
                            
                        messages.append({
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [{"id": tool_call.id, "type": "function", "function": {"name": tool_call.function.name, "arguments": tool_call.function.arguments}}]
                        })
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_call.function.name,
                            "content": f"Found Experts:\n{expert_details}"
                        })
                        continue
                        
                    elif tool_call.function.name == "transfer_to_agent":
                        args = json.loads(tool_call.function.arguments)
                        target_agent_id = args.get("agent_id")
                        reason = args.get("reason")
                        new_session = await switch_user_agent(session.user.id, target_agent_id)
                        reply = f"🔄 *Transferring you to another agent...*\nReason: {reason}"
                        return (reply, new_session.id)
                        
                    elif tool_call.function.name == "delegate_task":
                        args = json.loads(tool_call.function.arguments)
                        target_agent_id = args.get("agent_id")
                        task = args.get("task_description")
                        
                        specialist_reply = await MessageRouter.run_agent_headless(target_agent_id, task)
                        
                        # Add tool call to messages, then tool response
                        messages.append({
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [{"id": tool_call.id, "type": "function", "function": {"name": tool_call.function.name, "arguments": tool_call.function.arguments}}]
                        })
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_call.function.name,
                            "content": f"Specialist Reply: {specialist_reply}"
                        })
                        continue # Re-prompt the LLM
                
                reply = message.content or ""
                await save_message(session_id=session.id, role="assistant", content=reply)
                return (reply, session.id)
            except Exception as e:
                return (f"Agent error: {str(e)}", session_id)
        
        # If loop exhausts
        return ("Sorry, I took too long to think.", session_id)
        
    @staticmethod
    async def run_agent_headless(agent_id: str, prompt: str) -> str:
        from db.client import db
        agent = await db.agent.find_unique(where={"id": agent_id})
        if not agent:
            return "Error: Specialist Agent not found."
            
        messages = [
            {"role": "system", "content": agent.system_prompt},
            {"role": "user", "content": prompt}
        ]
        try:
            chat_completion = await get_groq_client().chat.completions.create(
                messages=messages,
                model=agent.llm_model or "llama-3.1-8b-instant",
            )
            return chat_completion.choices[0].message.content or ""
        except Exception as e:
            return f"Agent failed to complete task: {e}"
