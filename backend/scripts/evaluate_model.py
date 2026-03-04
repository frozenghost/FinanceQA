"""Model quality evaluation and comparison script.

Runs a standard evaluation dataset against one or more models, uses a judge model
to score answers on multiple dimensions, and generates comparison reports.

Usage:
    # Evaluate a single model
    uv run python scripts/evaluate_model.py --model anthropic/claude-opus-4.6

    # Evaluate multiple models and generate comparison report
    uv run python scripts/evaluate_model.py \
        --model anthropic/claude-opus-4.6 \
        --model openai/gpt-4o \
        --compare

    # Compare against a previously saved report
    uv run python scripts/evaluate_model.py \
        --model openai/gpt-4o \
        --compare-with ./eval/reports/report_anthropic_claude-opus-4.6_20260304.json
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

# Ensure backend root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from openai import AsyncOpenAI

from config.settings import settings

logger = logging.getLogger(__name__)

# ── Evaluation dimensions and their weights ────────────────────
DIMENSIONS = {
    "accuracy": {"weight": 0.30, "description": "事实准确性，数据是否正确"},
    "completeness": {"weight": 0.25, "description": "回答是否覆盖了问题的关键要点"},
    "relevance": {"weight": 0.20, "description": "回答与问题的相关程度"},
    "reasoning": {"weight": 0.15, "description": "分析推理的逻辑性与深度"},
    "language_quality": {"weight": 0.10, "description": "语言表达的流畅性、专业性与可读性"},
}

JUDGE_SYSTEM_PROMPT = """你是一个专业的金融问答系统质量评估员。你的任务是对 AI 模型的回答进行客观、严格的评分。

评分维度和标准（每个维度 1-10 分）：

1. **accuracy（准确性）**：回答中的事实、数据、概念是否准确。如果包含明显错误扣分。
2. **completeness（完整性）**：是否全面覆盖了问题涉及的关键知识点。遗漏重要信息扣分。
3. **relevance（相关性）**：回答是否紧扣问题主题。偏离主题或包含大量无关信息扣分。
4. **reasoning（推理质量）**：分析和推理是否有逻辑、有深度。浅尝辄止或逻辑混乱扣分。
5. **language_quality（语言质量）**：表达是否清晰、专业、易读。语法错误或表述混乱扣分。

你必须严格按照以下 JSON 格式输出评分结果，不要包含任何其他内容：

{
  "scores": {
    "accuracy": <1-10>,
    "completeness": <1-10>,
    "relevance": <1-10>,
    "reasoning": <1-10>,
    "language_quality": <1-10>
  },
  "strengths": "<回答的优点，1-2句话>",
  "weaknesses": "<回答的不足，1-2句话>",
  "overall_comment": "<总体评价，1-2句话>"
}"""


class ModelEvaluator:
    """Evaluates LLM model quality on a standard financial QA dataset."""

    def __init__(self):
        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.OPENROUTER_API_KEY,
        )
        self.dataset = self._load_dataset()

    def _load_dataset(self) -> dict:
        """Load evaluation dataset from configured path."""
        dataset_path = Path(settings.EVAL_DATASET_PATH)
        if not dataset_path.exists():
            raise FileNotFoundError(
                f"Evaluation dataset not found at {dataset_path}. "
                "Please create it or update EVAL_DATASET_PATH in .env"
            )
        with open(dataset_path, encoding="utf-8") as f:
            return json.load(f)

    async def _get_model_answer(self, model: str, question: str) -> tuple[str, float]:
        """Get answer from a model, return (answer, latency_seconds)."""
        start = time.monotonic()
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是一个专业的金融分析助手。请用中文回答问题，"
                            "确保回答准确、完整、有条理。如果涉及具体数据，请说明数据来源。"
                        ),
                    },
                    {"role": "user", "content": question},
                ],
                temperature=0.3,
                max_tokens=2000,
            )
            latency = time.monotonic() - start
            return response.choices[0].message.content or "", latency
        except Exception as e:
            latency = time.monotonic() - start
            logger.error(f"Model {model} failed on question: {e}")
            return f"[ERROR] {e}", latency

    async def _judge_answer(
        self, question: str, reference: str, answer: str, keywords: list[str]
    ) -> dict:
        """Use judge model to score an answer."""
        judge_prompt = f"""请评估以下 AI 模型的回答质量。

**问题**：{question}

**参考答案要点**：{reference}

**期望包含的关键词**：{', '.join(keywords)}

**模型实际回答**：
{answer}

