"""Research skill — knowledge base search and web research."""

import logging
from pathlib import Path
from typing import Any

import numpy as np
from langchain_core.tools import tool
from pydantic import BaseModel, Field, field_validator

from config.settings import settings
from services.cache_service import cached

logger = logging.getLogger(__name__)


class SearchKnowledgeBaseInput(BaseModel):
    """Schema for search_knowledge_base."""

    query: str = Field(description="Search question, e.g. 'What is P/E ratio', 'How to compute ROE'")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of results to return")

    @field_validator("query")
    @classmethod
    def query_not_empty(cls, v: str) -> str:
        t = (v or "").strip()
        if not t:
            raise ValueError("query must be non-empty")
        return t


class SearchWebInput(BaseModel):
    """Schema for search_web."""

    query: str = Field(description="Search keywords")
    max_results: int = Field(default=5, ge=1, le=10, description="Number of results")

    @field_validator("query")
    @classmethod
    def query_not_empty(cls, v: str) -> str:
        t = (v or "").strip()
        if not t:
            raise ValueError("query must be non-empty")
        return t

# ── BGE-reranker-v2-m3 ONNX singleton ────────────────────────
_onnx_session = None
_tokenizer = None


def _get_reranker():
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
    logger.info(f"BGE-reranker-v2-m3 ONNX loaded from {model_dir}")
    return _onnx_session, _tokenizer


def _get_vectordb():
    """Lazy-load ChromaDB."""
    from langchain_chroma import Chroma
    from services.embedding import get_embeddings

    return Chroma(
        collection_name="finance_knowledge",
        embedding_function=get_embeddings(),
        persist_directory=settings.CHROMA_DIR,
    )


def _bm25_search(query: str, documents: list[dict[str, Any]], top_k: int = 10) -> list[dict]:
    """BM25 keyword-based search with improved tokenization."""
    from rank_bm25 import BM25Okapi
    import jieba

    if not documents:
        return []

    corpus = [doc["page_content"] for doc in documents]
    
    def tokenize(text: str) -> list[str]:
        if any('\u4e00' <= c <= '\u9fff' for c in text):
            return list(jieba.cut_for_search(text))
        return text.lower().split()
    
    tokenized_corpus = [tokenize(doc) for doc in corpus]
    bm25 = BM25Okapi(tokenized_corpus)

    tokenized_query = tokenize(query)
    scores = bm25.get_scores(tokenized_query)

    scored_docs = list(zip(scores, documents))
    scored_docs.sort(key=lambda x: x[0], reverse=True)
    return [doc for _, doc in scored_docs[:top_k]]


def _rerank(query: str, documents: list[str], top_n: int = 5) -> list[tuple[int, float]]:
    """Rerank using BGE-reranker-v2-m3 (ONNX)."""
    if not documents:
        return []

    try:
        session, tokenizer = _get_reranker()

        pairs = [[query, doc[:512]] for doc in documents]
        inputs = tokenizer(
            pairs,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="np",
        )

        ort_inputs = {k: v.astype(np.int64) if v.dtype == np.int32 else v for k, v in inputs.items() if k in ("input_ids", "attention_mask", "token_type_ids")}
        outputs = session.run(None, ort_inputs)

        scores = outputs[0]
        if len(scores.shape) > 1:
            scores = scores[:, 0]
        scores = scores.flatten()

        scored_indices = [(i, float(scores[i])) for i in range(len(scores))]
        scored_indices.sort(key=lambda x: x[1], reverse=True)
        return scored_indices[:top_n]

    except Exception as e:
        logger.warning(f"BGE rerank failed, falling back to original order: {e}")
        return [(i, 0.0) for i in range(min(top_n, len(documents)))]


