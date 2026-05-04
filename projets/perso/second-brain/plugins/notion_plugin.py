"""plugins/notion_plugin.py — Notion API plugin.

Read/write Notion pages and databases.
Requires: NOTION_API_KEY and NOTION_DATABASE_ID in .env
"""
import logging
import os
from src.tools.base import BaseTool, PERMISSION_SAFE_WRITE, PERMISSION_READ_ONLY

logger = logging.getLogger(__name__)


def _notion_headers():
    token = os.getenv("NOTION_API_KEY", "")
    if not token:
        return None
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }


class NotionReadTool(BaseTool):
    name = "notion_read"
    description = "Lire les pages récentes d'une base de données Notion."
    permission_level = PERMISSION_READ_ONLY

    def schema(self) -> dict:
        return {
            "max_pages": {"type": "int", "required": False, "description": "Nombre max de pages", "default": 10},
        }

    def execute(self, max_pages: int = 10, **kwargs) -> dict:
        db_id = os.getenv("NOTION_DATABASE_ID", "")
        headers = _notion_headers()
        if not headers or not db_id:
            return {"status": "error", "message": "NOTION_API_KEY et NOTION_DATABASE_ID requis dans .env"}

        try:
            import requests
            r = requests.post(
                f"https://api.notion.com/v1/databases/{db_id}/query",
                headers=headers,
                json={"page_size": max_pages},
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            pages = []
            for p in data.get("results", []):
                title_prop = p.get("properties", {}).get("Name", {}).get("title", [{}])
                title = title_prop[0].get("plain_text", "") if title_prop else ""
                pages.append({
                    "id": p["id"],
                    "title": title or "(sans titre)",
                    "url": p.get("url", ""),
                    "last_edited": p.get("last_edited_time", ""),
                })
            return {"status": "success", "message": f"{len(pages)} page(s) Notion.", "pages": pages}
        except Exception as e:
            logger.error(f"Notion read failed: {e}")
            return {"status": "error", "message": str(e)}


class NotionWriteTool(BaseTool):
    name = "notion_write"
    description = "Créer une nouvelle page dans une base Notion."
    permission_level = PERMISSION_SAFE_WRITE

    def schema(self) -> dict:
        return {
            "title": {"type": "string", "required": True, "description": "Titre de la page"},
            "content": {"type": "string", "required": False, "description": "Contenu texte de la page"},
        }

    def execute(self, title: str = "", content: str = "", **kwargs) -> dict:
        db_id = os.getenv("NOTION_DATABASE_ID", "")
        headers = _notion_headers()
        if not headers or not db_id:
            return {"status": "error", "message": "NOTION_API_KEY et NOTION_DATABASE_ID requis dans .env"}
        if not title:
            return {"status": "error", "message": "Titre requis."}

        try:
            import requests
            payload = {
                "parent": {"database_id": db_id},
                "properties": {
                    "Name": {"title": [{"text": {"content": title}}]},
                },
            }
            if content:
                payload["children"] = [{
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": [{"type": "text", "text": {"content": content[:2000]}}]},
                }]

            r = requests.post(
                "https://api.notion.com/v1/pages",
                headers=headers,
                json=payload,
                timeout=15,
            )
            r.raise_for_status()
            page = r.json()
            return {"status": "success", "message": f"Page créée : {title}",
                    "url": page.get("url", ""), "id": page.get("id", "")}
        except Exception as e:
            logger.error(f"Notion write failed: {e}")
            return {"status": "error", "message": str(e)}
