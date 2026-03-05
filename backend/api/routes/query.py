"""POST /api/query — SSE streaming endpoint for the LangGraph ReAct agent."""

import json
import logging
import uuid

import json_repair
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
            coordinator_data_sent = False
            current_node = None

            async for event in agent.astream_events(
                {"messages": messages},
                version="v2",
            ):
                kind = event["event"]
                metadata = event.get("metadata", {})

                if kind == "on_chain_start":
                    current_node = metadata.get("langgraph_node") or current_node
                elif kind == "on_chain_end":
                    if metadata.get("langgraph_node") == current_node:
                        current_node = None
                    if metadata.get("langgraph_node") == "coordinator" and not coordinator_data_sent:
                        output = event["data"].get("output", {})
                        if output and isinstance(output, dict):
                            # 发送 Markdown 内容用于前端显示
                            markdown_content = output.get("coordinator_markdown", "")
                            if markdown_content:
                                # 发送一个特殊的 token 来标记协调器思考完成
                                yield f"data: {json.dumps({'type': 'thinking_complete', 'markdown': markdown_content}, default=str)}\n\n"
                                coordinator_data_sent = True

                if kind == "on_chat_model_stream":
                    node = metadata.get("langgraph_node") or current_node
                    chunk = event["data"]["chunk"]
                    if isinstance(chunk, AIMessageChunk) and chunk.content:
                        token = chunk.content
                        if node == "coordinator":
                            # Stream coordinator tokens for live display
                            yield f"data: {json.dumps({'type': 'thinking', 'token': token}, default=str)}\n\n"
                        else:
                            yield f"data: {json.dumps({'type': 'answer', 'token': token}, default=str)}\n\n"

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
                            # 使用 json_repair 解析工具返回的 JSON 字符串，兼容轻微格式问题
                            parsed = json_repair.loads(output)
                        else:
                            parsed = output

                        # Detect market data with OHLCV for chart rendering
                        if isinstance(parsed, dict):
                            if "ohlcv" in parsed:
                                # Convert lowercase keys to uppercase for frontend compatibility
                                ohlcv_data = parsed.get("ohlcv", [])
                                formatted_ohlcv = []
                                for item in ohlcv_data:
                                    formatted_ohlcv.append({
                                        "Date": item.get("date"),
                                        "Open": item.get("open"),
                                        "High": item.get("high"),
                                        "Low": item.get("low"),
                                        "Close": item.get("close"),
                                        "Volume": item.get("volume"),
                                    })
                                
                                metadata_payload = {
                                    "type": "market",
                                    "ticker": parsed.get("ticker"),
                                    "ohlcv": formatted_ohlcv,
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