请严格按照 JSON 格式给出评分。"""

        try:
            response = await self.client.chat.completions.create(
                model=settings.EVAL_JUDGE_MODEL,
                messages=[
                    {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                    {"role": "user", "content": judge_prompt},
                ],
                temperature=0.1,
                max_tokens=500,
            )

            content = response.choices[0].message.content or ""
            # Extract JSON from response (handle potential markdown wrapping)
            content = content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1]  # Remove first ```json line
                content = content.rsplit("```", 1)[0]  # Remove trailing ```

            result = json.loads(content)

            # Calculate keyword coverage
            answer_lower = answer.lower()
            keyword_hits = sum(1 for kw in keywords if kw.lower() in answer_lower)
            result["keyword_coverage"] = (
                round(keyword_hits / len(keywords), 2) if keywords else 1.0
            )

            return result

        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Judge model scoring failed: {e}")
            return {
                "scores": {dim: 0 for dim in DIMENSIONS},
                "strengths": "评分失败",
                "weaknesses": str(e),
                "overall_comment": "裁判模型评分出错",
                "keyword_coverage": 0.0,
            }

    def _calculate_weighted_score(self, scores: dict) -> float:
        """Calculate weighted overall score from dimension scores."""
        total = 0.0
        for dim, info in DIMENSIONS.items():
            total += scores.get(dim, 0) * info["weight"]
        return round(total, 2)

    async def evaluate_model(self, model: str) -> dict:
        """Run full evaluation for a single model."""
        logger.info(f"=== Starting evaluation for model: {model} ===")
        test_cases = self.dataset["test_cases"]
        results = []
        total_latency = 0.0

        for i, tc in enumerate(test_cases, 1):
            logger.info(
                f"  [{i}/{len(test_cases)}] Evaluating: {tc['id']} ({tc['category']})"
            )

            # Get model answer
            answer, latency = await self._get_model_answer(model, tc["question"])
            total_latency += latency

            # Judge the answer
            judgment = await self._judge_answer(
                question=tc["question"],
                reference=tc["reference_answer"],
                answer=answer,
                keywords=tc.get("expected_keywords", []),
            )

            weighted_score = self._calculate_weighted_score(judgment.get("scores", {}))

            result = {
                "test_case_id": tc["id"],
                "category": tc["category"],
                "difficulty": tc["difficulty"],
                "question": tc["question"],
                "model_answer": answer,
                "latency_seconds": round(latency, 2),
                "scores": judgment.get("scores", {}),
                "weighted_score": weighted_score,
                "keyword_coverage": judgment.get("keyword_coverage", 0.0),
                "strengths": judgment.get("strengths", ""),
                "weaknesses": judgment.get("weaknesses", ""),
                "overall_comment": judgment.get("overall_comment", ""),
            }
            results.append(result)
            logger.info(
                f"    Score: {weighted_score}/10 | Latency: {latency:.1f}s | "
                f"Keywords: {judgment.get('keyword_coverage', 0):.0%}"
            )

        # Aggregate statistics
        scores_list = [r["weighted_score"] for r in results]
        avg_score = round(sum(scores_list) / len(scores_list), 2) if scores_list else 0
        avg_latency = round(total_latency / len(results), 2) if results else 0

        # Per-category breakdown
        categories = {}
        for r in results:
            cat = r["category"]
            if cat not in categories:
                categories[cat] = {"scores": [], "count": 0}
            categories[cat]["scores"].append(r["weighted_score"])
            categories[cat]["count"] += 1

        category_summary = {}
        for cat, data in categories.items():
            category_summary[cat] = {
                "avg_score": round(sum(data["scores"]) / len(data["scores"]), 2),
                "count": data["count"],
            }

        # Per-dimension average
        dimension_avgs = {}
        for dim in DIMENSIONS:
            dim_scores = [r["scores"].get(dim, 0) for r in results]
            dimension_avgs[dim] = (
                round(sum(dim_scores) / len(dim_scores), 2) if dim_scores else 0
            )

        report = {
            "meta": {
                "model": model,
                "judge_model": settings.EVAL_JUDGE_MODEL,
                "evaluated_at": datetime.now().isoformat(),
                "dataset_version": self.dataset.get("version", "unknown"),
                "total_test_cases": len(results),
            },
            "summary": {
                "overall_score": avg_score,
                "avg_latency_seconds": avg_latency,
                "total_latency_seconds": round(total_latency, 2),
                "avg_keyword_coverage": round(
                    sum(r["keyword_coverage"] for r in results) / len(results), 2
                )
                if results
                else 0,
            },
            "dimension_averages": dimension_avgs,
            "category_breakdown": category_summary,
            "detailed_results": results,
        }

        logger.info(f"=== Evaluation complete for {model}: {avg_score}/10 ===")
        return report

    def save_report(self, report: dict) -> Path:
        """Save evaluation report to disk."""
        reports_dir = Path(settings.EVAL_REPORTS_DIR)
        reports_dir.mkdir(parents=True, exist_ok=True)

        model_safe = report["meta"]["model"].replace("/", "_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"report_{model_safe}_{timestamp}.json"
        filepath = reports_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        logger.info(f"Report saved to: {filepath}")
        return filepath

    @staticmethod
    def generate_comparison(reports: list[dict]) -> dict:
        """Generate a comparison report between multiple model evaluations."""
        if len(reports) < 2:
            raise ValueError("Need at least 2 reports to compare")

        comparison = {
            "meta": {
                "compared_at": datetime.now().isoformat(),
                "models": [r["meta"]["model"] for r in reports],
                "judge_model": reports[0]["meta"]["judge_model"],
            },
            "ranking": [],
            "dimension_comparison": {},
            "category_comparison": {},
            "head_to_head": [],
            "verdict": "",
        }

        # Overall ranking
        ranked = sorted(reports, key=lambda r: r["summary"]["overall_score"], reverse=True)
        for rank, r in enumerate(ranked, 1):
            comparison["ranking"].append(
                {
                    "rank": rank,
                    "model": r["meta"]["model"],
                    "overall_score": r["summary"]["overall_score"],
                    "avg_latency": r["summary"]["avg_latency_seconds"],
                    "keyword_coverage": r["summary"]["avg_keyword_coverage"],
                }
            )

        # Dimension comparison
        for dim in DIMENSIONS:
            dim_data = {}
            for r in reports:
                model = r["meta"]["model"]
                dim_data[model] = r["dimension_averages"].get(dim, 0)
            best_model = max(dim_data, key=dim_data.get)
            comparison["dimension_comparison"][dim] = {
                "scores": dim_data,
                "best": best_model,
                "diff": round(max(dim_data.values()) - min(dim_data.values()), 2),
            }

        # Category comparison
        all_categories = set()
        for r in reports:
            all_categories.update(r["category_breakdown"].keys())

        for cat in all_categories:
            cat_data = {}
            for r in reports:
                model = r["meta"]["model"]
                cat_data[model] = (
                    r["category_breakdown"].get(cat, {}).get("avg_score", 0)
                )
            best_model = max(cat_data, key=cat_data.get)
            comparison["category_comparison"][cat] = {
                "scores": cat_data,
                "best": best_model,
            }

        # Head-to-head per test case
        if len(reports) == 2:
            r1, r2 = reports[0], reports[1]
            m1, m2 = r1["meta"]["model"], r2["meta"]["model"]
            m1_wins = 0
            m2_wins = 0
            ties = 0

            for d1, d2 in zip(r1["detailed_results"], r2["detailed_results"]):
                s1 = d1["weighted_score"]
                s2 = d2["weighted_score"]
                if abs(s1 - s2) < 0.3:
                    winner = "tie"
                    ties += 1
                elif s1 > s2:
                    winner = m1
                    m1_wins += 1
                else:
                    winner = m2
                    m2_wins += 1

                comparison["head_to_head"].append(
                    {
                        "test_case_id": d1["test_case_id"],
                        "category": d1["category"],
                        f"{m1}_score": s1,
                        f"{m2}_score": s2,
                        "diff": round(s1 - s2, 2),
                        "winner": winner,
                    }
                )

            comparison["head_to_head_summary"] = {
                m1: m1_wins,
                m2: m2_wins,
                "ties": ties,
            }

        # Generate verdict
        best = comparison["ranking"][0]
        worst = comparison["ranking"][-1]
        diff = round(best["overall_score"] - worst["overall_score"], 2)

        if diff < 0.3:
            verdict_quality = "两个模型表现基本相当"
        elif diff < 1.0:
            verdict_quality = f"{best['model']} 略优于 {worst['model']}"
        elif diff < 2.0:
            verdict_quality = f"{best['model']} 明显优于 {worst['model']}"
        else:
            verdict_quality = f"{best['model']} 显著优于 {worst['model']}"

        latency_diff = best["avg_latency"] - worst["avg_latency"]
        if abs(latency_diff) < 1.0:
            verdict_speed = "响应速度相近"
        elif latency_diff > 0:
            verdict_speed = f"但 {worst['model']} 响应更快（快 {abs(latency_diff):.1f}s）"
        else:
            verdict_speed = f"且 {best['model']} 响应也更快（快 {abs(latency_diff):.1f}s）"

        comparison["verdict"] = (
            f"综合评分：{verdict_quality}（{best['overall_score']} vs {worst['overall_score']}）。"
            f"{verdict_speed}。"
        )

        return comparison

    def save_comparison(self, comparison: dict) -> Path:
        """Save comparison report to disk."""
        reports_dir = Path(settings.EVAL_REPORTS_DIR)
        reports_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        models_str = "_vs_".join(
            m.replace("/", "_") for m in comparison["meta"]["models"]
        )
        filename = f"comparison_{models_str}_{timestamp}.json"
        filepath = reports_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(comparison, f, ensure_ascii=False, indent=2)

        logger.info(f"Comparison report saved to: {filepath}")
        return filepath

    def print_report_summary(self, report: dict):
        """Print a human-readable summary to console."""
        meta = report["meta"]
        summary = report["summary"]

        print("\n" + "=" * 60)
        print(f"  模型评估报告")
        print("=" * 60)
        print(f"  模型：{meta['model']}")
        print(f"  裁判模型：{meta['judge_model']}")
        print(f"  评估时间：{meta['evaluated_at']}")
        print(f"  测试用例数：{meta['total_test_cases']}")
        print("-" * 60)
        print(f"  综合评分：{summary['overall_score']} / 10")
        print(f"  平均延迟：{summary['avg_latency_seconds']}s")
        print(f"  关键词覆盖率：{summary['avg_keyword_coverage']:.0%}")
        print("-" * 60)

        print("\n  各维度平均分：")
        for dim, score in report["dimension_averages"].items():
            bar = "█" * int(score) + "░" * (10 - int(score))
            print(f"    {dim:20s} {bar} {score}/10")

        print("\n  各类别表现：")
        for cat, data in report["category_breakdown"].items():
            print(f"    {cat:12s} {data['avg_score']}/10 ({data['count']} 题)")

        print("=" * 60 + "\n")

    def print_comparison_summary(self, comparison: dict):
        """Print a human-readable comparison summary."""
        print("\n" + "=" * 60)
        print(f"  模型对比报告")
        print("=" * 60)
        print(f"  对比时间：{comparison['meta']['compared_at']}")
        print("-" * 60)

        print("\n  总排名：")
        for entry in comparison["ranking"]:
            medal = ["🥇", "🥈", "🥉"][entry["rank"] - 1] if entry["rank"] <= 3 else "  "
            print(
                f"    {medal} #{entry['rank']} {entry['model']:40s} "
                f"分数: {entry['overall_score']}/10  延迟: {entry['avg_latency']}s"
            )

        print("\n  各维度对比：")
        for dim, data in comparison["dimension_comparison"].items():
            print(f"    {dim}:")
            for model, score in data["scores"].items():
                marker = " ← 最佳" if model == data["best"] else ""
                print(f"      {model:40s} {score}/10{marker}")

        if "head_to_head_summary" in comparison:
            print("\n  胜负统计：")
            for key, val in comparison["head_to_head_summary"].items():
                print(f"    {key}: {val}")

        print(f"\n  结论：{comparison['verdict']}")
        print("=" * 60 + "\n")


async def main():
    parser = argparse.ArgumentParser(description="Model quality evaluation tool")
    parser.add_argument(
        "--model",
        action="append",
        required=True,
        help="Model to evaluate (can specify multiple with repeated --model flags)",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Generate comparison report when evaluating multiple models",
    )
    parser.add_argument(
        "--compare-with",
        type=str,
        help="Path to a previously saved report JSON to compare against",
    )
    args = parser.parse_args()

    evaluator = ModelEvaluator()
    reports = []

    # Evaluate each specified model
    for model in args.model:
        report = await evaluator.evaluate_model(model)
        filepath = evaluator.save_report(report)
        evaluator.print_report_summary(report)
        reports.append(report)
        print(f"  报告已保存: {filepath}\n")

    # Load comparison baseline if specified
    if args.compare_with:
        with open(args.compare_with, encoding="utf-8") as f:
            baseline_report = json.load(f)
        reports.insert(0, baseline_report)
        logger.info(f"Loaded baseline report: {args.compare_with}")

    # Generate comparison if we have multiple reports
    if (args.compare or args.compare_with) and len(reports) >= 2:
        comparison = evaluator.generate_comparison(reports)
        comp_path = evaluator.save_comparison(comparison)
        evaluator.print_comparison_summary(comparison)
        print(f"  对比报告已保存: {comp_path}\n")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    asyncio.run(main())
