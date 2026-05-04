"""plugins/filesystem_plugin.py — Filesystem plugin with sandbox.

Safe read/write operations restricted to allowed directories.
All destructive operations require user confirmation.
"""
import logging
import shutil
from pathlib import Path
from src.tools.base import BaseTool, PERMISSION_READ_ONLY, PERMISSION_SAFE_WRITE, PERMISSION_RESTRICTED

logger = logging.getLogger(__name__)

# Sandbox: operations limited to these directories
SANDBOX_DIRS = [
    Path("data"),
    Path("data/raw"),
    Path("data/notes"),
    Path("data/exports"),
]

for d in SANDBOX_DIRS:
    d.mkdir(parents=True, exist_ok=True)


def _resolve_safe(path: str) -> Path:
    """Resolve a path within the sandbox. Returns None if outside."""
    p = Path(path).resolve()
    for sandbox in SANDBOX_DIRS:
        sb = sandbox.resolve()
        try:
            p.relative_to(sb)
            return p
        except ValueError:
            continue
    return None


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Lire le contenu d'un fichier dans data/"
    permission_level = PERMISSION_READ_ONLY

    def schema(self) -> dict:
        return {
            "path": {"type": "string", "required": True, "description": "Chemin relatif (ex: notes/recette.txt)"},
            "max_chars": {"type": "int", "required": False, "description": "Limite de caractères", "default": 5000},
        }

    def execute(self, path: str = "", max_chars: int = 5000, **kwargs) -> dict:
        safe = _resolve_safe(path)
        if not safe:
            return {"status": "error", "message": f"Accès refusé : '{path}' hors sandbox."}
        if not safe.exists():
            return {"status": "error", "message": f"Fichier introuvable : {path}"}
        try:
            content = safe.read_text(encoding="utf-8")[:max_chars]
            return {"status": "success", "message": f"Fichier lu : {path}", "content": content,
                    "size": safe.stat().st_size}
        except Exception as e:
            return {"status": "error", "message": str(e)}


class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Écrire/créer un fichier dans data/ (nécessite confirmation)."
    permission_level = PERMISSION_SAFE_WRITE

    def schema(self) -> dict:
        return {
            "path": {"type": "string", "required": True, "description": "Chemin relatif (ex: notes/idée.txt)"},
            "content": {"type": "string", "required": True, "description": "Contenu à écrire"},
        }

    def execute(self, path: str = "", content: str = "", **kwargs) -> dict:
        safe = _resolve_safe(path)
        if not safe:
            return {"status": "error", "message": f"Accès refusé : '{path}' hors sandbox."}
        try:
            safe.parent.mkdir(parents=True, exist_ok=True)
            safe.write_text(content, encoding="utf-8")
            return {"status": "success", "message": f"Fichier écrit : {path}", "size": len(content)}
        except Exception as e:
            return {"status": "error", "message": str(e)}


class ListFilesTool(BaseTool):
    name = "list_files"
    description = "Lister les fichiers dans un dossier de data/"
    permission_level = PERMISSION_READ_ONLY

    def schema(self) -> dict:
        return {
            "directory": {"type": "string", "required": False, "description": "Dossier (ex: notes)", "default": ""},
        }

    def execute(self, directory: str = "", **kwargs) -> dict:
        base = Path("data") / directory if directory else Path("data")
        safe = _resolve_safe(str(base))
        if not safe:
            return {"status": "error", "message": f"Accès refusé : '{directory}'"}
        if not safe.exists():
            return {"status": "success", "message": "Dossier vide.", "files": []}
        files = []
        for f in sorted(safe.iterdir()):
            files.append({
                "name": f.name,
                "type": "dossier" if f.is_dir() else "fichier",
                "size": f.stat().st_size if f.is_file() else 0,
            })
        return {"status": "success", "message": f"{len(files)} élément(s) dans {directory or 'data/'}.",
                "files": files[:50]}


class DeleteFileTool(BaseTool):
    name = "delete_file"
    description = "Supprimer un fichier dans data/ (⚠️ nécessite double confirmation)."
    permission_level = PERMISSION_RESTRICTED

    def schema(self) -> dict:
        return {
            "path": {"type": "string", "required": True, "description": "Chemin relatif du fichier à supprimer"},
        }

    def execute(self, path: str = "", **kwargs) -> dict:
        safe = _resolve_safe(path)
        if not safe:
            return {"status": "error", "message": f"Accès refusé : '{path}' hors sandbox."}
        if not safe.exists():
            return {"status": "error", "message": f"Fichier introuvable : {path}"}
        try:
            if safe.is_file():
                safe.unlink()
            else:
                shutil.rmtree(safe)
            return {"status": "success", "message": f"Supprimé : {path}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
