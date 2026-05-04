"""
Second Brain — Task Prioritization Agent
========================================
Takes the roadmap and existing tasks, and creates or prioritizes 
the immediate next steps.
"""

import json
from typing import Any, Dict
from src.agent.base_agent import BaseAgent
from src.tasks import add_task

class PrioritizationAgent(BaseAgent):
    name = "Prioritizer"
    
    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Suggests the immediate next task based on the roadmap.
        """
        self.logger.info("Running Task Prioritization...")
        
        roadmap = context.get("roadmap", "")
        goals = context.get("goals", [])
        tasks = context.get("tasks", [])
        
        if not goals:
            return {"prioritization": "No goals."}
            
        goal_id = goals[0]["id"]
        
        prompt = f"""
        ROADMAP ACTUELLE :
        {roadmap}
        
        TÂCHES EXISTANTES :
        {[t['title'] for t in tasks]}
        
        Générez UNE SEULE tâche urgente et actionnable pour avancer sur cette roadmap.
        Répondez UNIQUEMENT avec un objet JSON valide, sans markdown, avec ce format strict :
        {{
            "title": "Titre court",
            "description": "Description de l'action",
            "priority": 9
        }}
        """
        
        response = self.llm.generate(prompt=prompt, system_prompt="Tu es un planificateur strict. Tu ne réponds qu'en JSON.")
        
        try:
            # Clean possible markdown block
            clean_json = response.strip()
            if clean_json.startswith("```json"):
                clean_json = clean_json[7:]
            if clean_json.startswith("```"):
                clean_json = clean_json[3:]
            if clean_json.endswith("```"):
                clean_json = clean_json[:-3]
                
            task_data = json.loads(clean_json.strip())
            
            # Check if task already exists roughly
            exists = any(t['title'].lower() == task_data['title'].lower() for t in tasks)
            if not exists:
                new_task = add_task(
                    goal_id=goal_id,
                    title=task_data["title"],
                    description=task_data.get("description", ""),
                    priority=task_data.get("priority", 8)
                )
                self.logger.info(f"Prioritizer created new task: {new_task['title']}")
                return {"new_task": new_task}
            else:
                self.logger.info("Task already exists, skipping.")
                return {"new_task": None, "msg": "Task already exists"}
                
        except Exception as e:
            self.logger.warning(f"Failed to parse task JSON: {e}")
            return {"error": "Failed to parse prioritization output."}
