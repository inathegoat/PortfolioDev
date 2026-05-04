import subprocess
import logging
from src.tools.base import BaseTool, PERMISSION_SAFE_WRITE

logger = logging.getLogger(__name__)

class AppleRemindersTool(BaseTool):
    """
    Outil pour ajouter une tâche dans l'application Rappels (Reminders) d'Apple sur Mac.
    """
    name = "add_apple_reminder"
    description = "Ajouter un rappel ou une tâche dans l'application native 'Rappels' (Reminders) d'Apple."
    permission_level = PERMISSION_SAFE_WRITE

    def schema(self) -> dict:
        return {
            "task_name": {
                "type": "string",
                "required": True,
                "description": "Le nom ou le texte du rappel à ajouter.",
            }
        }

    def execute(self, task_name: str = "", **kwargs) -> dict:
        if not task_name:
            return {"status": "error", "message": "Le nom du rappel est requis."}

        applescript = f'''
        tell application "Reminders"
            try
                set myList to default list
            on error
                set myList to list "Reminders"
            end try
            make new reminder at end of myList with properties {{name:"{task_name}"}}
        end tell
        '''

        try:
            result = subprocess.run(["osascript", "-e", applescript], capture_output=True, text=True)
            if result.returncode != 0:
                return {"status": "error", "message": f"Erreur AppleScript: {result.stderr}"}
                
            return {
                "status": "success",
                "message": f"Rappel ajouté avec succès dans l'application Apple.",
                "details": f"Tâche: {task_name}"
            }
        except Exception as e:
            logger.error(f"Reminders plugin error: {e}")
            return {"status": "error", "message": f"Erreur technique: {e}"}
