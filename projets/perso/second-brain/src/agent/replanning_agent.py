"""
Second Brain — Adaptive Replanning Agent
========================================
Analyzes recent user activity and closed tasks to adapt future behavior.
"""

from typing import Any, Dict
from src.agent.base_agent import BaseAgent
from src.tasks import load_tasks, save_tasks

class ReplanningAgent(BaseAgent):
    name = "Replanner"
    
    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Cleans up old tasks or reflects on done tasks.
        """
        self.logger.info("Running Adaptive Replanning...")
        
        # Example of adaptive logic: delete completed tasks that are older, or just log progress.
        tasks = load_tasks()
        done_tasks = [t for t in tasks if t.get("status") in ["done", "completed"]]
        
        if done_tasks:
            self.logger.info(f"User has completed {len(done_tasks)} tasks. Replanning future goals...")
            # For now, we just acknowledge the progress in the cycle.
            replanning_note = f"Acknowledged {len(done_tasks)} completed tasks."
        else:
            replanning_note = "No newly completed tasks."
            
        self.logger.info(replanning_note)
        
        return {
            "replanning_status": replanning_note
        }
