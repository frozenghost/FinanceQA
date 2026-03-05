"""POST /api/query — SSE streaming endpoint for the LangGraph ReAct agent."""

import json
import logging
import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessageChunk, HumanMessage
from pydantic import BaseModel

from core.agent.graph import get_agent

logger = logging.getLogger(__name__)
router = APIRouter()


class QueryRequest(BaseModel):
    message: str
    history: list[dict] | None = None


@router.post("/api/query")
async def query_agent(req: QueryRequest):
    """Stream agent response via SSE (Server-Sent Events)."""

    async def event_stream():
        agent = get_agent()

        # Build message history
        messages = []
        if req.history:
            for msg in req.history[-10:]:  # Last 10 messages for context
                if msg.get("role") == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                elif msg.get("role") == "assistant":
                    from langchain_core.messages import AIMessage

                    messages.append(AIMessage(content=msg["content"]))

        messages.append(HumanMessage(content=req.message))

        try:
            tool_calls_info = []
            coordinator_sent = False

            async for event in agent.astream_events(
                {"messages": messages},
                version="v2",
            ):
                kind = event["event"]
                
                # 捕获协调器节点的输出
                if kind == "on_chain_end" and not coordinator_sent:
                    metadata = event.get("metadata", {})
                    langgraph_node = metadata.get("langgraph_node", "")
                    
                    if langgraph_node == "coordinator":
                        output = event["data"].get("output", {})
                        if output and isinstance(output, dict):
                            coordinator_data = {
                                "reasoning": output.get("coordination_reasoning", ""),
                                "tool_plan": output.get("tool_plan", []),
                                "needs_tools": output.get("needs_tools", False),
                            }
                            if coordinator_data["reasoning"] or coordinator_data["tool_plan"]:
                                yield f"data: {json.dumps({'type': 'coordinator', 'data': coordinator_data}, default=str)}\n\n"
                                coordinator_sent = True

                if kind == "on_chat_model_stream":
                    # Streaming tokens from the LLM
                    chunk = event["data"]["chunk"]
                    if isinstance(chunk, AIMessageChunk) and chunk.content:
                        token = chunk.content
                        yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"

                elif kind == "on_tool_start":
                    # Tool invocation started
                    tool_name = event.get("name", "unknown")
                    tool_input = event["data"].get("input", {})
                    step = {
                        "id": str(uuid.uuid4())[:8],
                        "tool": tool_name,
                        "input": tool_input,
                        "status": "running",
                    }
                    tool_calls_info.append(step)
                    yield f"data: {json.dumps({'type': 'step', 'step': step}, default=str)}\n\n"

                elif kind == "on_tool_end":
                    # Tool invocation completed
                    tool_name = event.get("name", "unknown")
                    output = event["data"].get("output", "")

                    # Try to parse structured output
                    metadata_payload = None
                    try:
                        if isinstance(output, str):
                            parsed = json.loads(output)
                        else:
                            parsed = output

                        # Detect market data with OHLCV for chart rendering
                        if isinstance(parsed, dict):
                            if "ohlcv" in parsed:
                                metadata_payload = {
                                    "type": "market",
                                    "ticker": parsed.get("ticker"),
                                    "ohlcv": parsed.get("ohlcv"),
                                    "current": parsed.get("current"),
                                    "change_pct": parsed.get("change_pct"),
                                    "trend": parsed.get("trend"),
                                }
                            elif "indicators" in parsed:
                                metadata_payload = {
                                    "type": "technical",
                                    "ticker": parsed.get("ticker"),
                                    "indicators": parsed.get("indicators"),
                                    "signals": parsed.get("signals"),
                                }
                    except (json.JSONDecodeError, TypeError):
                        pass

                    # Update tool step status
                    for step in tool_calls_info:
                        if step["tool"] == tool_name and step["status"] == "running":
                            step["status"] = "completed"
                            break

                    step_update = {
                        "tool": tool_name,
                        "status": "completed",
                    }
                    yield f"data: {json.dumps({'type': 'step_complete', 'step': step_update}, default=str)}\n\n"

                    # Send metadata if we have structured data
                    if metadata_payload:
                        yield f"data: {json.dumps({'type': 'metadata', 'payload': metadata_payload}, default=str)}\n\n"

            # Send final steps summary
            if tool_calls_info:
                yield f"data: {json.dumps({'type': 'metadata', 'payload': {'steps': tool_calls_info}}, default=str)}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            logger.error(f"Agent execution error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
