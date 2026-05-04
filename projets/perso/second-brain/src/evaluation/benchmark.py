"""src/evaluation/benchmark.py — RAG evaluation framework.

Metrics:
- Faithfulness: Does the answer stick to retrieved context?
- Relevance: Is the retrieved context relevant to the question?
- Answer correctness: Is the answer factually correct vs ground truth?
- Chunk recall: How many expected chunks were retrieved?
- Latency: End-to-end response time.

Usage:
    benchmark = RAGBenchmark(rag_pipeline)
    benchmark.add_case(question="...", ground_truth="...", expected_sources=["doc1.txt"])
    report = benchmark.run()
"""
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class EvalCase:
    """A single evaluation test case."""
    question: str
    ground_truth: str        # Expected answer or key facts
    expected_sources: List[str] = field(default_factory=list)  # Expected document names
    min_sources: int = 1     # Minimum number of sources expected


@dataclass
class EvalMetrics:
    """Metrics for a single evaluation."""
    question: str
    faithfulness: float       # 0-1: does answer use only retrieved context?
    relevance: float          # 0-1: is retrieved context relevant?
    answer_correctness: float # 0-1: does answer match ground truth?
    chunk_recall: float       # 0-1: how many expected sources were retrieved?
    latency_ms: float         # end-to-end time
    num_chunks_retrieved: int
    sources_found: List[str] = field(default_factory=list)


@dataclass
class EvalReport:
    """Aggregate evaluation report."""
    cases: List[EvalMetrics] = field(default_factory=list)
    avg_faithfulness: float = 0.0
    avg_relevance: float = 0.0
    avg_answer_correctness: float = 0.0
    avg_chunk_recall: float = 0.0
    avg_latency_ms: float = 0.0
    total_cases: int = 0
    passed: int = 0  # cases with answer_correctness > 0.5


