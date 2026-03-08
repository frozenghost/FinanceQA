"""POST /api/query — SSE streaming endpoint for the LangGraph ReAct agent."""

import json
import logging
import uuid
from typing import Optional

import json_repair
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from pydantic import BaseModel

from core.agent.graph import get_agent

logger = logging.getLogger(__name__)
router = APIRouter()


class QueryRequest(BaseModel):
    message: str
    history: Optional[list[dict]] = None
    thread_id: Optional[str] = None


class FeedbackRequest(BaseModel):
    run_id: str
    key: str = "human-feedback-stars"
    score: float
    comment: Optional[str] = None


@router.post("/api/feedback")
async def feedback(req: FeedbackRequest) -> dict:
    """Record feedback for a run (e.g. for future LangSmith integration)."""
    logger.info(f"Feedback: run_id={req.run_id} key={req.key} score={req.score}")
    return {"status": "success"}


@router.post("/api/query")
async def query_agent(req: QueryRequest) -> StreamingResponse:
    """Stream agent response via SSE (Server-Sent Events)."""

    async def event_stream():
        agent = get_agent()

        messages = []
        if req.history:
            for msg in req.history[-10:]:
                if msg.get("role") == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                elif msg.get("role") == "assistant":
                    messages.append(AIMessage(content=msg["content"]))

        messages.append(HumanMessage(content=req.message))

        thread_id = req.thread_id or str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id, "run_id": run_id}}

        try:
            tool_calls_info = []
            coordinator_data_sent = False
            current_node = None

            async for event in agent.astream_events(
                {"messages": messages},
                config=config,
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
                            markdown_content = output.get("coordinator_markdown", "")
                            analysis_start = output.get("analysis_start")
                            analysis_end = output.get("analysis_end")
                            if markdown_content or analysis_start or analysis_end:
                                payload = {"type": "thinking_complete", "markdown": markdown_content or ""}
                                if analysis_start:
                                    payload["analysis_start"] = analysis_start
                                if analysis_end:
                                    payload["analysis_end"] = analysis_end
                                yield f"data: {json.dumps(payload, default=str)}\n\n"
                                coordinator_data_sent = True

                if kind == "on_chat_model_stream":
                    node = metadata.get("langgraph_node") or current_node
                    chunk = event["data"]["chunk"]
                    if isinstance(chunk, AIMessageChunk) and chunk.content:
                        token = chunk.content
                        # if node == "coordinator":
                        #     # Stream coordinator tokens for live display
                        #     yield f"data: {json.dumps({'type': 'thinking', 'token': token}, default=str)}\n\n"
                        if node != "coordinator":
                            yield f"data: {json.dumps({'type': 'answer', 'token': token}, default=str)}\n\n"

                elif kind == "on_tool_start":
                    # Tool invocation started
                    tool_name = event.get("name", "unknown")
                    logger.info(f"[query] Tool start: {tool_name}")
                    tool_input = event["data"].get("input", {})
                    step = {
                        "id": str(uuid.uuid4())[:8],
                        "tool": tool_name,
                        "input": tool_input,
                        "status": "running",
                    }
                    tool_calls_info.append(step)
                    logger.info(f"[query] Step added, total steps: {len(tool_calls_info)}")
                    yield f"data: {json.dumps({'type': 'step', 'step': step}, default=str)}\n\n"

                elif kind == "on_tool_end":
                    # Tool invocation completed
                    tool_name = event.get("name", "unknown")
                    output = event["data"].get("output", "")
                    logger.info(f"[query] Tool end: {tool_name}, output type: {type(output).__name__}")

                    # Try to parse structured output
                    metadata_payload = None
                    try:
                        # Extract content from ToolMessage object
                        raw_content = ""
                        if hasattr(output, "content"):
                            raw_content = output.content
                        elif isinstance(output, str):
                            raw_content = output
                        
                        # Parse the content as JSON
                        parsed = None
                        if raw_content:
                            try:
                                parsed = json_repair.loads(raw_content)
                                logger.info(f"[query] Parsed output for {tool_name}, keys: {list(parsed.keys()) if isinstance(parsed, dict) else 'not dict'}")
                            except Exception as e:
                                logger.warning(f"[query] Failed to parse {tool_name} output: {e}")

                        # Detect market data with OHLCV for chart rendering
                        if isinstance(parsed, dict):
                            if "ohlcv" in parsed:
                                logger.info(f"[query] Found ohlcv in {tool_name} output!")
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
                                logger.info(f"[query] Found indicators in {tool_name} output")
                                metadata_payload = {
                                    "type": "technical",
                                    "ticker": parsed.get("ticker"),
                                    "indicators": parsed.get("indicators"),
                                    "signals": parsed.get("signals"),
                                }
                            elif "chart_series" in parsed and not parsed.get("error"):
                                if parsed.get("no_earnings_in_range"):
                                    metadata_payload = {
                                        "type": "earnings",
                                        "ticker": parsed.get("ticker"),
                                        "no_earnings_in_range": True,
                                        "reason": parsed.get("reason"),
                                    }
                                else:
                                    logger.info(f"[query] Found chart_series (earnings) in {tool_name} output")
                                    metadata_payload = {
                                        "type": "earnings",
                                        "ticker": parsed.get("ticker"),
                                        "quarterly": parsed.get("quarterly"),
                                        "annual": parsed.get("annual"),
                                        "earnings_surprise": parsed.get("earnings_surprise"),
                                        "earnings_dates": parsed.get("earnings_dates"),
                                        "chart_series": parsed.get("chart_series"),
                                    }
                            else:
                                logger.info(f"[query] No ohlcv or indicators in {tool_name}, keys: {list(parsed.keys())}")
                    except Exception as e:
                        logger.error(f"[query] Error parsing tool output: {e}")

                    # Update tool step status
                    for step in tool_calls_info:
                        if step["tool"] == tool_name and step["status"] == "running":
                            step["status"] = "completed"
                            logger.info(f"[query] Step completed: {tool_name}, total: {len(tool_calls_info)}")
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
                logger.info(f"[query] Sending final steps, count: {len(tool_calls_info)}, detail: {json.dumps(tool_calls_info, default=str)}")
                yield f"data: {json.dumps({'type': 'metadata', 'payload': {'steps': tool_calls_info}}, default=str)}\n\n"
            else:
                logger.warning("[query] No tool calls recorded, steps will not be sent")

            yield f"data: {json.dumps({'type': 'done', 'run_id': run_id})}\n\n"

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
