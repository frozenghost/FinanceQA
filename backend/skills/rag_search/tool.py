"""RAG search skill — hybrid BM25 + vector retrieval with BGE ONNX reranking."""

import logging
from pathlib import Path
from typing import Any

import numpy as np
from langchain_core.tools import tool

from config.settings import settings

logger = logging.getLogger(__name__)

# ── BGE-reranker-v2-m3 ONNX singleton ────────────────────────
_onnx_session = None
_tokenizer = None


def _get_reranker():
    """Lazy-load ONNX reranker model (singleton, thread-safe enough for GIL)."""
    global _onnx_session, _tokenizer

    if _onnx_session is not None:
        return _onnx_session, _tokenizer

    import onnxruntime as ort
    from transformers import AutoTokenizer

    model_dir = Path(settings.RERANKER_MODEL_DIR)

    if not (model_dir / "model.onnx").exists():
        raise FileNotFoundError(
            f"ONNX reranker model not found at {model_dir}/model.onnx. "
            "Please run the download script first:\n"
            "  uv run --with optimum --with torch python scripts/download_reranker.py"
        )

    _tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
    _onnx_session = ort.InferenceSession(
        str(model_dir / "model.onnx"),
        providers=["CPUExecutionProvider"],
    )
    logger.info(f"BGE-reranker-v2-m3 ONNX loaded from {model_dir}")
    return _onnx_session, _tokenizer


def _get_vectordb():
    """Lazy-load ChromaDB to avoid import-time failures."""
    from langchain_chroma import Chroma
    from services.embedding import get_embeddings

    return Chroma(
        collection_name="finance_knowledge",
        embedding_function=get_embeddings(),
        persist_directory=settings.CHROMA_DIR,
    )


def _bm25_search(query: str, documents: list[dict[str, Any]], top_k: int = 10) -> list[dict]:
    """BM25 keyword-based search over document texts."""
    from rank_bm25 import BM25Okapi

    if not documents:
        return []

    corpus = [doc["page_content"] for doc in documents]
    tokenized_corpus = [doc.split() for doc in corpus]
    bm25 = BM25Okapi(tokenized_corpus)

    tokenized_query = query.split()
    scores = bm25.get_scores(tokenized_query)

    scored_docs = list(zip(scores, documents))
    scored_docs.sort(key=lambda x: x[0], reverse=True)
    return [doc for _, doc in scored_docs[:top_k]]


def _rerank(query: str, documents: list[str], top_n: int = 5) -> list[int]:
    """Rerank using BGE-reranker-v2-m3 (ONNX). Returns indices of top_n documents."""
    if not documents:
        return []

    try:
        session, tokenizer = _get_reranker()

        # Build query-document pairs for cross-encoder scoring
        pairs = [[query, doc] for doc in documents]
        inputs = tokenizer(
            pairs,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="np",
        )

        # Run ONNX inference
        ort_inputs = {k: v for k, v in inputs.items() if k in ("input_ids", "attention_mask", "token_type_ids")}
        outputs = session.run(None, ort_inputs)

        # BGE reranker outputs logits; higher = more relevant
        scores = outputs[0].flatten()
        if len(scores.shape) > 1:
            scores = scores[:, 0]

        # Return indices sorted by score descending
        ranked_indices = np.argsort(scores)[::-1][:top_n].tolist()
        return ranked_indices

    except Exception as e:
        logger.warning(f"BGE rerank 失败，回退到原始排序: {e}")
        return list(range(min(top_n, len(documents))))


@tool
def search_knowledge_base(query: str, top_k: int = 5) -> dict:
    """
    在金融知识库中进行混合检索（向量相似度 + BM25 关键词），并用 BGE 重排序。
    - query: 用户问题，如 "什么是市盈率"、"阿里巴巴的 ROE 是多少"
    - top_k: 返回最相关的文档数量，默认 5
    用于回答金融概念解释、公司财务指标、行业术语等知识性问题。
    如果知识库中没有相关内容，请如实告知，不要编造答案。
    """
    try:
        vectordb = _get_vectordb()

        # 1. Vector similarity search
        vector_results = vectordb.similarity_search(query, k=top_k * 2)
        vector_docs = [
            {"page_content": doc.page_content, "metadata": doc.metadata}
            for doc in vector_results
        ]

        # 2. BM25 keyword search (over same collection)
        # Get all documents for BM25 (limited to a reasonable size)
        try:
            collection = vectordb._collection
            all_data = collection.get(limit=1000)
            all_docs_for_bm25 = [
                {
                    "page_content": content,
                    "metadata": meta,
                }
                for content, meta in zip(
                    all_data.get("documents", []),
                    all_data.get("metadatas", []),
                )
            ]
            bm25_docs = _bm25_search(query, all_docs_for_bm25, top_k=top_k * 2)
        except Exception as e:
            logger.warning(f"BM25 检索失败，仅使用向量检索: {e}")
            bm25_docs = []

        # 3. Merge and deduplicate
        seen = set()
        merged = []
        for doc in vector_docs + bm25_docs:
            content_hash = hash(doc["page_content"][:200])
            if content_hash not in seen:
                seen.add(content_hash)
                merged.append(doc)

        if not merged:
            return {
                "query": query,
                "results": [],
                "message": "知识库中未找到相关内容",
            }

        # 4. Rerank with BGE-reranker-v2-m3 (ONNX)
        texts = [doc["page_content"] for doc in merged]
        top_indices = _rerank(query, texts, top_n=top_k)

        results = []
        for idx in top_indices:
            if idx < len(merged):
                results.append({
                    "content": merged[idx]["page_content"],
                    "source": merged[idx]["metadata"].get("source", "unknown"),
                    "type": merged[idx]["metadata"].get("type", "unknown"),
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