class RAGBenchmark:
    """Local benchmark for RAG pipeline evaluation.

    Usage:
        bm = RAGBenchmark(rag)
        bm.load_cases("benchmark_cases.json")
        report = bm.run()
        print(bm.format_report(report))
    """

    def __init__(self, rag_pipeline, llm_client=None):
        self.rag = rag_pipeline
        self.llm = llm_client or rag_pipeline.llm_client
        self.cases: List[EvalCase] = []

    def add_case(
        self,
        question: str,
        ground_truth: str,
        expected_sources: Optional[List[str]] = None,
        min_sources: int = 1,
    ):
        self.cases.append(EvalCase(question, ground_truth, expected_sources or [], min_sources))

    def load_cases(self, path: str):
        """Load cases from a JSON file.

        Format:
        [
            {
                "question": "...",
                "ground_truth": "...",
                "expected_sources": ["doc1.txt"],
                "min_sources": 1
            }
        ]
        """
        with open(path) as f:
            data = json.load(f)
        for item in data:
            self.add_case(**item)
        logger.info(f"Loaded {len(data)} evaluation cases from {path}")

    def run(self) -> EvalReport:
        """Run all evaluation cases and return a report."""
        metrics_list = []
        for case in self.cases:
            m = self._evaluate_case(case)
            metrics_list.append(m)
            logger.info(
                f"Q: {m.question[:50]}... | "
                f"faith={m.faithfulness:.2f} rel={m.relevance:.2f} "
                f"correct={m.answer_correctness:.2f} recall={m.chunk_recall:.2f} "
                f"lat={m.latency_ms:.0f}ms"
            )

        n = len(metrics_list)
        report = EvalReport(
            cases=metrics_list,
            avg_faithfulness=sum(m.faithfulness for m in metrics_list) / n,
            avg_relevance=sum(m.relevance for m in metrics_list) / n,
            avg_answer_correctness=sum(m.answer_correctness for m in metrics_list) / n,
            avg_chunk_recall=sum(m.chunk_recall for m in metrics_list) / n,
            avg_latency_ms=sum(m.latency_ms for m in metrics_list) / n,
            total_cases=n,
            passed=sum(1 for m in metrics_list if m.answer_correctness > 0.5),
        )
        return report

    def _evaluate_case(self, case: EvalCase) -> EvalMetrics:
        """Evaluate a single case."""
        start = time.time()
        response = self.rag.query(case.question)
        latency_ms = (time.time() - start) * 1000

        # Source recall
        sources_found = [s.get("source_file", "") for s in response.sources]
        expected = set(case.expected_sources)
        found = set(sources_found)
        chunk_recall = len(expected & found) / len(expected) if expected else 1.0

        # Faithfulness: LLM-based evaluation
        faithfulness = self._score_faithfulness(case.question, response.answer, response.sources)

        # Relevance: ratio of high-relevance chunks
        if response.sources:
            relevance = sum(
                s.get("relevance", 0) for s in response.sources
            ) / len(response.sources)
        else:
            relevance = 0.0

        # Answer correctness: LLM-based evaluation
        answer_correctness = self._score_correctness(
            case.question, response.answer, case.ground_truth
        )

        return EvalMetrics(
            question=case.question,
            faithfulness=faithfulness,
            relevance=relevance,
            answer_correctness=answer_correctness,
            chunk_recall=chunk_recall,
            latency_ms=latency_ms,
            num_chunks_retrieved=response.num_chunks_used,
            sources_found=sources_found,
        )

    def _score_faithfulness(
        self,
        question: str,
        answer: str,
        sources: List[dict],
    ) -> float:
        """LLM-based faithfulness: does the answer only use the provided context?"""
        if not sources:
            return 1.0 if not answer.strip() else 0.0
        try:
            context = "\n".join(s.get("preview", "") for s in sources[:3])
            prompt = (
                f"Rate how faithful this answer is to the provided context (0-1).\n"
                f"1.0 = entirely based on context, 0.0 = hallucinated.\n\n"
                f"Question: {question}\n\n"
                f"Context: {context}\n\n"
                f"Answer: {answer}\n\n"
                f"Faithfulness score (0-1):"
            )
            score = self.llm.generate(prompt=prompt, temperature=0.0, max_tokens=5)
            return max(0.0, min(1.0, float("".join(c for c in score if c in "0123456789.") or "0.5")))
        except Exception:
            return 0.5

    def _score_correctness(self, question: str, answer: str, ground_truth: str) -> float:
        """LLM-based answer correctness: does the answer match ground truth?"""
        try:
            prompt = (
                f"Rate how correct this answer is compared to the ground truth (0-1).\n"
                f"1.0 = perfectly correct, 0.0 = completely wrong.\n\n"
                f"Question: {question}\n\n"
                f"Ground truth: {ground_truth}\n\n"
                f"Answer: {answer}\n\n"
                f"Correctness score (0-1):"
            )
            score = self.llm.generate(prompt=prompt, temperature=0.0, max_tokens=5)
            return max(0.0, min(1.0, float("".join(c for c in score if c in "0123456789.") or "0.5")))
        except Exception:
            return 0.5

    @staticmethod
    def format_report(report: EvalReport) -> str:
        """Format an evaluation report as a readable string."""
        lines = [
            "=" * 60,
            "       RAG Evaluation Report",
            "=" * 60,
            f"Cases:        {report.total_cases}",
            f"Passed (>0.5): {report.passed}/{report.total_cases}",
            "",
            "Average Metrics:",
            f"  Faithfulness:       {report.avg_faithfulness:.3f}",
            f"  Relevance:          {report.avg_relevance:.3f}",
            f"  Answer Correctness: {report.avg_answer_correctness:.3f}",
            f"  Chunk Recall:       {report.avg_chunk_recall:.3f}",
            f"  Latency:            {report.avg_latency_ms:.0f} ms",
            "=" * 60,
        ]
        return "\n".join(lines)

    def save_report(self, report: EvalReport, path: str):
        """Save the report as JSON."""
        data = {
            "summary": {
                "total_cases": report.total_cases,
                "passed": report.passed,
                "avg_faithfulness": report.avg_faithfulness,
                "avg_relevance": report.avg_relevance,
                "avg_answer_correctness": report.avg_answer_correctness,
                "avg_chunk_recall": report.avg_chunk_recall,
                "avg_latency_ms": report.avg_latency_ms,
            },
            "details": [
                {
                    "question": m.question,
                    "faithfulness": m.faithfulness,
                    "relevance": m.relevance,
                    "answer_correctness": m.answer_correctness,
                    "chunk_recall": m.chunk_recall,
                    "latency_ms": m.latency_ms,
                    "sources_found": m.sources_found,
                }
                for m in report.cases
            ],
        }
        Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False))
        logger.info(f"Report saved to {path}")
