"""
Tests for Phase 3 — Agent Layer
=================================
Tests goal system, attention scoring, goal matching,
and the brain loop with simulated memories.
"""

import json
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ═══════════════════════════════════════════════════════════════════
#  TEST DATA — Simulated memories
# ═══════════════════════════════════════════════════════════════════

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

def _hours_ago_iso(hours):
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


SAMPLE_MEMORIES = [
    {
        "question": "What is overfitting in machine learning?",
        "answer": "Overfitting in machine learning refers to a situation where a model learns the training data too well, including noise, and performs poorly on new data. This happens when the model is too complex for the amount of data.",
        "timestamp": _hours_ago_iso(2),  # 2 hours ago — very recent
    },
    {
        "question": "How does the bias-variance tradeoff relate to overfitting?",
        "answer": "The bias-variance tradeoff describes the balance between underfitting and overfitting. High variance means the model overfits. The goal is to find optimal complexity that minimizes both.",
        "timestamp": _hours_ago_iso(4),  # 4 hours ago
    },
    {
        "question": "What are embeddings and how are they used in RAG?",
        "answer": "Embeddings are dense vector representations of text. In RAG, we embed both documents and queries, then find similar vectors in a database to retrieve relevant context for the LLM.",
        "timestamp": _hours_ago_iso(24),  # 1 day ago
    },
    {
        "question": "How does gradient descent work?",
        "answer": "Gradient descent is an optimization algorithm that iteratively adjusts model parameters by computing the gradient of the loss function and moving in the direction that reduces the loss.",
        "timestamp": _hours_ago_iso(72),  # 3 days ago
    },
    {
        "question": "What is the weather like today?",
        "answer": "I don't have access to weather data. I can only answer questions based on your personal documents.",
        "timestamp": _hours_ago_iso(48),  # 2 days ago — irrelevant
    },
    {
        "question": "Explain the transformer architecture and attention mechanism",
        "answer": "The transformer architecture uses self-attention to process sequences in parallel. Attention computes weighted sums of values based on query-key compatibility, enabling the model to focus on relevant parts of the input.",
        "timestamp": _hours_ago_iso(6),  # 6 hours ago
    },
]

SAMPLE_GOALS = [
    {
        "id": "goal_001",
        "title": "Master Machine Learning Fundamentals",
        "description": "Build a deep understanding of core ML concepts",
        "priority": 8,
        "keywords": ["machine learning", "overfitting", "bias", "variance",
                     "regularization", "gradient descent", "training"],
        "progress": 20,
    },
    {
        "id": "goal_002",
        "title": "Build AI-Powered Applications",
        "description": "Learn to integrate AI models into real-world applications",
        "priority": 9,
        "keywords": ["RAG", "embeddings", "vector database", "LLM",
                     "prompt engineering", "pipeline"],
        "progress": 35,
    },
    {
        "id": "goal_003",
        "title": "Deep Learning & Neural Networks",
        "description": "Understand neural network architectures",
        "priority": 7,
        "keywords": ["deep learning", "neural network", "transformer",
                     "attention", "backpropagation", "CNN", "RNN"],
        "progress": 10,
    },
]


# ═══════════════════════════════════════════════════════════════════
#  TEST 1: Goal System
# ═══════════════════════════════════════════════════════════════════

