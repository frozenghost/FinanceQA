"""Research skill — knowledge base search and web research."""

import logging
from pathlib import Path
from typing import Any

import numpy as np
from langchain_core.tools import tool

from config.settings import settings
from services.cache_service import cached

logger = logging.getLogger(__name__)

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

        ort_inputs = {k: v for k, v in inputs.items() if k in ("input_ids", "attention_mask", "token_type_ids")}
        outputs = session.run(None, ort_inputs)

        scores = outputs[0]
        if len(scores.shape) > 1:
            scores = scores[:, 0]
        scores = scores.flatten()

        scored_indices = [(i, float(scores[i])) for i in range(len(scores))]
        scored_indices.sort(key=lambda x: x[1], reverse=True)
        return scored_indices[:top_n]

    except Exception as e:
        logger.warning(f"BGE rerank 失败，回退到原始排序: {e}")
        return [(i, 0.0) for i in range(min(top_n, len(documents)))]


@tool
async def search_knowledge_base(query: str, top_k: int = 5) -> dict:
    """
    在金融知识库中搜索相关信息（混合检索：向量+BM25+重排序）。
    - query: 搜索问题，如 "什么是市盈率"、"ROE如何计算"
    - top_k: 返回结果数量，默认 5
    返回最相关的知识库文档片段，包含内容、来源和相关性评分。
    适用于金融概念解释、指标定义、行业知识等场景。
    如果知识库中没有相关内容，请明确告知用户，不要编造答案。
    """
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

        # 2. BM25 keyword search
        bm25_docs = []
        if vector_docs:
            try:
                bm25_docs = _bm25_search(query, vector_docs, top_k=top_k * 2)
            except Exception as e:
                logger.warning(f"BM25 检索失败: {e}")

        # 3. Merge and deduplicate
        seen = set()
        merged = []
        
        for doc in vector_docs + bm25_docs:
            content_hash = hash(doc["page_content"])
            if content_hash not in seen:
                seen.add(content_hash)
                merged.append(doc)

        if not merged:
            return {
                "query": query,
                "results": [],
                "message": "知识库中未找到相关内容，建议使用 search_web 工具搜索最新信息",
            }

        # 4. Rerank with BGE
        texts = [doc["page_content"] for doc in merged]
        ranked_results = _rerank(query, texts, top_n=top_k)

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

        return {
            "query": query,
            "results": results,
            "total_candidates": len(merged),
            "retrieval_method": "hybrid (vector + BM25) + BGE rerank",
        }

    except Exception as e:
        logger.error(f"知识库检索失败: {e}")
        return {
            "query": query,
            "results": [],
            "error": f"检索失败: {str(e)}",
        }


@tool
@cached(key_prefix="web", ttl=900)
async def search_web(query: str, max_results: int = 5) -> dict:
    """
    使用 Tavily 搜索引擎进行实时网络搜索。
    - query: 搜索关键词
    - max_results: 返回结果数量，默认 5
    返回最新的网络搜索结果，包含标题、内容摘要和来源链接。
    适用于获取最新资讯、实时事件、最新公告等知识库中没有的信息。
    """
    if not settings.TAVILY_API_KEY:
        return {"error": "Tavily API key 未配置，无法进行网络搜索"}

    try:
        import asyncio
        from tavily import TavilyClient

        loop = asyncio.get_event_loop()
        tavily = TavilyClient(api_key=settings.TAVILY_API_KEY)
        
        # 添加超时控制
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
        logger.error(f"Tavily 搜索失败: {e}")
        return {"error": f"网络搜索失败: {str(e)}"}
