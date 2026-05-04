"""src/agents_v2/planner.py — Breaks down user request into actionable steps.

Input: user message + conversation context
Output: list of (action_type, parameters)
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_PLANNER = """Tu es un planificateur. Ton rôle est de décomposer une demande utilisateur en étapes concrètes.

Types d'étapes possibles :
- retrieve: chercher dans les documents (param: query)
- web_search: chercher sur internet (param: query)
- create_task: créer une tâche (params: title, description)
- get_date: obtenir la date/heure
- answer: répondre directement (param: response)

Réponds UNIQUEMENT en JSON :
{
  "steps": [
    {"type": "retrieve", "query": "question précise"},
    {"type": "answer", "response": null}
  ]
}
"""


@dataclass
class Step:
    """A single execution step."""
    type: str
    params: Dict[str, Any] = field(default_factory=dict)


class Planner:
    """Decomposes user requests into execution steps."""

    def __init__(self, llm_client=None):
        self._llm = llm_client

    def plan(self, user_message: str, context: Optional[str] = None) -> List[Step]:
        """Generate a plan from the user's message.

        If no LLM is available, returns a default plan.
        """
        if not self._llm or not self._llm.is_available():
            return self._default_plan(user_message)

        prompt = f"Demande : {user_message}"
        if context:
            prompt = f"Contexte : {context}\n\n{prompt}"

        try:
            raw = self._llm.generate(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT_PLANNER,
                temperature=0.1,
                max_tokens=300,
            )
            return self._parse_plan(raw)
        except Exception as e:
            logger.warning(f"Planner LLM failed: {e}, using default plan")
            return self._default_plan(user_message)

    def _default_plan(self, message: str) -> List[Step]:
        """Fallback: always retrieve + answer."""
        return [
            Step(type="retrieve", params={"query": message}),
            Step(type="answer", params={}),
        ]

    def _parse_plan(self, raw: str) -> List[Step]:
        """Parse JSON plan from LLM output."""
        import json
        # Extract JSON block
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(raw[start:end])
                return [Step(type=s["type"], params={k: v for k, v in s.items() if k != "type"})
                        for s in data.get("steps", [])]
            except (json.JSONDecodeError, KeyError):
                pass
        return self._default_plan("fallback")
