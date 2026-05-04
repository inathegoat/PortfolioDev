"""
Second Brain — Tool Registry & Executor (Phase 5+6)
======================================================
Central registry for all tools with integrated safety.

Responsibilities:
  - Tool registration and discovery
  - Argument validation (JSON schema)
  - Permission enforcement (read_only / safe_write / restricted)
  - Path sandboxing (restrict file operations)
  - Execution with error handling
  - Audit logging (all executions to JSON)

Every tool execution goes through:
  register → validate args → check permission → sandbox → execute → audit
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable

from config.settings import (
    TOOLS_LOG_FILE, ALLOWED_TOOL_DIRS, LOGS_DIR,
    PROJECT_ROOT,
)
from src.tools.base import (
    BaseTool,
    PERMISSION_RESTRICTED,
    VALID_PERMISSIONS,
)

logger = logging.getLogger(__name__)


# ── Global Registry ─────────────────────────────────────────────────

_registry: dict[str, BaseTool] = {}


# ── Registration ────────────────────────────────────────────────────

def register_tool(tool: BaseTool) -> None:
    """
    Enregistrer un outil dans le registre global.

    Args:
        tool: Instance de BaseTool à enregistrer.

    Raises:
        ValueError: Si le nom est vide ou déjà pris.
    """
    if not tool.name:
        raise ValueError("Tool must have a non-empty 'name'")

    if tool.permission_level not in VALID_PERMISSIONS:
        raise ValueError(
            f"Invalid permission level '{tool.permission_level}' "
            f"for tool '{tool.name}'. Must be one of {VALID_PERMISSIONS}"
        )

    if tool.name in _registry:
        logger.warning(f"Tool '{tool.name}' already registered — overwriting")

    _registry[tool.name] = tool
    logger.info(
        f"Registered tool: {tool.name} "
        f"(permission={tool.permission_level})"
    )


def get_tool(name: str) -> Optional[BaseTool]:
    """Récupérer un outil par son nom."""
    return _registry.get(name)


def list_tools() -> list[dict]:
    """Lister tous les outils enregistrés."""
    return [tool.to_dict() for tool in _registry.values()]


def get_tool_names() -> list[str]:
    """Retourner les noms de tous les outils enregistrés."""
    return list(_registry.keys())


def clear_registry() -> None:
    """Vider le registre (utile pour les tests)."""
    _registry.clear()


# ── Execution ───────────────────────────────────────────────────────

def execute_tool(
    tool_name: str,
    args: dict,
    confirm_fn: Optional[Callable[[str], bool]] = None,
) -> dict:
    """
    Exécuter un outil de manière sécurisée.

    Pipeline complet :
    1. Vérifier que l'outil existe (allowlist)
    2. Valider les arguments (schema)
    3. Vérifier les permissions
    4. Sandbox les chemins de fichiers
    5. Exécuter
    6. Journaliser dans l'audit log

    Args:
        tool_name:  Nom de l'outil à exécuter.
        args:       Dict d'arguments pour l'outil.
        confirm_fn: Fonction de confirmation pour les outils restreints.
                    Reçoit un message, retourne True/False.
                    Si None, les outils restreints sont bloqués.

    Returns:
        Dict avec le résultat (status, message, ...).
    """
    # ── Step 1: Allowlist check ─────────────────────────────────────
    tool = _registry.get(tool_name)
    if tool is None:
        result = {
            "status": "error",
            "message": f"Outil inconnu : '{tool_name}'. "
                       f"Outils disponibles : {get_tool_names()}",
        }
        _audit_log(tool_name, args, result, "unknown")
        return result

    # ── Step 2: Validate arguments ──────────────────────────────────
    valid, error_msg = tool.validate_args(args)
    if not valid:
        result = {
            "status": "error",
            "message": f"Arguments invalides pour '{tool_name}' : {error_msg}",
        }
        _audit_log(tool_name, args, result, tool.permission_level)
        return result

    # ── Step 3: Permission check ────────────────────────────────────
    if tool.permission_level == PERMISSION_RESTRICTED:
        if confirm_fn is None:
            result = {
                "status": "blocked",
                "message": (
                    f"L'outil '{tool_name}' nécessite une confirmation. "
                    f"Aucune fonction de confirmation fournie."
                ),
            }
            _audit_log(tool_name, args, result, tool.permission_level)
            return result

        # Ask user for confirmation
        confirm_msg = (
            f"⚠️  L'outil '{tool_name}' est restreint.\n"
            f"   Action : {tool.description}\n"
            f"   Arguments : {json.dumps(args, ensure_ascii=False)}\n"
            f"   Confirmer l'exécution ?"
        )
        if not confirm_fn(confirm_msg):
            result = {
                "status": "cancelled",
                "message": "Action annulée par l'utilisateur.",
            }
            _audit_log(tool_name, args, result, tool.permission_level)
            return result

    # ── Step 4: Path sandboxing ─────────────────────────────────────
    sandbox_ok, sandbox_msg = _check_path_sandbox(args)
    if not sandbox_ok:
        result = {
            "status": "error",
            "message": f"Violation de sécurité : {sandbox_msg}",
        }
        _audit_log(tool_name, args, result, tool.permission_level)
        return result

    # ── Step 5: Execute ─────────────────────────────────────────────
    try:
        logger.info(f"Executing tool: {tool_name} with args={args}")
        result = tool.execute(**args)

        # Ensure result has required fields
        if "status" not in result:
            result["status"] = "success"

        logger.info(
            f"Tool '{tool_name}' → {result.get('status')}: "
            f"{result.get('message', '')[:80]}"
        )

    except Exception as e:
        result = {
            "status": "error",
            "message": f"Erreur d'exécution de '{tool_name}' : {str(e)}",
        }
        logger.error(f"Tool '{tool_name}' failed: {e}", exc_info=True)

    # ── Step 6: Audit log ───────────────────────────────────────────
    _audit_log(tool_name, args, result, tool.permission_level)

    return result


# ── Path Sandboxing (Phase 6) ──────────────────────────────────────

def _check_path_sandbox(args: dict) -> tuple[bool, str]:
    """
    Vérifier que tous les chemins dans les arguments
    sont dans les répertoires autorisés.

    Inspecte les valeurs d'args contenant "path", "file",
    ou "directory" dans la clé.

    Returns:
        (True, "") si tout est OK,
        (False, "raison") si une violation est détectée.
    """
    path_keys = [
        k for k in args.keys()
        if any(word in k.lower() for word in ("path", "file", "dir"))
    ]

    for key in path_keys:
        value = args[key]
        if not isinstance(value, str):
            continue

        target_path = Path(value).resolve()

        # Check if the path is within any allowed directory
        is_allowed = any(
            _is_subpath(target_path, allowed_dir)
            for allowed_dir in ALLOWED_TOOL_DIRS
        )

        if not is_allowed:
            return (
                False,
                f"Le chemin '{value}' est en dehors des répertoires autorisés. "
                f"Répertoires permis : {[str(d) for d in ALLOWED_TOOL_DIRS]}",
            )

    return True, ""


def _is_subpath(child: Path, parent: Path) -> bool:
    """Check if child is a subpath of parent."""
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def is_path_allowed(path: str | Path) -> bool:
    """
    API publique pour vérifier si un chemin est autorisé.

    Utilisé par les outils avant d'écrire des fichiers.
    """
    target = Path(path).resolve()
    return any(
        _is_subpath(target, allowed)
        for allowed in ALLOWED_TOOL_DIRS
    )


# ── Audit Log (Phase 6) ────────────────────────────────────────────

def _audit_log(
    tool_name: str,
    args: dict,
    result: dict,
    permission_level: str,
) -> None:
    """
    Journaliser une exécution d'outil dans le fichier d'audit.

    Chaque entrée contient : timestamp, outil, args, résultat, permission.
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": tool_name,
        "args": _sanitize_for_log(args),
        "result_status": result.get("status", "unknown"),
        "result_message": result.get("message", "")[:200],
        "permission_level": permission_level,
    }

    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)

        # Load existing log
        if TOOLS_LOG_FILE.exists():
            content = TOOLS_LOG_FILE.read_text(encoding="utf-8")
            log_data = json.loads(content) if content.strip() else []
        else:
            log_data = []

        if not isinstance(log_data, list):
            log_data = []

        log_data.append(entry)

        # Keep last 500 entries to prevent unbounded growth
        if len(log_data) > 500:
            log_data = log_data[-500:]

        TOOLS_LOG_FILE.write_text(
            json.dumps(log_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    except Exception as e:
        logger.error(f"Failed to write audit log: {e}")


def load_audit_log() -> list[dict]:
    """Charger l'historique d'exécution des outils."""
    try:
        if not TOOLS_LOG_FILE.exists():
            return []
        content = TOOLS_LOG_FILE.read_text(encoding="utf-8")
        data = json.loads(content) if content.strip() else []
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _sanitize_for_log(args: dict) -> dict:
    """Remove or truncate large values before logging."""
    sanitized = {}
    for k, v in args.items():
        if isinstance(v, str) and len(v) > 300:
            sanitized[k] = v[:300] + "... (tronqué)"
        else:
            sanitized[k] = v
    return sanitized


# ── CLI Confirmation Helper ─────────────────────────────────────────

def cli_confirm(message: str) -> bool:
    """
    Demander confirmation à l'utilisateur via le terminal.

    Args:
        message: Message à afficher.

    Returns:
        True si l'utilisateur confirme (o/y), False sinon.
    """
    print(f"\n{message}")
    response = input("  [o/N] > ").strip().lower()
    return response in ("o", "oui", "y", "yes")
