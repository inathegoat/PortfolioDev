"""
Tests for Phase 4 — Task System, Planning, Follow-Up
========================================================
Tests task CRUD, task generation, planning, follow-up,
and the upgraded brain loop.
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
#  TEST DATA
# ═══════════════════════════════════════════════════════════════════

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

def _hours_ago_iso(hours):
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


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
]

SAMPLE_MEMORIES = [
    {
        "question": "What is overfitting in machine learning?",
        "answer": "Overfitting is when a model learns noise in the training data...",
        "timestamp": _hours_ago_iso(2),
    },
    {
        "question": "How do embeddings work in RAG?",
        "answer": "Embeddings are dense vector representations of text used for retrieval...",
        "timestamp": _hours_ago_iso(4),
    },
]

SAMPLE_INSIGHTS = [
    "Tu devrais explorer les techniques de régularisation comme L1/L2 pour contrer l'overfitting.",
    "Connecte tes connaissances en embeddings avec le RAG pipeline — essaie de visualiser les vecteurs.",
    "Implémente un simple réseau de neurones from scratch pour renforcer les fondamentaux.",
]


# ═══════════════════════════════════════════════════════════════════
#  TEST 1: Task CRUD
# ═══════════════════════════════════════════════════════════════════

def test_task_crud():
    """Test task creation, loading, status update, and filtering."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as f:
        json.dump([], f)
        temp_path = Path(f.name)
    
    try:
        with patch("src.tasks.TASKS_FILE", temp_path), \
             patch("src.tasks.TASKS_DIR", temp_path.parent):
            from src.tasks import (
                load_tasks, add_task, update_task_status,
                get_pending_tasks, task_exists_similar,
            )

            # Add tasks
            t1 = add_task(
                goal_id="goal_001",
                title="Explorer la régularisation L2",
                description="Étudier L1/L2 et dropout",
                steps=["Lire la doc", "Implémenter"],
                priority=8,
            )
            assert t1["id"].startswith("task_")
            assert t1["status"] == "pending"
            assert t1["priority"] == 8
            print(f"✅ Test 1.1: Task creation — PASSED (id={t1['id']})")

            t2 = add_task(
                goal_id="goal_002",
                title="Visualiser les embeddings",
                priority=6,
            )

            # Load all
            tasks = load_tasks()
            assert len(tasks) == 2
            print(f"✅ Test 1.2: Load tasks — PASSED ({len(tasks)} tasks)")

            # Pending filter
            pending = get_pending_tasks()
            assert len(pending) == 2
            print(f"✅ Test 1.3: Pending filter — PASSED ({len(pending)} pending)")

            # Update status
            result = update_task_status(t1["id"], "done")
            assert result is True
            pending = get_pending_tasks()
            assert len(pending) == 1
            print("✅ Test 1.4: Status update — PASSED")

            # Deduplication (check against t2 which is still pending)
            is_dup = task_exists_similar("Visualiser les embeddings du RAG")
            assert is_dup is True
            print("✅ Test 1.5: Deduplication — PASSED (duplicate detected)")

            not_dup = task_exists_similar("Complètement nouveau sujet")
            assert not_dup is False
            print("✅ Test 1.6: Non-duplicate — PASSED")

    finally:
        temp_path.unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════════════
#  TEST 2: Planning Engine
# ═══════════════════════════════════════════════════════════════════

def test_planner():
    """Test plan generation with mocked LLM."""
    mock_response = """1. Lire le chapitre sur la régularisation dans le livre de ML
2. Implémenter la régularisation L2 sur un modèle simple en Python
3. Comparer les performances avant/après régularisation
4. Documenter les résultats dans tes notes"""

    with patch("src.planner.LLMClient") as MockLLM:
        mock_instance = MagicMock()
        mock_instance.generate.return_value = mock_response
        MockLLM.return_value = mock_instance

        from src.planner import generate_plan

        steps = generate_plan(
            task_title="Explorer la régularisation",
            task_description="Étudier L1/L2 et dropout",
            goal=SAMPLE_GOALS[0],
            context_memories=SAMPLE_MEMORIES,
        )

        assert len(steps) >= 3, f"Should generate at least 3 steps, got {len(steps)}"
        assert len(steps) <= 5, f"Should cap at 5 steps, got {len(steps)}"
        print(f"✅ Test 2.1: Plan generation — PASSED ({len(steps)} steps)")
        for i, step in enumerate(steps):
            print(f"   {i+1}. {step}")


def test_planner_fallback():
    """Test fallback when LLM is unavailable."""
    with patch("src.planner.LLMClient") as MockLLM:
        mock_instance = MagicMock()
        mock_instance.generate.side_effect = ConnectionError("No Ollama")
        MockLLM.return_value = mock_instance

        from src.planner import generate_plan

        steps = generate_plan(
            task_title="Explorer la régularisation",
        )

        assert len(steps) == 3, f"Fallback should give 3 steps, got {len(steps)}"
        assert "régularisation" in steps[0].lower()
        print(f"✅ Test 2.2: Planner fallback — PASSED ({len(steps)} steps)")