def test_goal_loading():
    """Test that goals load correctly from a temp file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(SAMPLE_GOALS, f)
        temp_path = Path(f.name)

    try:
        with patch("src.goals.GOALS_FILE", temp_path):
            from src.goals import load_goals
            goals = load_goals()
            assert len(goals) == 3, f"Expected 3 goals, got {len(goals)}"
            assert goals[0]["id"] == "goal_001"
            assert goals[1]["priority"] == 9
            print("✅ Test 1.1: Goal loading — PASSED")
    finally:
        temp_path.unlink()


def test_goal_matching():
    """Test keyword-based goal matching."""
    from src.goals import match_goals

    # Text about ML should match goal_001
    text = "Overfitting in machine learning happens when the model is too complex"
    matches = match_goals(text, SAMPLE_GOALS)

    assert len(matches) > 0, "Should match at least one goal"
    assert matches[0]["goal"]["id"] == "goal_001", (
        "Top match should be ML goal"
    )
    assert "overfitting" in [kw.lower() for kw in matches[0]["matched_keywords"]]
    print(f"✅ Test 1.2: Goal matching — PASSED ({len(matches)} matches)")

    # Text about weather should NOT match any goals
    text = "What is the weather like today?"
    matches = match_goals(text, SAMPLE_GOALS)
    assert len(matches) == 0, "Weather should not match any goals"
    print("✅ Test 1.3: No-match case — PASSED")


# ═══════════════════════════════════════════════════════════════════
#  TEST 2: Attention System
# ═══════════════════════════════════════════════════════════════════

def test_attention_scoring():
    """Test that memories are scored and ranked correctly."""
    from src.agent.attention import compute_score, rank_memories

    # Score a single recent ML memory — should be high
    ml_memory = SAMPLE_MEMORIES[0]  # Overfitting, 2 hours ago
    score = compute_score(ml_memory, SAMPLE_MEMORIES, SAMPLE_GOALS)
    assert 0.0 <= score <= 1.0, f"Score out of range: {score}"
    assert score > 0.3, f"Recent ML memory should score high, got {score:.3f}"
    print(f"✅ Test 2.1: Single memory scoring — PASSED (score={score:.3f})")

    # Score the weather memory — should be low
    weather_memory = SAMPLE_MEMORIES[4]  # Weather, no goal match
    weather_score = compute_score(weather_memory, SAMPLE_MEMORIES, SAMPLE_GOALS)
    assert weather_score < score, (
        f"Weather ({weather_score:.3f}) should score lower than ML ({score:.3f})"
    )
    print(f"✅ Test 2.2: Low-relevance scoring — PASSED (score={weather_score:.3f})")


def test_memory_ranking():
    """Test that memories are ranked in the correct order."""
    from src.agent.attention import rank_memories

    ranked = rank_memories(SAMPLE_MEMORIES, SAMPLE_GOALS)

    assert len(ranked) == len(SAMPLE_MEMORIES), "All memories should be ranked"

    # Check scores are descending
    scores = [m["attention_score"] for m in ranked]
    assert scores == sorted(scores, reverse=True), "Scores should be descending"

    # The weather memory should be near the bottom
    weather_idx = next(
        i for i, m in enumerate(ranked)
        if "weather" in m.get("question", "").lower()
    )
    assert weather_idx >= len(ranked) - 2, (
        f"Weather should be near bottom, was at index {weather_idx}"
    )

    print("✅ Test 2.3: Memory ranking order — PASSED")
    print("   Ranking results:")
    for i, m in enumerate(ranked):
        goals = ", ".join(m.get("matched_goals", [])) or "none"
        print(
            f"   #{i+1} [{m['attention_score']:.3f}] "
            f"Q: {m['question'][:50]}... "
            f"(goals: {goals})"
        )


# ═══════════════════════════════════════════════════════════════════
#  TEST 3: Insight Parsing
# ═══════════════════════════════════════════════════════════════════

def test_insight_parsing():
    """Test that LLM responses are correctly parsed into insights."""
    from src.agent.insights import _parse_insights, _filter_trivial

    raw = """1. You should explore regularization techniques like L1/L2 to address your overfitting concerns from recent sessions.
