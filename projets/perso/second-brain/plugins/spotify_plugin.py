import subprocess
import logging
from src.tools.base import BaseTool, PERMISSION_SAFE_WRITE

logger = logging.getLogger(__name__)

class SpotifyControlTool(BaseTool):
    """
    Outil pour contrôler Spotify sur Mac via AppleScript.
    """
    name = "spotify_control"
    description = "Contrôler l'application Spotify locale sur Mac. Commandes: 'play', 'pause', 'playpause', 'next', 'previous'."
    permission_level = PERMISSION_SAFE_WRITE

    def schema(self) -> dict:
        return {
            "command": {
                "type": "string",
                "required": True,
                "description": "La commande à envoyer (play, pause, playpause, next, previous).",
            }
        }

    def execute(self, command: str = "", **kwargs) -> dict:
        valid_commands = ["play", "pause", "playpause", "next", "previous"]
        if command not in valid_commands:
            # allow aliases
            if command == "suivante": command = "next"
            elif command == "précédente": command = "previous"
            else:
                return {"status": "error", "message": f"Commande invalide. Doit être parmi: {valid_commands}"}

        # Format AppleScript command
        if command == "next":
            applescript = 'tell application "Spotify" to next track'
        elif command == "previous":
            applescript = 'tell application "Spotify" to previous track'
        else:
            applescript = f'tell application "Spotify" to {command}'

        try:
            result = subprocess.run(["osascript", "-e", applescript], capture_output=True, text=True)
            if result.returncode != 0:
                # Peut arriver si Spotify n'est pas ouvert
                return {"status": "error", "message": f"Impossible de contrôler Spotify. Est-il ouvert ? ({result.stderr})"}
                
            return {
                "status": "success",
                "message": f"Commande '{command}' envoyée à Spotify avec succès.",
            }
        except Exception as e:
            logger.error(f"Spotify plugin error: {e}")
            return {"status": "error", "message": f"Erreur technique: {e}"}
