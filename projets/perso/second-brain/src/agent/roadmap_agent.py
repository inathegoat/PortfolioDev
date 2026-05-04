"""
Second Brain — Roadmap Generation Agent
=======================================
Takes the strategic analysis and goals to generate long-term milestones
and high-level directions.
"""

from typing import Any, Dict
from src.agent.base_agent import BaseAgent

class RoadmapAgent(BaseAgent):
    name = "Roadmap Generator"
    
    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generates or updates the roadmap milestones based on strategy.
        """
        self.logger.info("Running Roadmap Generation...")
        
        strategy = context.get("strategy", "")
        goals = context.get("goals", [])
        
        if not goals:
            return {"roadmap": "No goals defined."}
            
        goal_summary = "\\n".join([f"- {g['title']}" for g in goals])
        
        prompt = f"""
        Basé sur l'analyse stratégique suivante :
        "{strategy}"
        
        Et les objectifs actuels :
        {goal_summary}
        
        Définissez une "Roadmap" (feuille de route) très courte (3 points maximum) 
        des grands jalons (milestones) à atteindre prochainement.
        """
        
        roadmap = self.llm.generate(prompt=prompt, system_prompt="Tu es l'Architecte Produit du Second Brain.")
        self.logger.info("Roadmap Generation completed.")
        
        return {
            "roadmap": roadmap
        }
