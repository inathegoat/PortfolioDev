from typing import Any, Dict
from src.agent.base_agent import BaseAgent

class StrategicAgent(BaseAgent):
    name = "Strategic Analyst"
    
    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.info("Running Strategic Analyst...")
        
        system_prompt = """You are a strategic analysis agent.

INPUT:
* User Goals
* Available Resources
* Context

OBJECTIVE:
Analyze the situation and identify key factors.

TASKS:
1. Identify opportunities
2. Identify threats
3. Assess current situation
4. Determine best approach

OUTPUT:
Opportunities:
* ...

Threats:
* ...

Assessment:
* ...

Strategic Insights:
* ...

Be sharp, insightful, and forward-looking.
"""
        
        user_prompt = f"""
{context['base_context']}

[ADAPTATION RÉCENTE]
{context.get('adaptation_report', 'Aucune adaptation précédente.')}

Réalisez l'analyse stratégique.
"""
        
        strategic_analysis = self.llm.generate(prompt=user_prompt, system_prompt=system_prompt)
        self.logger.info("Strategic Analyst completed.")
        
        return {"strategic_analysis": strategic_analysis}
