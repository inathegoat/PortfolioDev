"""src/core/errors.py — Domain exceptions for the Second Brain."""


class SecondBrainError(Exception):
    """Base exception for all Second Brain errors."""


class ConfigError(SecondBrainError):
    """Configuration-related error."""


class IngestionError(SecondBrainError):
    """Document ingestion failed."""


class RetrievalError(SecondBrainError):
    """Vector search or retrieval failed."""


class LLMError(SecondBrainError):
    """LLM generation or connection failed."""


class ToolError(SecondBrainError):
    """Tool execution failed."""


class SecurityError(SecondBrainError):
    """Security violation (auth, access, path traversal)."""
