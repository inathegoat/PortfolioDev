"""
Tests for Phase 7 — Multi-Agent Architecture
================================================
Tests the Coordinator, Planner, Execution, and Critic agents.
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agent.coordinator import Coordinator
from src.agent.planner_agent import PlannerAgent
from src.agent.execution_agent import ExecutionAgent
from src.agent.critic_agent import CriticAgent


def test_planner_agent():
    with patch('src.agent.planner_agent.generate_insights') as mock_insights, \
         patch('src.agent.planner_agent.generate_tasks') as mock_tasks, \
         patch('src.agent.planner_agent.load_goals') as mock_goals:

        mock_insights.return_value = ["Insight 1"]
        mock_tasks.return_value = [{"title": "Task 1", "priority": 5}]
        mock_goals.return_value = []

        agent = PlannerAgent()
        result = agent.run({"important_memories": [{"fake": "memory"}]})

        assert len(result["insights"]) == 1
        assert len(result["new_tasks"]) == 1
        assert result["new_tasks"][0]["title"] == "Task 1"
        print("PlannerAgent — PASSED")


def test_executor_agent():
    with patch('src.agent.execution_agent.route_and_execute') as mock_route, \
         patch('src.agent.execution_agent.update_task_status') as mock_update:

        mock_route.return_value = {"status": "success", "message": "Done"}

        agent = ExecutionAgent()
        context = {"new_tasks": [{"id": "t1", "title": "Test"}]}
        result = agent.run(context)

        assert len(result["execution_results"]) == 1
        assert result["execution_results"][0]["success"] is True
        print("ExecutionAgent — PASSED")


def test_critic_agent():
    with patch('src.agent.critic_agent.update_task_status') as mock_update, \
         patch('src.agent.critic_agent.add_interaction') as mock_add:

        agent = CriticAgent()
        context = {
            "execution_results": [
                {"task": {"id": "t1", "title": "Test"}, "success": True, "action_result": {}},
                {"task": {"id": "t2", "title": "Fail"}, "success": False, "action_result": {}}
            ]
        }
        result = agent.run(context)

        assert len(result["feedback"]) == 2
        assert result["feedback"][0]["status"] == "approved"
        assert result["feedback"][1]["status"] == "rejected"
        print("CriticAgent — PASSED")


def test_coordinator():
    with patch.object(PlannerAgent, 'run') as m_plan, \
         patch.object(ExecutionAgent, 'run') as m_exec, \
         patch.object(CriticAgent, 'run') as m_crit:

        m_plan.return_value = {"plan": True}
        m_exec.return_value = {"exec": True}
        m_crit.return_value = {"crit": True}

        coord = Coordinator()
        res = coord.run_cycle()

        assert res.get("plan") is True
        assert res.get("exec") is True
        assert res.get("crit") is True
        print("Coordinator — PASSED")


if __name__ == "__main__":
    print("Running Multi-Agent Tests...\n" + "="*40)
    test_planner_agent()
    test_executor_agent()
    test_critic_agent()
    test_coordinator()
    print("="*40 + "\nAll tests passed!")
