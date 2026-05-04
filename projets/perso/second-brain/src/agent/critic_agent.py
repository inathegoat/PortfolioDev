from typing import Any, Dict
from src.agent.base_agent import BaseAgent

class CriticAgent(BaseAgent):
    name = "Critic"
    
    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.info("Running Critic...")
        
        system_prompt = """You are a critic and risk assessor.

INPUT:
* Draft Roadmap
* Strategic Analysis
* Context

OBJECTIVE:
Find all risks, issues, weaknesses, and things that could fail.

TASKS:
1. Identify unrealistic steps
2. Find missing dependencies
3. Detect scope creep
4. Flag ambiguity
5. Point out risks (time, technical, resource)

OUTPUT:
Critical Issues:
* ...

Risks:
* ...

Warnings:
* ...

Suggestions:
* ...

Be sharp but constructive.
"""
        
        user_prompt = f"""
{context['base_context']}

[ANALYSE STRATÉGIQUE]
{context.get('strategic_analysis', '')}

[BROUILLON DE FEUILLE DE ROUTE (Draft Roadmap)]
{context.get('draft_roadmap', '')}

Critiquez ce plan et trouvez les failles.
"""
        
        critic_feedback = self.llm.generate(prompt=user_prompt, system_prompt=system_prompt)
        self.logger.info("Critic completed.")
        
        return {"critic_feedback": critic_feedback}
