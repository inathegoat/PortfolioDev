"""
Second Brain — Base Tool Contract (Phase 5)
==============================================
Defines the abstract interface all tools must implement.

Every tool must declare:
  - name:             Unique identifier (e.g. "create_note")
  - description:      Human-readable purpose
  - permission_level: "read_only" | "safe_write" | "restricted"
  - schema():         JSON-like dict describing expected arguments
  - execute(**args):   Perform the action and return a result dict
"""

from abc import ABC, abstractmethod


# ── Permission Levels ───────────────────────────────────────────────

PERMISSION_READ_ONLY = "read_only"       # No side effects
PERMISSION_SAFE_WRITE = "safe_write"     # Creates/edits notes, tasks
PERMISSION_RESTRICTED = "restricted"     # Destructive — needs confirmation

VALID_PERMISSIONS = {
    PERMISSION_READ_ONLY,
    PERMISSION_SAFE_WRITE,
    PERMISSION_RESTRICTED,
}


class BaseTool(ABC):
    """
    Contrat de base pour tous les outils du système.

    Sous-classes doivent définir :
      - name, description, permission_level
      - schema() → dict décrivant les arguments attendus
      - execute(**kwargs) → dict avec le résultat

    Exemple :
        class MyTool(BaseTool):
            name = "my_tool"
            description = "Does something"
            permission_level = "safe_write"

            def schema(self):
                return {
                    "title": {"type": "string", "required": True},
                }

            def execute(self, title="", **kwargs):
                return {"status": "success", "message": f"Created: {title}"}
    """

    name: str = ""
    description: str = ""
    permission_level: str = PERMISSION_SAFE_WRITE

    @abstractmethod
    def schema(self) -> dict:
        """
        Retourner le schéma des arguments attendus.

        Format :
            {
                "arg_name": {
                    "type": "string" | "int" | "bool",
                    "required": True | False,
                    "description": "...",
                    "default": ...  (optionnel)
                }
            }
        """
        ...

    @abstractmethod
    def execute(self, **kwargs) -> dict:
        """
        Exécuter l'outil avec les arguments validés.

        Returns:
            Dict avec au minimum :
              - "status": "success" | "error"
              - "message": texte descriptif du résultat
              - ...données supplémentaires propres à l'outil
        """
        ...

    def validate_args(self, args: dict) -> tuple[bool, str]:
        """
        Valider les arguments contre le schéma.

        Args:
            args: Dict d'arguments à valider.

        Returns:
            (True, "") si valide,
            (False, "raison") si invalide.
        """
        tool_schema = self.schema()

        # Check required fields
        for field_name, field_def in tool_schema.items():
            if field_def.get("required", False):
                if field_name not in args or args[field_name] is None:
                    return False, f"Argument requis manquant : '{field_name}'"

                # Type check
                expected_type = field_def.get("type", "string")
                value = args[field_name]
                if not _check_type(value, expected_type):
                    return (
                        False,
                        f"Type invalide pour '{field_name}' : "
                        f"attendu {expected_type}, reçu {type(value).__name__}",
                    )

        # Check for unknown args
        known = set(tool_schema.keys())
        unknown = set(args.keys()) - known
        if unknown:
            return False, f"Arguments inconnus : {unknown}"

        return True, ""

    def to_dict(self) -> dict:
        """Sérialiser l'outil pour affichage ou prompt LLM."""
        return {
            "name": self.name,
            "description": self.description,
            "permission_level": self.permission_level,
            "args": self.schema(),
        }


# ── Helpers ─────────────────────────────────────────────────────────

def _check_type(value, expected: str) -> bool:
    """Check if a value matches the expected type string."""
    type_map = {
        "string": str,
        "str": str,
        "int": int,
        "integer": int,
        "float": (int, float),
        "bool": bool,
        "boolean": bool,
        "list": list,
    }
    expected_type = type_map.get(expected, str)
    if isinstance(expected_type, tuple):
        return isinstance(value, expected_type)
    return isinstance(value, expected_type)
