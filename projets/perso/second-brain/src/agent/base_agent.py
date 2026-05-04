"""
Second Brain — Base Agent
=========================
Abstract contract for all specialized agents in the system.
"""

from abc import ABC, abstractmethod
import logging
from typing import Any, Dict

from src.ai.llm_client import LLMClient

class BaseAgent(ABC):
    """
    Abstract base class for all Second Brain agents.
    """
    name: str = "BaseAgent"
    
    def __init__(self, llm: LLMClient = None):
        self.llm = llm or LLMClient()
        self.logger = logging.getLogger(f"agent.{self.name.lower()}")
    
    @abstractmethod
    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the agent's primary function.
        
        Args:
            context: A dictionary of state passed from the Coordinator.
                     Includes memory, goals, tasks, and previous agent outputs.
                     
        Returns:
            A dictionary representing the agent's output/updates to the state.
        """
        pass