@tool(args_schema=SearchKnowledgeBaseInput)
async def search_knowledge_base(query: str, top_k: int = 5) -> dict:
    """
    Search the financial knowledge base (hybrid: vector + BM25 + rerank).
    - query: Search question, e.g. "What is P/E ratio", "How to compute ROE"
    - top_k: Number of results to return, default 5
    Returns the most relevant document snippets with content, source and relevance score.
    Use for financial concepts, indicator definitions, industry knowledge.
    If no relevant content is found, tell the user clearly; do not fabricate answers.
    """
    logger.info(f"[search_knowledge_base] Query: '{query}', top_k: {top_k}")
    
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        vectordb = _get_vectordb()

        # 1. Vector similarity search
        vector_results_with_scores = await loop.run_in_executor(
            None,
            lambda: vectordb.similarity_search_with_score(query, k=top_k * 3)
        )
        vector_docs = [
            {
                "page_content": doc.page_content, 
                "metadata": doc.metadata,
                "vector_score": float(score),
            }
            for doc, score in vector_results_with_scores
        ]
        
        logger.info(f"[search_knowledge_base] Vector search returned {len(vector_docs)} candidates")
        if vector_docs:
            logger.debug(f"[search_knowledge_base] Vector scores: {[round(d['vector_score'], 4) for d in vector_docs[:3]]}")

        # 2. BM25 keyword search
        bm25_docs = []
        if vector_docs:
            try:
                bm25_docs = _bm25_search(query, vector_docs, top_k=top_k * 2)
                logger.info(f"[search_knowledge_base] BM25 search returned {len(bm25_docs)} candidates")
            except Exception as e:
                logger.warning(f"BM25 retrieval failed: {e}")

        # 3. Merge and deduplicate
        seen = set()
        merged = []
        
        for doc in vector_docs + bm25_docs:
            content_hash = hash(doc["page_content"])
            if content_hash not in seen:
                seen.add(content_hash)
                merged.append(doc)

        logger.info(f"[search_knowledge_base] After merge/dedup: {len(merged)} unique candidates")

        if not merged:
            logger.warning(f"[search_knowledge_base] No results found for query: '{query}'")
            return {
                "query": query,
                "results": [],
                "message": "No relevant content found in knowledge base; consider using search_web for up-to-date information",
            }

        # 4. Rerank with BGE
        texts = [doc["page_content"] for doc in merged]
        ranked_results = _rerank(query, texts, top_n=top_k)
        
        logger.info(f"[search_knowledge_base] Reranked top-{len(ranked_results)} results")

        results = []
        for idx, rerank_score in ranked_results:
            if idx < len(merged):
                doc = merged[idx]
                results.append({
                    "content": doc["page_content"],
                    "source": doc["metadata"].get("source", "unknown"),
                    "type": doc["metadata"].get("type", "unknown"),
                    "relevance_score": rerank_score,
                })

        # Log top-k results for debugging
        for i, r in enumerate(results):
            logger.info(f"[search_knowledge_base] Top-{i+1}: source={r['source']}, type={r['type']}, score={r['relevance_score']:.4f}, content_preview={r['content'][:100]}...")

        return {
            "query": query,
            "results": results,
            "total_candidates": len(merged),
            "retrieval_method": "hybrid (vector + BM25) + BGE rerank",
        }

    except Exception as e:
        logger.error(f"Knowledge base retrieval failed: {e}")
        return {
            "query": query,
            "results": [],
            "error": f"Retrieval failed: {str(e)}",
        }


@tool(args_schema=SearchWebInput)
@cached(key_prefix="web", ttl=900)
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
        import asyncio
        from tavily import TavilyClient

        loop = asyncio.get_event_loop()
        tavily = TavilyClient(api_key=settings.TAVILY_API_KEY)
        
        # Timeout control
        response = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: tavily.search(query, max_results=max_results)),
            timeout=15.0
        )

        results = []
        for r in response.get("results", []):
            results.append({
                "title": r.get("title", ""),
                "content": r.get("content", ""),
                "url": r.get("url", ""),
                "score": r.get("score", 0),
            })

        return {
            "query": query,
            "results": results,
            "data_source": "Tavily",
        }
    
    except Exception as e:
        logger.error(f"Tavily search failed: {e}")
        return {"error": f"Web search failed: {str(e)}"}
