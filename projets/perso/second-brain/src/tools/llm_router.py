"""
Second Brain — LLM Tool Router (Phase 5)
============================================
Decides when and which tool to use based on user input.

Pipeline:
  1. Build a prompt listing available tools + their schemas
  2. Send to LLM with the user's query
  3. Parse the structured JSON response
  4. Return tool name + args (or null if no tool needed)

The LLM outputs strict JSON:
  {"tool": "create_note", "args": {"title": "...", "content": "..."}}
  {"tool": null}  — if no tool is needed
"""

import json
import logging
import re
from typing import Optional

from src.ai.llm_client import LLMClient
from src.tools.registry import list_tools, get_tool_names

logger = logging.getLogger(__name__)


# ── Prompts ─────────────────────────────────────────────────────────

ROUTER_SYSTEM_PROMPT = """Tu es un routeur d'outils intelligent pour un assistant IA personnel.

Ton rôle est de déterminer si la requête de l'utilisateur nécessite l'utilisation d'un outil,
et si oui, lequel et avec quels arguments.

Règles STRICTES :
1. Analyse la requête de l'utilisateur.
2. Si un outil est pertinent, retourne un objet JSON avec "tool" et "args".
3. Si AUCUN outil n'est pertinent (question simple, conversation), retourne {"tool": null}.
4. Retourne UNIQUEMENT du JSON valide, RIEN d'autre (pas de texte, pas d'explication).
5. Les arguments doivent correspondre exactement au schéma de l'outil.

Format de réponse OBLIGATOIRE (et RIEN d'autre) :
{"tool": "nom_outil", "args": {"arg1": "valeur1"}}
ou
{"tool": null}
"""

ROUTER_PROMPT_TEMPLATE = """=== OUTILS DISPONIBLES ===
{tools_description}

=== REQUÊTE DE L'UTILISATEUR ===
{user_query}

=== CONTEXTE ADDITIONNEL ===
{context}

Quel outil utiliser ? Retourne UNIQUEMENT du JSON valide.
"""


# ── Public API ──────────────────────────────────────────────────────

def route_query(
    user_query: str,
    context: str = "",
    llm: LLMClient = None,
) -> Optional[dict]:
    """
    Déterminer si une requête nécessite un outil.

    Args:
        user_query: La question/demande de l'utilisateur.
        context:    Contexte additionnel (mémoires, objectifs).
        llm:        Client LLM (en crée un si non fourni).

    Returns:
        Dict {"tool": "...", "args": {...}} si un outil est nécessaire,
        None si la requête est une conversation normale.
    """
    if not user_query:
        return None

    if llm is None:
        llm = LLMClient()

    # Build tools description
    tools = list_tools()
    if not tools:
        logger.info("No tools registered — skipping routing")
        return None

    tools_desc = _format_tools(tools)

    prompt = ROUTER_PROMPT_TEMPLATE.format(
        tools_description=tools_desc,
        user_query=user_query,
        context=context or "(aucun contexte)",
    )

    try:
        raw_response = llm.generate(
            prompt=prompt,
            system_prompt=ROUTER_SYSTEM_PROMPT,
            temperature=0.1,  # Low temp for structured output
            max_tokens=200,
        )

        result = _parse_tool_response(raw_response)
        if result and result.get("tool"):
            logger.info(
                f"Router decision: use '{result['tool']}' "
                f"with args={result.get('args', {})}"
            )
        else:
            logger.info("Router decision: no tool needed")

        return result

    except ConnectionError:
        logger.error("Cannot connect to Ollama for tool routing")
        return None
    except Exception as e:
        logger.error(f"Tool routing failed: {e}")
        return None


def route_and_execute(
    user_query: str,
    context: str = "",
    llm: LLMClient = None,
    confirm_fn=None,
) -> Optional[dict]:
    """
    Router + exécuter en une seule étape.

    Combine route_query() et execute_tool() pour un usage simple.

    Returns:
        Dict avec le résultat de l'outil, ou None si pas d'outil.
    """
    from src.tools.registry import execute_tool

    decision = route_query(user_query, context, llm)

    if decision is None or decision.get("tool") is None:
        return None

    tool_name = decision["tool"]
    args = decision.get("args", {})

    return execute_tool(tool_name, args, confirm_fn=confirm_fn)


# ── Internal Logic ──────────────────────────────────────────────────

def _format_tools(tools: list[dict]) -> str:
    """Format tool list for the LLM prompt."""
    parts = []
    for tool in tools:
        args_desc = ""
        for arg_name, arg_def in tool.get("args", {}).items():
            required = "REQUIS" if arg_def.get("required") else "optionnel"
            desc = arg_def.get("description", "")
            arg_type = arg_def.get("type", "string")
            args_desc += f"    - {arg_name} ({arg_type}, {required}): {desc}\n"

        parts.append(
            f"Outil: {tool['name']}\n"
            f"  Description: {tool['description']}\n"
            f"  Permission: {tool['permission_level']}\n"
            f"  Arguments:\n{args_desc}"
        )

    return "\n".join(parts)


def _parse_tool_response(raw_text: str) -> Optional[dict]:
    """
    Parse the LLM response to extract tool + args.

    Handles:
    - Clean JSON responses
    - JSON embedded in markdown code blocks
    - Messy LLM output with text around the JSON
    """
    if not raw_text:
        return None

    text = raw_text.strip()

    # Try 1: Direct JSON parse
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return _validate_parsed(result)
    except json.JSONDecodeError:
        pass

    # Try 2: Extract from markdown code block
    code_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if code_match:
        try:
            result = json.loads(code_match.group(1).strip())
            if isinstance(result, dict):
                return _validate_parsed(result)
        except json.JSONDecodeError:
            pass

    # Try 3: Find JSON-like substring with nested braces
    json_str = _extract_json_object(text)
    if json_str:
        try:
            result = json.loads(json_str)
            if isinstance(result, dict):
                return _validate_parsed(result)
        except json.JSONDecodeError:
            pass

    logger.warning(f"Failed to parse tool response: {text[:200]}")
    return None


def _validate_parsed(result: dict) -> Optional[dict]:
    """Validate the parsed JSON has the expected structure."""
    # Must have "tool" key
    if "tool" not in result:
        return None

    tool_name = result.get("tool")

    # null tool = no tool needed
    if tool_name is None:
        return {"tool": None}

    # Verify tool exists
    if tool_name not in get_tool_names():
        logger.warning(f"LLM suggested unknown tool: '{tool_name}'")
        return None

    # Ensure args is a dict
    args = result.get("args", {})
    if not isinstance(args, dict):
        args = {}

    return {"tool": tool_name, "args": args}


def _extract_json_object(text: str) -> Optional[str]:
    """
    Extract a JSON object from text using brace counting.
    Handles nested braces.
    """
    start_idx = text.find('{')
    if start_idx == -1:
        return None

    brace_count = 0
    in_string = False
    escape = False

    for i in range(start_idx, len(text)):
        char = text[i]

        if escape:
            escape = False
            continue

        if char == '\\':
            escape = True
        elif char == '"':
            in_string = not in_string
        elif not in_string:
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    return text[start_idx:i+1]

    return None

