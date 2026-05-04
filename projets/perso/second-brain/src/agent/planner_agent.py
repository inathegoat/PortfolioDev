from typing import Any, Dict
from src.agent.base_agent import BaseAgent

class PlannerAgent(BaseAgent):
    name = "Planner"
    
    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.info("Running Planner...")
        
        system_prompt = """You are a goal-oriented planner.

INPUT:
* User Goals
* Available Resources
* Constraints & Deadlines

OBJECTIVE:
Create a clear, realistic roadmap with milestones.

TASKS:
1. Break goals into phases
2. Assign timelines
3. Identify dependencies
4. Define deliverables

OUTPUT:
Milestones:
* M1: ...
* M2: ...
* M3: ...

Key Tasks Per Milestone:
* ...

Constraints:
* ...

Timeline:
* Start: ...
* End: ...

Be ambitious but practical.
"""
        
        user_prompt = f"""
{context['base_context']}

[ANALYSE STRATÉGIQUE]
{context.get('strategic_analysis', '')}

Créez le brouillon de la feuille de route (Draft Roadmap).
"""
        
        draft_roadmap = self.llm.generate(prompt=user_prompt, system_prompt=system_prompt)
        self.logger.info("Planner completed.")
        
        return {"draft_roadmap": draft_roadmap}
