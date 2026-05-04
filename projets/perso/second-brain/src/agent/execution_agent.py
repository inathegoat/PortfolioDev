from typing import Any, Dict
from src.agent.base_agent import BaseAgent

class ExecutionAgent(BaseAgent):
    name = "Execution Selector"
    
    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.info("Running Execution Selector...")
        
        system_prompt = """You are a decision agent.

INPUT:
* Optimized Roadmap
* Current tasks

OBJECTIVE:
Select what the user must do immediately.

TASKS:
1. Choose ONE main task
2. Choose 1–2 supporting tasks
3. Remove distractions

OUTPUT:
Main Task:
* ...

Secondary Tasks:
* ...

Avoid:
* ...

Reason:
* ...

Keep it extremely focused.
"""
        
        user_prompt = f"""
{context['base_context']}

[PLAN OPTIMISÉ (Optimized Roadmap)]
{context.get('optimized_roadmap', '')}

Sélectionnez l'action immédiate que l'utilisateur doit accomplir maintenant.
"""
        
        selected_action = self.llm.generate(prompt=user_prompt, system_prompt=system_prompt)
        self.logger.info("Execution Selector completed.")
        
        return {"selected_action": selected_action}
