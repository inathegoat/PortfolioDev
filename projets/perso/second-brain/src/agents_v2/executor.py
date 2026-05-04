"""src/agents_v2/executor.py — Executes steps and produces final response.

Input: plan steps + retrieved context
Output: final answer or action result
"""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_EXECUTOR = """Tu es un assistant qui répond aux questions en te basant UNIQUEMENT sur le contexte fourni.

Règles :
1. Utilise uniquement les informations du contexte.
2. Pour chaque affirmation, cite la source : [Source: nom_fichier].
3. Si le contexte est insuffisant, dis-le clairement.
4. Sois concis et factuel.
5. Réponds en français.
"""


class Executor:
    """Executes plan steps and generates the final response."""

    def __init__(self, llm_client=None, tools_registry=None):
        self._llm = llm_client
        self._tools = tools_registry or {}

    def execute(
        self,
        steps: list,
        context: str = "",
        user_message: str = "",
    ) -> Dict[str, Any]:
        """Execute all steps and return the result.

        Returns:
            dict with keys: answer, sources_used, tool_results
        """
        retrieved_context = context
        tool_results = []

        for step in steps:
            # Handle both Step dataclass and dict
            if hasattr(step, 'type'):
                step_type = step.type
                params = step.params if hasattr(step, 'params') else {}
            elif isinstance(step, dict):
                step_type = step.get("type", "")
                params = {k: v for k, v in step.items() if k != "type"}
            else:
                continue

            if step_type == "answer":
                if not retrieved_context:
                    answer = "Je ne trouve pas d'information pertinente dans vos documents."
                else:
                    answer = self._generate_answer(user_message, retrieved_context)
                return {
                    "answer": answer,
                    "context_used": retrieved_context,
                    "tool_results": tool_results,
                }

            elif step_type == "get_date":
                from datetime import datetime
                result = datetime.now().strftime("Nous sommes le %d/%m/%Y, il est %H:%M.")
                tool_results.append({"tool": "get_date", "result": result})

            elif step_type in self._tools:
                try:
                    result = self._tools[step_type](**params)
                    tool_results.append({"tool": step_type, "result": result})
                except Exception as e:
                    tool_results.append({"tool": step_type, "error": str(e)})

        # No answer step found, generate one
        return {
            "answer": self._generate_answer(user_message, retrieved_context),
            "context_used": retrieved_context,
            "tool_results": tool_results,
        }

    def _generate_answer(self, question: str, context: str) -> str:
        """Generate final answer from context."""
        if not self._llm or not self._llm.is_available():
            return f"Contexte trouvé mais LLM indisponible. Contexte : {context[:300]}..."

        prompt = (
            f"=== CONTEXTE ===\n{context}\n=== FIN CONTEXTE ===\n\n"
            f"Question : {question}"
        )
        try:
            return self._llm.generate(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT_EXECUTOR,
                temperature=0.3,
            )
        except Exception as e:
            logger.error(f"Executor LLM failed: {e}")
            return f"Erreur lors de la génération : {e}"
