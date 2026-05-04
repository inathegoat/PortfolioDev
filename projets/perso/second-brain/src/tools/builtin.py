"""
Second Brain — Built-in Tools (Phase 5)
==========================================
Concrete tool implementations for the AI to use.

Tools:
  1. CreateNoteTool    — Creates a markdown note in data/notes/
  2. CreateTaskTool    — Creates a new task via the task system
  3. UpdateTaskTool    — Updates task status (pending/in_progress/done)
  4. ExportDataTool    — Exports goals, tasks, or memories to JSON

All tools follow the BaseTool contract and declare their
permission level for the safety system.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from config.settings import NOTES_DIR, EXPORTS_DIR
from src.tools.base import (
    BaseTool,
    PERMISSION_READ_ONLY,
    PERMISSION_SAFE_WRITE,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
#  TOOL 1 — CREATE NOTE
# ═══════════════════════════════════════════════════════════════════

class CreateNoteTool(BaseTool):
    """
    Créer une note markdown dans data/notes/.

    L'IA utilise cet outil pour persister des idées,
    résumés, plans ou réflexions générées automatiquement.
    """

    name = "create_note"
    description = (
        "Créer un fichier de note markdown. "
        "Utile pour sauvegarder des idées, résumés ou plans d'action."
    )
    permission_level = PERMISSION_SAFE_WRITE

    def schema(self) -> dict:
        return {
            "title": {
                "type": "string",
                "required": True,
                "description": "Titre de la note (utilisé comme nom de fichier)",
            },
            "content": {
                "type": "string",
                "required": True,
                "description": "Contenu de la note en markdown",
            },
        }

    def execute(self, title: str = "", content: str = "", **kwargs) -> dict:
        """Créer un fichier .md dans data/notes/."""
        if not title or not content:
            return {
                "status": "error",
                "message": "Le titre et le contenu sont requis.",
            }

        # Sanitize filename
        safe_name = _sanitize_filename(title)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{safe_name}.md"

        filepath = NOTES_DIR / filename
        NOTES_DIR.mkdir(parents=True, exist_ok=True)

        # Build markdown content
        md_content = f"# {title}\n\n"
        md_content += f"*Créé le {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n"
        md_content += content

        filepath.write_text(md_content, encoding="utf-8")

        logger.info(f"Note created: {filepath}")
        return {
            "status": "success",
            "message": f"Note « {title} » créée avec succès.",
            "path": str(filepath),
            "filename": filename,
        }


# ═══════════════════════════════════════════════════════════════════
#  TOOL 2 — CREATE TASK
# ═══════════════════════════════════════════════════════════════════

class CreateTaskTool(BaseTool):
    """
    Créer une nouvelle tâche dans le système.

    Utilise le module src/tasks.py existant.
    """

    name = "create_task"
    description = (
        "Créer une nouvelle tâche liée à un objectif. "
        "Utile pour transformer une idée en action concrète."
    )
    permission_level = PERMISSION_SAFE_WRITE

    def schema(self) -> dict:
        return {
            "title": {
                "type": "string",
                "required": True,
                "description": "Titre court de la tâche (verbe d'action)",
            },
            "description": {
                "type": "string",
                "required": False,
                "description": "Description détaillée",
            },
            "goal_id": {
                "type": "string",
                "required": False,
                "description": "ID de l'objectif associé",
            },
            "priority": {
                "type": "int",
                "required": False,
                "description": "Priorité de 1 à 10",
            },
        }

    def execute(
        self,
        title: str = "",
        description: str = "",
        goal_id: str = "",
        priority: int = 5,
        **kwargs,
    ) -> dict:
        """Créer une tâche via le système existant."""
        if not title:
            return {
                "status": "error",
                "message": "Le titre de la tâche est requis.",
            }

        from src.tasks import add_task, task_exists_similar

        # Check duplicates
        if task_exists_similar(title):
            return {
                "status": "skipped",
                "message": f"Une tâche similaire existe déjà : « {title} »",
            }

        task = add_task(
            goal_id=goal_id,
            title=title,
            description=description,
            priority=priority,
        )

        return {
            "status": "success",
            "message": f"Tâche « {title} » créée (ID: {task['id']}).",
            "task_id": task["id"],
            "priority": task["priority"],
        }


# ═══════════════════════════════════════════════════════════════════
#  TOOL 3 — UPDATE TASK STATUS
# ═══════════════════════════════════════════════════════════════════

class UpdateTaskTool(BaseTool):
    """
    Mettre à jour le statut d'une tâche existante.
    """

    name = "update_task_status"
    description = (
        "Mettre à jour le statut d'une tâche existante. "
        "Statuts possibles : pending, in_progress, done."
    )
    permission_level = PERMISSION_SAFE_WRITE

    def schema(self) -> dict:
        return {
            "task_id": {
                "type": "string",
                "required": True,
                "description": "ID de la tâche à mettre à jour",
            },
            "status": {
                "type": "string",
                "required": True,
                "description": "Nouveau statut : 'pending', 'in_progress', ou 'done'",
            },
        }

    def execute(
        self,
        task_id: str = "",
        status: str = "",
        **kwargs,
    ) -> dict:
        """Mettre à jour le statut d'une tâche."""
        if not task_id or not status:
            return {
                "status": "error",
                "message": "task_id et status sont requis.",
            }

        from src.tasks import update_task_status, get_task

        # Verify task exists
        task = get_task(task_id)
        if not task:
            return {
                "status": "error",
                "message": f"Tâche non trouvée : {task_id}",
            }

        success = update_task_status(task_id, status)
        if success:
            return {
                "status": "success",
                "message": (
                    f"Tâche « {task['title']} » mise à jour → {status}."
                ),
            }
        else:
            return {
                "status": "error",
                "message": f"Échec de la mise à jour de la tâche {task_id}.",
            }


