"""Research skill — knowledge base search and web research."""

import asyncio
import logging
from pathlib import Path
from typing import Any

import numpy as np
from langchain_core.tools import tool
from pydantic import BaseModel, Field, field_validator

from config.settings import settings
from services.cache_service import cached
from skills.common import validate_non_empty

logger = logging.getLogger(__name__)

# Retrieval tuning: more candidates → rerank filters similar concepts (e.g. P/E vs P/B)
VECTOR_CANDIDATES_MULTIPLIER = 3
BM25_TOP_MULTIPLIER = 2
RERANK_MAX_LENGTH = 512
MIN_RERANK_SCORE = -2.0  # drop chunks with very low rerank score (likely wrong concept)


class SearchKnowledgeBaseInput(BaseModel):
    """Schema for search_knowledge_base."""

    query: str = Field(description="Search question, e.g. 'What is P/E ratio', 'How to compute ROE'")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of results to return")

    @field_validator("query")
    @classmethod
    def query_not_empty(cls, v: str) -> str:
        return validate_non_empty(v, "query")


class SearchWebInput(BaseModel):
    """Schema for search_web."""

    query: str = Field(description="Search keywords")
    max_results: int = Field(default=5, ge=1, le=10, description="Number of results")

    @field_validator("query")
    @classmethod
    def query_not_empty(cls, v: str) -> str:
        return validate_non_empty(v, "query")


# BGE-reranker-v2-m3 ONNX singleton
_onnx_session = None
_tokenizer = None


def _get_reranker() -> tuple[Any, Any]:
    """Lazy-load ONNX reranker model (singleton)."""
    global _onnx_session, _tokenizer
    if _onnx_session is not None:
        return _onnx_session, _tokenizer

    import onnxruntime as ort
    from transformers import AutoTokenizer

    model_dir = Path(settings.RERANKER_MODEL_DIR)
    if not (model_dir / "model.onnx").exists():
        raise FileNotFoundError(
            f"ONNX reranker model not found at {model_dir}/model.onnx. "
            "Please run: uv run python scripts/download_reranker.py"
        )
    _tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
    _onnx_session = ort.InferenceSession(
        str(model_dir / "model.onnx"),
        providers=["CPUExecutionProvider"],
    )
    logger.info("BGE-reranker-v2-m3 ONNX loaded from %s", model_dir)
    return _onnx_session, _tokenizer


def _get_vectordb() -> Any:
    """Lazy-load ChromaDB."""
    from langchain_chroma import Chroma
    from services.embedding import get_embeddings

    return Chroma(
        collection_name="finance_knowledge",
        embedding_function=get_embeddings(),
        persist_directory=settings.CHROMA_DIR,
    )


def _tokenize_for_bm25(text: str) -> list[str]:
    """Tokenize for BM25: jieba for CJK, else lowercase split."""
    import jieba
    if any("\u4e00" <= c <= "\u9fff" for c in text):
        return list(jieba.cut_for_search(text))
    return text.lower().split()


def _bm25_search(query: str, documents: list[dict[str, Any]], top_k: int = 10) -> list[dict[str, Any]]:
    """BM25 keyword search over candidate docs; boosts exact term match (reduces similar-concept noise)."""
    from rank_bm25 import BM25Okapi

    if not documents:
        return []
    corpus = [d["page_content"] for d in documents]
    tokenized_corpus = [_tokenize_for_bm25(c) for c in corpus]
    bm25 = BM25Okapi(tokenized_corpus)
    scores = bm25.get_scores(_tokenize_for_bm25(query))
    indexed = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    return [documents[i] for i in indexed[:top_k]]


def _rerank(query: str, documents: list[str], top_n: int, min_score: float = MIN_RERANK_SCORE) -> list[tuple[int, float]]:
    """Rerank with BGE-reranker-v2-m3 (ONNX). Drops items below min_score to filter wrong-concept chunks."""
    if not documents:
        return []

    try:
        session, tokenizer = _get_reranker()
        pairs = [[query, doc[:RERANK_MAX_LENGTH]] for doc in documents]
        inputs = tokenizer(
            pairs,
            padding=True,
            truncation=True,
            max_length=RERANK_MAX_LENGTH,
            return_tensors="np",
        )
        ort_inputs = {
            k: (v.astype(np.int64) if v.dtype == np.int32 else v)
            for k, v in inputs.items()
            if k in ("input_ids", "attention_mask", "token_type_ids")
        }
        outputs = session.run(None, ort_inputs)
        scores = np.asarray(outputs[0]).reshape(-1)
        if scores.ndim > 1:
            scores = scores[:, 0]

        out: list[tuple[int, float]] = []
        for i in np.argsort(-scores):
            s = float(scores[i])
            if s < min_score:
                break
            out.append((int(i), s))
            if len(out) >= top_n:
                break
        return out
    except Exception as e:
        logger.warning("BGE rerank failed, using original order: %s", e)
        return [(i, 0.0) for i in range(min(top_n, len(documents)))]


