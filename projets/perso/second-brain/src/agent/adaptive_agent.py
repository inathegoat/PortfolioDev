from typing import Any, Dict
from src.agent.base_agent import BaseAgent

class AdaptiveAgent(BaseAgent):
    name = "Adaptive Agent"
    
    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.info("Running Adaptive Agent...")
        
        system_prompt = """You are an adaptive agent.

INPUT:
* Previous roadmap
* Task progress
* New memory

OBJECTIVE:
Update strategy based on reality.

TASKS:
1. Detect what worked / failed
2. Identify friction
3. Adjust plan
4. Maintain momentum

OUTPUT:
Progress:
* Completed:
* Not completed:

Problems:
* ...

Adjustments:
* ...

Next Step:
* ...

Prioritize progress over perfection.
"""
        
        user_prompt = f"""
{context['base_context']}

[PROGRESSION DEPUIS LE DERNIER CYCLE]
Action précédente sélectionnée :
{context.get('task_progress', '')}

Sur la base de ces informations, évaluez ce qui a fonctionné, ce qui a échoué et ce qu'il faut ajuster.
"""
        
        adaptation_report = self.llm.generate(prompt=user_prompt, system_prompt=system_prompt)
        self.logger.info("Adaptive Agent completed.")
        
        return {"adaptation_report": adaptation_report}
