from typing import Any, Dict
from src.agent.base_agent import BaseAgent

class OptimizerAgent(BaseAgent):
    name = "Optimizer"
    
    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.info("Running Optimizer...")
        
        system_prompt = """You are an optimization agent.

INPUT:
* Strategic Analysis
* Initial Roadmap
* Critic Feedback

OBJECTIVE:
Produce the best possible execution plan.

TASKS:
1. Fix all critical issues
2. Simplify where possible
3. Ensure realism and execution focus
4. Keep only high-impact steps

OUTPUT:
Optimized Roadmap:
Phase 1:
* ...
Phase 2:
* ...
Phase 3:
* ...

Execution Rules:
* ...

Immediate Next Action:
* ...

The final plan must be:
* simple
* actionable
* realistic
"""
        
        user_prompt = f"""
{context['base_context']}

[BROUILLON DE FEUILLE DE ROUTE (Draft Roadmap)]
{context.get('draft_roadmap', '')}

[RETOURS DU CRITIQUE (Critic Feedback)]
{context.get('critic_feedback', '')}

Optimisez et corrigez le plan pour produire le plan d'exécution parfait.
"""
        
        optimized_roadmap = self.llm.generate(prompt=user_prompt, system_prompt=system_prompt)
        self.logger.info("Optimizer completed.")
        
        return {"optimized_roadmap": optimized_roadmap}