def _merge_dedup_by_content(doc_lists: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Merge doc lists and deduplicate by page_content (order: first occurrence wins)."""
    seen: set[int] = set()
    merged: list[dict[str, Any]] = []
    for doc in (d for lst in doc_lists for d in lst):
        h = hash(doc["page_content"])
        if h not in seen:
            seen.add(h)
            merged.append(doc)
    return merged


@tool(args_schema=SearchKnowledgeBaseInput)
async def search_knowledge_base(query: str, top_k: int = 5) -> dict:
    """
    Search the financial knowledge base (hybrid: vector + BM25 + rerank).
    - query: Search question, e.g. "What is P/E ratio", "How to compute ROE"
    - top_k: Number of results to return, default 5
    Returns document snippets with content, source and type (no internal scores).
    Use for financial concepts, indicator definitions, industry knowledge.
    If no relevant content is found, tell the user clearly; do not fabricate answers.
    """
    logger.info("[search_knowledge_base] query=%r top_k=%s", query, top_k)
    try:
        vectordb = _get_vectordb()
        k_vector = top_k * VECTOR_CANDIDATES_MULTIPLIER

        vector_results = await asyncio.to_thread(
            vectordb.similarity_search_with_score, query, k=k_vector
        )
        vector_docs = [
            {"page_content": doc.page_content, "metadata": doc.metadata, "vector_score": float(score)}
            for doc, score in vector_results
        ]
        logger.info("[search_knowledge_base] vector candidates=%s", len(vector_docs))

        bm25_docs: list[dict[str, Any]] = []
        if vector_docs:
            try:
                bm25_docs = _bm25_search(query, vector_docs, top_k=top_k * BM25_TOP_MULTIPLIER)
            except Exception as e:
                logger.warning("BM25 retrieval failed: %s", e)

        merged = _merge_dedup_by_content([vector_docs, bm25_docs])
        logger.info("[search_knowledge_base] after merge/dedup unique=%s", len(merged))

        if not merged:
            return {
                "query": query,
                "results": [],
                "message": "No relevant content found in knowledge base; consider using search_web for up-to-date information",
            }

        texts = [d["page_content"] for d in merged]
        ranked = _rerank(query, texts, top_n=top_k)

        def _display_source(_meta: dict) -> str:
            """Public-facing label only; never expose internal paths or file names."""
            return "知识库"

        results = []
        for idx, score in ranked:
            if idx >= len(merged):
                continue
            doc = merged[idx]
            meta = doc.get("metadata") or {}
            display_src = _display_source(meta)
            results.append({
                "content": doc["page_content"],
                "source": display_src,
                "type": meta.get("type", "unknown"),
                "relevance_score": score,
            })

        for i, r in enumerate(results):
            logger.info(
                "[search_knowledge_base] top-%s source=%s type=%s score=%.4f content_preview=%s...",
                i + 1, r["source"], r["type"], r["relevance_score"], r["content"][:100]
            )

        # Expose only content and generic source; never internal paths, filenames, or scores
        results_for_agent = [
            {"content": r["content"], "source": r["source"], "type": r["type"]}
            for r in results
        ]
        return {
            "query": query,
            "results": results_for_agent,
        }
    except Exception as e:
        logger.exception("Knowledge base retrieval failed")
        return {"query": query, "results": [], "error": f"Retrieval failed: {str(e)}"}


def _cache_key_web(*args, **kwargs) -> str:
    query = (kwargs.get("query") or (args[0] if args else "") or "")[:80].replace(" ", "_")
    max_results = kwargs.get("max_results", 5)
    return f"{query}_{max_results}"


@tool(args_schema=SearchWebInput)
@cached(key_prefix="web", ttl=900, key_extra=_cache_key_web)
async def search_web(query: str, max_results: int = 5) -> dict:
    """
    Real-time web search via Tavily.
    - query: Search keywords
    - max_results: Number of results, default 5
    Returns latest web results with title, snippet and URL.
    Use for news, real-time events, announcements not in the knowledge base.
    """
    if not settings.TAVILY_API_KEY:
        return {"error": "Tavily API key not configured; web search unavailable"}

    try:
        from tavily import TavilyClient

        tavily = TavilyClient(api_key=settings.TAVILY_API_KEY)
        response = await asyncio.wait_for(
            asyncio.to_thread(tavily.search, query, max_results=max_results),
            timeout=15.0,
        )
        results = [
            {
                "title": r.get("title", ""),
                "content": r.get("content", ""),
                "url": r.get("url", ""),
                "score": r.get("score", 0),
            }
            for r in response.get("results", [])
        ]
        return {"query": query, "results": results, "data_source": "web_search"}
    except Exception as e:
        logger.exception("Tavily search failed")
        return {"error": f"Web search failed: {str(e)}"}