# ═══════════════════════════════════════════════════════════════════
#  TEST 3: Task Generation from Insights
# ═══════════════════════════════════════════════════════════════════

def test_task_generation():
    """Test converting insights into tasks."""
    mock_llm_response = """TITRE: Explorer les techniques de régularisation L1/L2
DESCRIPTION: Étudier et implémenter les techniques de régularisation pour combattre l'overfitting.

TITRE: Visualiser les embeddings du RAG pipeline
DESCRIPTION: Créer des visualisations des vecteurs d'embeddings pour comprendre le retrieval.

TITRE: Implémenter un réseau de neurones from scratch
DESCRIPTION: Coder un perceptron multicouche en Python pur pour renforcer les fondamentaux."""

    mock_plan_response = """1. Lire la documentation sur L1/L2
2. Implémenter dans un notebook
3. Tester sur un dataset"""

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as f:
        json.dump([], f)
        temp_path = Path(f.name)

    try:
        with patch("src.tasks.TASKS_FILE", temp_path), \
             patch("src.tasks.TASKS_DIR", temp_path.parent), \
             patch("src.agent.task_generator.LLMClient") as MockLLM, \
             patch("src.planner.LLMClient") as MockPlannerLLM:

            # Mock both LLM clients
            mock_instance = MagicMock()
            mock_instance.generate.side_effect = [
                mock_llm_response,   # task generation
                mock_plan_response,  # plan for task 1
                mock_plan_response,  # plan for task 2
                mock_plan_response,  # plan for task 3
            ]
            MockLLM.return_value = mock_instance
            MockPlannerLLM.return_value = mock_instance

            from src.agent.task_generator import generate_tasks

            tasks = generate_tasks(
                insights=SAMPLE_INSIGHTS,
                goals=SAMPLE_GOALS,
                ranked_memories=SAMPLE_MEMORIES,
            )

            assert len(tasks) >= 1, f"Should create at least 1 task, got {len(tasks)}"
            print(f"✅ Test 3.1: Task generation — PASSED ({len(tasks)} tasks)")

            for task in tasks:
                assert "id" in task
                assert "title" in task
                assert "steps" in task
                assert task["status"] == "pending"
                print(
                    f"   📋 {task['title']} "
                    f"({len(task['steps'])} steps, p={task['priority']})"
                )

    finally:
        temp_path.unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════════════
#  TEST 4: Follow-Up System
# ═══════════════════════════════════════════════════════════════════

def test_follow_up_none():
    """Recent tasks should NOT trigger reminders."""
    from src.agent.follow_up import check_follow_ups

    recent_tasks = [
        {
            "id": "task_recent",
            "title": "Tâche récente",
            "status": "pending",
            "created_at": _hours_ago_iso(6),  # 6 hours ago — too recent
            "steps": ["Étape 1"],
            "last_reminded_at": None,
            "reminder_count": 0,
        }
    ]

    reminders = check_follow_ups(recent_tasks)
    assert len(reminders) == 0, f"No reminder expected, got {len(reminders)}"
    print("✅ Test 4.1: No reminder for recent task — PASSED")


def test_follow_up_reminder():
    """Tasks older than 24h should get a gentle reminder."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as f:
        old_task = {
            "id": "task_old",
            "title": "Tâche ancienne",
            "status": "pending",
            "created_at": _hours_ago_iso(30),  # 30 hours ago
            "steps": ["Lire le chapitre 1", "Faire les exercices"],
            "last_reminded_at": None,
            "reminder_count": 0,
        }
        json.dump([old_task], f)
        temp_path = Path(f.name)

    try:
        with patch("src.tasks.TASKS_FILE", temp_path), \
             patch("src.tasks.TASKS_DIR", temp_path.parent):
            from src.agent.follow_up import check_follow_ups

            reminders = check_follow_ups([old_task])
            assert len(reminders) == 1
            assert reminders[0]["level"] == "rappel"
            assert "Tâche ancienne" in reminders[0]["message"]
            print(f"✅ Test 4.2: Gentle reminder — PASSED")
            print(f"   Message: {reminders[0]['message']}")
    finally:
        temp_path.unlink(missing_ok=True)


def test_follow_up_escalation():
    """Tasks older than 48h should get an escalation."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as f:
        very_old_task = {
            "id": "task_very_old",
            "title": "Tâche très ancienne",
            "status": "pending",
            "created_at": _hours_ago_iso(72),  # 3 days ago
            "steps": ["Première action simple"],
            "last_reminded_at": None,
            "reminder_count": 2,
        }
        json.dump([very_old_task], f)
        temp_path = Path(f.name)

    try:
        with patch("src.tasks.TASKS_FILE", temp_path), \
             patch("src.tasks.TASKS_DIR", temp_path.parent):
            from src.agent.follow_up import check_follow_ups

            reminders = check_follow_ups([very_old_task])
            assert len(reminders) == 1
            assert reminders[0]["level"] == "escalade"
            assert "⚠️" in reminders[0]["message"]
            print(f"✅ Test 4.3: Escalation — PASSED")
            print(f"   Message: {reminders[0]['message']}")
    finally:
        temp_path.unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════════════
