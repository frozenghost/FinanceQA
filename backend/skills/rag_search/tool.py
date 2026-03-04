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
    """BM25 keyword-based search over document texts with improved tokenization."""
    from rank_bm25 import BM25Okapi
    import jieba

    if not documents:
        return []

    corpus = [doc["page_content"] for doc in documents]
    
    # 改进分词：中文用jieba，英文用空格
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
    """Rerank using BGE-reranker-v2-m3 (ONNX). Returns list of (index, score) tuples."""
    if not documents:
        return []

    try:
        session, tokenizer = _get_reranker()

        # Build query-document pairs for cross-encoder scoring
        pairs = [[query, doc[:512]] for doc in documents]  # 截断过长文本
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
        scores = outputs[0]
        if len(scores.shape) > 1:
            scores = scores[:, 0]
        scores = scores.flatten()

        # Return (index, score) pairs sorted by score descending
        scored_indices = [(i, float(scores[i])) for i in range(len(scores))]
        scored_indices.sort(key=lambda x: x[1], reverse=True)
        return scored_indices[:top_n]

    except Exception as e:
        logger.warning(f"BGE rerank 失败，回退到原始排序: {e}")
        # 回退时返回带默认分数的结果
        return [(i, 0.0) for i in range(min(top_n, len(documents)))]


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

        # 1. Vector similarity search with scores
        vector_results_with_scores = vectordb.similarity_search_with_score(query, k=top_k * 3)
        vector_docs = [
            {
                "page_content": doc.page_content, 
                "metadata": doc.metadata,
                "vector_score": float(score),
            }
            for doc, score in vector_results_with_scores
        ]

        # 2. BM25 keyword search (优化：只在向量召回的候选集上做BM25)
        bm25_docs = []
        if vector_docs:
            try:
                bm25_docs = _bm25_search(query, vector_docs, top_k=top_k * 2)
            except Exception as e:
                logger.warning(f"BM25 检索失败，仅使用向量检索: {e}")

        # 3. Merge and deduplicate (改进：用完整内容hash + 相邻chunk合并)
        seen = set()
        merged = []
        parent_chunks = {}  # 用于合并同一文档的相邻chunks
        
        for doc in vector_docs + bm25_docs:
            content_hash = hash(doc["page_content"])
            if content_hash not in seen:
                seen.add(content_hash)
                
                # 尝试合并相邻chunks
                parent_id = doc["metadata"].get("parent_doc_id")
                chunk_idx = doc["metadata"].get("chunk_index")
                
                if parent_id and chunk_idx is not None:
                    key = f"{parent_id}_{chunk_idx}"
                    if key not in parent_chunks:
                        parent_chunks[key] = doc
                        merged.append(doc)
                else:
                    merged.append(doc)

        if not merged:
            return {
                "query": query,
                "results": [],
                "message": "知识库中未找到相关内容",
            }

        # 4. Rerank with BGE-reranker-v2-m3 (ONNX)
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
                    "rerank_score": rerank_score,
                    "vector_score": doc.get("vector_score"),
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
