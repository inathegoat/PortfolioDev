"""src/core/metrics.py — Runtime metrics tracking for RAG pipeline.

Tracks latency, error rates, top-k recall, and token estimates.
"""
import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class QueryMetrics:
    """Metrics for a single RAG query."""
    timestamp: str = ""
    question: str = ""
    answer_len: int = 0
    latency_ms: float = 0.0
    chunks_retrieved: int = 0
    chunks_used: int = 0
    top_k_recall: float = 0.0  # chunks_used / chunks_retrieved
    error: Optional[str] = None
    sources: List[str] = field(default_factory=list)


class MetricsCollector:
    """Thread-safe metrics collector for the RAG pipeline.

    Usage:
        collector = MetricsCollector()
        collector.record_query(metrics)
        print(collector.summary())
    """

    def __init__(self, max_history: int = 1000):
        self._lock = threading.Lock()
        self.queries: List[QueryMetrics] = []
        self.max_history = max_history
        self._start_time = time.time()
        self._error_counts: Dict[str, int] = defaultdict(int)

    def record_query(self, m: QueryMetrics):
        with self._lock:
            self.queries.append(m)
            if m.error:
                self._error_counts[m.error[:50]] += 1
            # Trim old entries
            if len(self.queries) > self.max_history:
                self.queries = self.queries[-self.max_history:]

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            n = len(self.queries)
            if n == 0:
                return {"total_queries": 0}

            latencies = [q.latency_ms for q in self.queries]
            recalls = [q.top_k_recall for q in self.queries if q.chunks_retrieved > 0]
            errors = sum(1 for q in self.queries if q.error)
            uptime_s = time.time() - self._start_time

            return {
                "total_queries": n,
                "errors": errors,
                "error_rate": round(errors / n, 4) if n else 0,
                "uptime_seconds": round(uptime_s, 0),
                "qps": round(n / uptime_s, 3) if uptime_s > 0 else 0,
                "latency": {
                    "avg_ms": round(sum(latencies) / len(latencies), 1),
                    "p50_ms": round(sorted(latencies)[len(latencies) // 2], 1),
                    "p95_ms": round(sorted(latencies)[int(len(latencies) * 0.95)], 1),
                    "p99_ms": round(sorted(latencies)[int(len(latencies) * 0.99)], 1),
                    "min_ms": round(min(latencies), 1),
                    "max_ms": round(max(latencies), 1),
                },
                "top_k_recall": {
                    "avg": round(sum(recalls) / len(recalls), 3) if recalls else 0,
                },
                "avg_chunks_used": round(sum(q.chunks_used for q in self.queries) / n, 1),
                "top_errors": dict(
                    sorted(self._error_counts.items(), key=lambda x: -x[1])[:5]
                ),
            }

    def reset(self):
        with self._lock:
            self.queries.clear()
            self._error_counts.clear()
            self._start_time = time.time()

    def __len__(self) -> int:
        return len(self.queries)


# Global singleton
_global_collector: Optional[MetricsCollector] = None


def get_collector() -> MetricsCollector:
    global _global_collector
    if _global_collector is None:
        _global_collector = MetricsCollector()
    return _global_collector
