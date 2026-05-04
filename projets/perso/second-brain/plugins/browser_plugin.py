"""plugins/browser_plugin.py — Browser plugin.

- Open URLs in default browser
- Simple web scraping (read text content)
"""
import logging
import webbrowser
from urllib.parse import urlparse
from src.tools.base import BaseTool, PERMISSION_READ_ONLY

logger = logging.getLogger(__name__)


class OpenURLTool(BaseTool):
    name = "open_url"
    description = "Ouvrir une URL dans le navigateur par défaut."
    permission_level = PERMISSION_READ_ONLY

    def schema(self) -> dict:
        return {
            "url": {"type": "string", "required": True, "description": "URL complète (https://...) à ouvrir"},
        }

    def execute(self, url: str = "", **kwargs) -> dict:
        if not url:
            return {"status": "error", "message": "URL requise."}
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return {"status": "error", "message": "Seules les URLs http/https sont autorisées."}
        try:
            webbrowser.open(url)
            return {"status": "success", "message": f"URL ouverte : {url}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}


class WebScrapeTool(BaseTool):
    name = "web_scrape"
    description = "Extraire le contenu texte d'une page web."
    permission_level = PERMISSION_READ_ONLY

    def schema(self) -> dict:
        return {
            "url": {"type": "string", "required": True, "description": "URL à scraper"},
            "max_chars": {"type": "int", "required": False, "description": "Limite caractères", "default": 2000},
        }

    def execute(self, url: str = "", max_chars: int = 2000, **kwargs) -> dict:
        if not url:
            return {"status": "error", "message": "URL requise."}
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return {"status": "error", "message": "Seules les URLs http/https sont autorisées."}
        try:
            import requests
            headers = {"User-Agent": "SecondBrain/2.0"}
            r = requests.get(url, headers=headers, timeout=10)
            r.raise_for_status()

            # Simple text extraction
            import re
            text = re.sub(r"<[^>]+>", " ", r.text)
            text = re.sub(r"\s+", " ", text).strip()
            text = text[:max_chars]

            return {"status": "success", "message": f"Contenu extrait ({len(text)} car.)",
                    "content": text, "url": url}
        except Exception as e:
            return {"status": "error", "message": str(e)}


class SearchWebTool(BaseTool):
    name = "search_web"
    description = "Rechercher sur le web via DuckDuckGo."
    permission_level = PERMISSION_READ_ONLY

    def schema(self) -> dict:
        return {
            "query": {"type": "string", "required": True, "description": "Termes de recherche"},
            "max_results": {"type": "int", "required": False, "description": "Nombre de résultats", "default": 5},
        }

    def execute(self, query: str = "", max_results: int = 5, **kwargs) -> dict:
        if not query:
            return {"status": "error", "message": "Requête vide."}
        try:
            from ddgs import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
            items = [{"title": r.get("title", ""), "url": r.get("href", ""),
                       "snippet": r.get("body", "")} for r in results]
            return {"status": "success", "message": f"{len(items)} résultat(s) pour '{query}'.",
                    "results": items}
        except ImportError:
            return {"status": "error", "message": "Package manquant : pip install ddgs"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
