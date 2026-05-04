"""src/ai/tools.py — Registry d'outils + tool-use parser."""
import json
import logging
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Tuple

logger = logging.getLogger(__name__)

# ── Registry ─────────────────────────────────────────────────────────

TOOL_REGISTRY: Dict[str, Callable] = {}


def register(name: str):
    def decorator(fn):
        TOOL_REGISTRY[name] = fn
        return fn
    return decorator


# ── Outils ───────────────────────────────────────────────────────────

@register("get_date_time")
def get_date_time(**_) -> Dict[str, str]:
    now = datetime.now()
    return {"date": now.strftime("%d/%m/%Y"), "time": now.strftime("%H:%M"), "iso": now.isoformat()}


@register("web_search")
def web_search(query: str = "", max_results: int = 5, **_) -> Dict[str, Any]:
    if not query.strip():
        return {"status": "error", "results": [], "error": "Query vide"}

    try:
        from ddgs import DDGS

        with DDGS() as ddgs:
            raw_results = list(ddgs.text(query, max_results=max_results))

        results = []
        for r in raw_results:
            results.append({
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", "")
            })

        if not results:
            return {
                "status": "empty",
                "results": [],
                "message": f"Aucun résultat trouvé pour: {query}"
            }

        return {
            "status": "ok",
            "query": query,
            "count": len(results),
            "results": results
        }

    except ImportError:
        logger.exception("DDGS import failed")
        return {
            "status": "error",
            "results": [],
            "error": "Package manquant: pip install ddgs"
        }
    except Exception as e:
        logger.exception("web_search failed for query=%r", query)
        return {
            "status": "error",
            "results": [],
            "error": str(e)
        }


@register("calculator")
def calculator(expression: str = "", **_) -> Dict[str, Any]:
    try:
        import ast
        import operator as op

        _SAFE_OPS = {
            ast.Add: op.add, ast.Sub: op.sub,
            ast.Mult: op.mul, ast.Div: op.truediv,
            ast.USub: op.neg, ast.UAdd: op.pos,
            ast.Pow: op.pow,
        }

        def _safe_eval(node):
            if isinstance(node, ast.Expression):
                return _safe_eval(node.body)
            if isinstance(node, ast.BinOp):
                left = _safe_eval(node.left)
                right = _safe_eval(node.right)
                if isinstance(node.op, ast.Div) and right == 0:
                    raise ZeroDivisionError("division by zero")
                return _SAFE_OPS[type(node.op)](left, right)
            if isinstance(node, ast.UnaryOp):
                return _SAFE_OPS[type(node.op)](_safe_eval(node.operand))
            if isinstance(node, ast.Constant):
                return node.value
            raise ValueError(f"unsupported expression: {type(node).__name__}")

        tree = ast.parse(expression.strip(), mode="eval")
        result = _safe_eval(tree)
        return {"expression": expression, "result": result}
    except Exception as e:
        return {"error": str(e)}


@register("list_documents")
def list_documents(**_) -> Dict[str, Any]:
    try:
        from src.memory.vector_store import VectorStore
        vs = VectorStore()
        return {"sources": vs.list_sources(), "total_chunks": vs.count()}
    except Exception as e:
        return {"sources": [], "error": str(e)}


@register("create_task")
def create_task(title: str = "", description: str = "", objective: str = "", **_) -> Dict[str, Any]:
    import sqlite3
    from config.settings import TASKS_DB
    try:
        with sqlite3.connect(TASKS_DB) as conn:
            cur = conn.execute(
                "INSERT INTO tasks (title, description, objective, priority, created_at) VALUES (?,?,?,?,?)",
                (title, description, objective, 3, datetime.now().isoformat()),
            )
            conn.commit()
        return {"status": "created", "id": cur.lastrowid, "title": title}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ── Schéma pour le system prompt ─────────────────────────────────────

def get_tools_schema() -> str:
    descriptions = {
        "get_date_time":  "Obtenir la date et heure actuelles",
        "web_search":     "Rechercher sur le web. Params: query (str), max_results (int)",
        "calculator":     "Calculer une expression. Params: expression (str)",
        "list_documents": "Lister les documents indexés",
        "create_task":    "Créer une tâche. Params: title, description, objective (str)",
    }
    example = json.dumps({"name": "web_search", "params": {"query": "inflation France 2025"}})
    lines = [
        "Tu peux utiliser ces outils via JSON entre balises <tool>...</tool> :",
        "",
    ]
    for name, desc in descriptions.items():
        lines.append(f"  - {name}: {desc}")
    lines += [
        "",
        "Exemple : <tool>" + example + "</tool>",
        "",
        "N'utilise un outil que si c'est vraiment nécessaire.",
    ]
    return "\n".join(lines)


# ── Parser tool-use ───────────────────────────────────────────────────

def parse_and_execute_tools(response_text: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Parse <tool>...</tool> tags in LLM output and execute registered tools.
    Returns (cleaned_response, tool_results_list).

    Args:
        response_text: Raw LLM output possibly containing <tool>...</tool> blocks.

    Returns:
        Tuple of (text with tool results injected, list of tool execution results).
    """
    tool_pattern = re.compile(r"<tool>(.*?)</tool>", re.DOTALL)
    matches = tool_pattern.findall(response_text)
    if not matches:
        return response_text.strip(), []

    clean = response_text
    tool_results: List[Dict[str, Any]] = []

    for raw in matches:
        clean = clean.replace(f"<tool>{raw}</tool>", "").strip()
        try:
            call = json.loads(raw.strip())
            name = call.get("name", "")
            params = call.get("params", {})
            if name in TOOL_REGISTRY:
                result = TOOL_REGISTRY[name](**params)
                tool_results.append({"tool": name, "params": params, "result": result})
                result_text = json.dumps(result, ensure_ascii=False)
                clean += f"\n\n[Résultat {name}]: {result_text}"
            else:
                logger.warning(f"Tool not found: {name}")
        except json.JSONDecodeError as e:
            logger.debug(f"Tool parse error: {e}")

    return clean.strip(), tool_results