# ═══════════════════════════════════════════════════════════════════
#  TOOL 4 — EXPORT DATA
# ═══════════════════════════════════════════════════════════════════

class ExportDataTool(BaseTool):
    """
    Exporter des données du système en JSON.

    Types d'export : goals, tasks, memories, all.
    """

    name = "export_data"
    description = (
        "Exporter les données du système (objectifs, tâches, mémoires) "
        "en fichier JSON."
    )
    permission_level = PERMISSION_READ_ONLY

    def schema(self) -> dict:
        return {
            "data_type": {
                "type": "string",
                "required": True,
                "description": (
                    "Type de données à exporter : "
                    "'goals', 'tasks', 'memories', ou 'all'"
                ),
            },
        }

    def execute(self, data_type: str = "all", **kwargs) -> dict:
        """Exporter les données vers data/exports/."""
        valid_types = {"goals", "tasks", "memories", "all"}
        if data_type not in valid_types:
            return {
                "status": "error",
                "message": (
                    f"Type invalide : '{data_type}'. "
                    f"Types valides : {valid_types}"
                ),
            }

        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_data = {}

        if data_type in ("goals", "all"):
            from src.goals import load_goals
            export_data["goals"] = load_goals()

        if data_type in ("tasks", "all"):
            from src.tasks import load_tasks
            export_data["tasks"] = load_tasks()

        if data_type in ("memories", "all"):
            from src.memory.history import load_memory
            export_data["memories"] = load_memory()

        filename = f"export_{data_type}_{timestamp}.json"
        filepath = EXPORTS_DIR / filename

        filepath.write_text(
            json.dumps(export_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        total_items = sum(len(v) for v in export_data.values() if isinstance(v, list))

        return {
            "status": "success",
            "message": (
                f"Export « {data_type} » terminé : {total_items} éléments "
                f"→ {filename}"
            ),
            "path": str(filepath),
            "items_exported": total_items,
        }


# ═══════════════════════════════════════════════════════════════════
#  TOOL 5 — WEB SEARCH (Phase 9)
# ═══════════════════════════════════════════════════════════════════

class WebSearchTool(BaseTool):
    """
    Recherche sur internet via DuckDuckGo.
    
    Permet au système de pallier le manque d'informations locales
    par des informations récentes provenant d'internet.
    """

    name = "web_search"
    description = (
        "Rechercher des informations récentes sur internet. "
        "Utile pour trouver des faits actuels ou des actualités."
    )
    permission_level = PERMISSION_READ_ONLY

    def schema(self) -> dict:
        return {
            "query": {
                "type": "string",
                "required": True,
                "description": "La requête de recherche (mots-clés optimisés)",
            },
        }

    def execute(self, query: str = "", **kwargs) -> dict:
        """Effectuer la recherche DuckDuckGo."""
        if not query:
            return {
                "status": "error",
                "message": "La requête de recherche (query) est requise.",
            }

        try:
            from duckduckgo_search import DDGS
            
            logger.info(f"WebSearchTool searching for: '{query}'")
            
            with DDGS() as ddgs:
                # Get top 3 results
                results = list(ddgs.text(query, max_results=3))
            
            if not results:
                return {
                    "status": "success",
                    "message": f"Aucun résultat trouvé sur internet pour : {query}",
                    "results": []
                }
                
            formatted_results = "\\n".join([f"- {r['title']}: {r['body']}" for r in results])
            
            return {
                "status": "success",
                "message": f"Résultats de recherche pour '{query}'",
                "results": results,
                "formatted_text": formatted_results
            }
            
        except ImportError:
            return {
                "status": "error",
                "message": "duckduckgo-search n'est pas installé. Lancez 'pip install duckduckgo-search'.",
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Erreur lors de la recherche internet: {e}",
            }


# ═══════════════════════════════════════════════════════════════════
#  REGISTRATION
# ═══════════════════════════════════════════════════════════════════

def register_builtin_tools() -> None:
    """Enregistrer tous les outils intégrés dans le registre global."""
    from src.tools.registry import register_tool

    tools = [
        CreateNoteTool(),
        CreateTaskTool(),
        UpdateTaskTool(),
        ExportDataTool(),
        WebSearchTool(),
    ]

    for tool in tools:
        register_tool(tool)

    logger.info(f"Registered {len(tools)} built-in tools")


# ── Helpers ─────────────────────────────────────────────────────────

def _sanitize_filename(name: str) -> str:
    """Convertir un titre en nom de fichier sûr."""
    # Replace spaces and special chars
    safe = name.lower().strip()
    safe = safe.replace(" ", "_")
    # Keep only alphanumeric, underscores, hyphens
    safe = "".join(c for c in safe if c.isalnum() or c in ("_", "-"))
    # Limit length
    return safe[:60]
