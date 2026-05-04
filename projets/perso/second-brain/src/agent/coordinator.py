"""
Second Brain — Multi-Agent Coordinator
======================================
Manages the message passing and loop between the 6 specialized agents.
"""

import logging
from typing import Any, Dict

from src.ai.llm_client import LLMClient
from src.goals import load_goals
from src.tasks import load_tasks
from src.memory.history import load_memory

from src.agent.adaptive_agent import AdaptiveAgent
from src.agent.strategic_agent import StrategicAgent
from src.agent.planner_agent import PlannerAgent
from src.agent.critic_agent import CriticAgent
from src.agent.optimizer_agent import OptimizerAgent
from src.agent.execution_agent import ExecutionAgent

logger = logging.getLogger(__name__)

class Coordinator:
    """Orchestrates the 6-agent strategic workflow."""
    
    def __init__(self):
        self.llm = LLMClient()
        self.adaptive_agent = AdaptiveAgent(self.llm)
        self.strategic_agent = StrategicAgent(self.llm)
        self.planner_agent = PlannerAgent(self.llm)
        self.critic_agent = CriticAgent(self.llm)
        self.optimizer_agent = OptimizerAgent(self.llm)
        self.execution_agent = ExecutionAgent(self.llm)
        
        # State retained across cycles
        self.previous_plan = ""
        self.task_progress = ""
        
    def _build_base_context(self) -> str:
        """Builds the mandatory context string for all agents."""
        goals = load_goals()
        tasks = load_tasks()
        memories = load_memory()
        
        goal_summary = "\\n".join([f"- {g['title']} (Priority: {g.get('priority', 5)})" for g in goals]) if goals else "Aucun objectif."
        task_summary = "\\n".join([f"- [{t.get('status', 'todo')}] {t['title']} (Priority: {t.get('priority', 3)})" for t in tasks]) if tasks else "Aucune tâche."
        memory_summary = "\\n".join([f"- Q: {m.get('question', '')}" for m in memories[-3:]]) if memories else "Aucune mémoire récente."
        prev_plan_summary = self.previous_plan if self.previous_plan else "Aucun plan précédent."
        
        return f"""
[CONTEXTE GLOBAL OBLIGATOIRE]
OBJECTIFS (Priorité) :
{goal_summary}

TÂCHES ACTUELLES :
{task_summary}

ÉVÉNEMENTS RÉCENTS (Mémoire) :
{memory_summary}

PLAN PRÉCÉDENT :
{prev_plan_summary}
"""

    def run_cycle(self) -> Dict[str, Any]:
        """
        Runs one complete 6-agent loop.
        """
        logger.info("=== Starting 6-Agent Strategic Loop ===")
        context: Dict[str, Any] = {}
        
        base_context = self._build_base_context()
        context["base_context"] = base_context
        context["previous_plan"] = self.previous_plan
        context["task_progress"] = self.task_progress
        
        # 1. Adaptive Agent (Evaluates what happened since last loop)
        if self.previous_plan:
            adapt_out = self.adaptive_agent.run(context)
            context.update(adapt_out)
        else:
            context["adaptation_report"] = "Initialisation du système. Pas de plan précédent à évaluer."
        
        # 2. Strategic Analyst
        strat_out = self.strategic_agent.run(context)
        context.update(strat_out)
        
        # 3. Planner
        plan_out = self.planner_agent.run(context)
        context.update(plan_out)
        
        # 4. Critic
        critic_out = self.critic_agent.run(context)
        context.update(critic_out)
        
        # 5. Optimizer
        opt_out = self.optimizer_agent.run(context)
        context.update(opt_out)
        
        # 6. Execution Selector
        exec_out = self.execution_agent.run(context)
        context.update(exec_out)
        
        # Save state for next cycle
        self.previous_plan = context.get("optimized_roadmap", "")
        
        # Update task_progress for next loop (naively for now, user acts in between)
        self.task_progress = context.get("selected_action", "")
        
        logger.info("=== Completed 6-Agent Strategic Loop ===")
        return context

    def start(self, interval: int = 3600):
        import time
        logger.info(f"Starting Multi-Agent Coordinator loop (interval: {interval}s)")
        try:
            while True:
                self.run_cycle()
                logger.info(f"Sleeping for {interval} seconds...")
                time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("Coordinator loop stopped by user.")