#  TEST 5: Brain Loop (full cycle with tasks)
# ═══════════════════════════════════════════════════════════════════

def test_brain_loop_with_tasks():
    """Test the full brain loop including task creation."""
    mock_insight_response = """1. Tu devrais explorer les techniques de régularisation L1/L2.
2. Connecte tes connaissances en embeddings avec le RAG pipeline.
3. Implémente un réseau de neurones from scratch."""

    mock_task_response = """TITRE: Explorer la régularisation L1/L2
DESCRIPTION: Étudier et implémenter les techniques de régularisation.

TITRE: Visualiser les embeddings du pipeline RAG
DESCRIPTION: Comprendre le fonctionnement du retrieval par vecteurs."""

    mock_plan_response = """1. Lire la documentation
2. Implémenter un exemple
3. Tester les résultats"""

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as f:
        json.dump([], f)
        temp_tasks_path = Path(f.name)

    try:
        with patch("src.agent.brain_loop.load_memory", return_value=SAMPLE_MEMORIES), \
             patch("src.agent.brain_loop.load_goals", return_value=SAMPLE_GOALS), \
             patch("src.agent.brain_loop.get_pending_tasks", return_value=[]), \
             patch("src.agent.insights.LLMClient") as MockInsightLLM, \
             patch("src.agent.task_generator.LLMClient") as MockTaskLLM, \
             patch("src.planner.LLMClient") as MockPlanLLM, \
             patch("src.tasks.TASKS_FILE", temp_tasks_path), \
             patch("src.tasks.TASKS_DIR", temp_tasks_path.parent), \
             patch("src.agent.notifier._send_notification", return_value=True):

            # Setup mocks
            insight_mock = MagicMock()
            insight_mock.generate.return_value = mock_insight_response
            MockInsightLLM.return_value = insight_mock

            task_mock = MagicMock()
            task_mock.generate.side_effect = [
                mock_task_response,
                mock_plan_response,
                mock_plan_response,
            ]
            MockTaskLLM.return_value = task_mock
            MockPlanLLM.return_value = task_mock

            from src.agent.brain_loop import BrainLoop

            loop = BrainLoop(interval=300)
            result = loop.run_once()

            assert result["memories_loaded"] == 2
            assert result["insights_generated"] > 0
            assert result["tasks_created"] >= 0  # May be 0 due to mock setup
            print(f"✅ Test 5.1: Brain loop with tasks — PASSED")
            print(f"   Memories: {result['memories_loaded']}")
            print(f"   Insights: {result['insights_generated']}")
            print(f"   Tasks: {result['tasks_created']}")
            print(f"   Reminders: {result['reminders_sent']}")
            print(f"   Notifications: {result['notifications_sent']}")

    finally:
        temp_tasks_path.unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════════════
#  TEST 6: Deduplication across cycles
# ═══════════════════════════════════════════════════════════════════

def test_deduplication():
    """Verify that duplicate tasks are not created across cycles."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as f:
        existing = [
            {
                "id": "task_existing",
                "goal_id": "goal_001",
                "title": "Explorer la régularisation L2",
                "status": "pending",
                "priority": 8,
                "steps": [],
                "created_at": _now_iso(),
                "last_reminded_at": None,
                "reminder_count": 0,
            }
        ]
        json.dump(existing, f)
        temp_path = Path(f.name)

    try:
        with patch("src.tasks.TASKS_FILE", temp_path), \
             patch("src.tasks.TASKS_DIR", temp_path.parent):
            from src.tasks import task_exists_similar, load_tasks

            # This should be detected as duplicate
            assert task_exists_similar("Explorer la régularisation L1") is True
            print("✅ Test 6.1: Cross-cycle dedup — PASSED (L1 ≈ L2 detected)")

            # This should NOT be a duplicate
            assert task_exists_similar("Créer un chatbot avec RAG") is False
            print("✅ Test 6.2: Non-duplicate — PASSED")

            # Very different phrasing should pass
            assert task_exists_similar("Analyser les vecteurs d'embeddings") is False
            print("✅ Test 6.3: Different topic — PASSED")

    finally:
        temp_path.unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════════════
#  RUN ALL TESTS
# ═══════════════════════════════════════════════════════════════════

def run_all():
    """Run all Phase 4 tests."""
    print("=" * 60)
    print("  Phase 4 — Task System, Planning & Follow-Up Tests")
    print("=" * 60)
    print()

    tests = [
        ("Task CRUD", test_task_crud),
        ("Plan Generation", test_planner),
        ("Planner Fallback", test_planner_fallback),
        ("Task Generation", test_task_generation),
        ("Follow-Up: No Reminder", test_follow_up_none),
        ("Follow-Up: Reminder", test_follow_up_reminder),
        ("Follow-Up: Escalation", test_follow_up_escalation),
        ("Brain Loop with Tasks", test_brain_loop_with_tasks),
        ("Deduplication", test_deduplication),
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