2. Consider implementing a simple RAG evaluation pipeline to measure retrieval quality.
3. The transformer attention mechanism connects to your embeddings work — try visualizing attention weights.
4. Keep learning.
5. Good job on your progress."""

    insights = _parse_insights(raw)
    assert len(insights) >= 3, f"Should parse at least 3 insights, got {len(insights)}"
    print(f"✅ Test 3.1: Insight parsing — PASSED ({len(insights)} parsed)")

    # Filter trivial ones
    filtered = _filter_trivial(insights)
    assert len(filtered) < len(insights), "Should filter out trivial insights"
    print(f"✅ Test 3.2: Trivial filtering — PASSED ({len(insights)} → {len(filtered)})")


# ═══════════════════════════════════════════════════════════════════
#  TEST 4: Brain Loop (single cycle, mocked LLM)
# ═══════════════════════════════════════════════════════════════════

def test_brain_loop_cycle():
    """Test a single brain loop cycle with mocked LLM."""
    from src.agent.brain_loop import BrainLoop

    mock_llm_response = """1. Your recurring focus on overfitting suggests exploring regularization techniques like dropout and L2 penalty.
2. Connect your RAG pipeline knowledge with the transformer architecture — consider implementing attention-based reranking.
3. Gradient descent foundations can be reinforced by implementing a simple neural network from scratch."""

    with patch("src.agent.brain_loop.load_memory", return_value=SAMPLE_MEMORIES), \
         patch("src.agent.brain_loop.load_goals", return_value=SAMPLE_GOALS), \
         patch("src.agent.insights.LLMClient") as MockLLM, \
         patch("src.agent.notifier._send_notification", return_value=True):

        # Mock the LLM
        mock_instance = MagicMock()
        mock_instance.generate.return_value = mock_llm_response
        MockLLM.return_value = mock_instance

        loop = BrainLoop(interval=300)
        result = loop.run_once()

        assert result["memories_loaded"] == 6, (
            f"Should load 6 memories, got {result['memories_loaded']}"
        )
        assert result["memories_above_threshold"] > 0, (
            "Should have memories above threshold"
        )
        assert result["insights_generated"] > 0, (
            "Should generate insights"
        )
        print(f"✅ Test 4.1: Brain loop cycle — PASSED")
        print(f"   Loaded: {result['memories_loaded']} memories")
        print(f"   Above threshold: {result['memories_above_threshold']}")
        print(f"   Insights: {result['insights_generated']}")
        print(f"   Notifications: {result['notifications_sent']}")


# ═══════════════════════════════════════════════════════════════════
#  TEST 5: Notification System
# ═══════════════════════════════════════════════════════════════════

def test_notification_truncation():
    """Test message truncation and anti-spam."""
    from src.agent.notifier import _truncate, reset_cooldown

    # Test truncation
    short = "Hello"
    assert _truncate(short, 200) == short, "Short messages should not be truncated"

    long = "x" * 300
    truncated = _truncate(long, 200)
    assert len(truncated) <= 200, f"Should truncate to 200, got {len(truncated)}"
    assert truncated.endswith("..."), "Should end with ..."
    print("✅ Test 5.1: Notification truncation — PASSED")

    # Reset cooldown for testing
    reset_cooldown()
    print("✅ Test 5.2: Cooldown reset — PASSED")


# ═══════════════════════════════════════════════════════════════════
#  RUN ALL TESTS
# ═══════════════════════════════════════════════════════════════════

def run_all():
    """Run all Phase 3 tests."""
    print("=" * 60)
    print("  Phase 3 — Agent Layer Tests")
    print("=" * 60)
    print()

    tests = [
        ("Goal Loading", test_goal_loading),
        ("Goal Matching", test_goal_matching),
        ("Attention Scoring", test_attention_scoring),
        ("Memory Ranking", test_memory_ranking),
        ("Insight Parsing", test_insight_parsing),
        ("Brain Loop Cycle", test_brain_loop_cycle),
        ("Notification System", test_notification_truncation),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        try:
            print(f"\n── {name} ──")
            test_fn()
            passed += 1
        except Exception as e:
            print(f"❌ {name} — FAILED: {e}")
            failed += 1
            import traceback
            traceback.print_exc()

    print(f"\n{'=' * 60}")
    print(f"  Results: {passed} passed, {failed} failed")
    print(f"{'=' * 60}")

    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
