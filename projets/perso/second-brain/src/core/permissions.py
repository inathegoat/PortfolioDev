"""src/core/permissions.py — Permission system for agent actions.

Every external action must pass through explicit user validation.
Whitelist: safe actions that don't need approval.
Blacklist: dangerous actions always blocked.
Default: require user confirmation.
"""
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ActionCategory(Enum):
    READ = "read"           # Read files, search documents, get date
    COMPUTE = "compute"     # Calculator, data processing
    WRITE = "write"         # Create files, modify data, send email
    DELETE = "delete"       # Delete files, remove data
    NETWORK = "network"     # Web search, API calls, email


@dataclass
class ProposedAction:
    """An action proposed by an agent, pending user approval."""
    action_id: str
    category: ActionCategory
    tool_name: str
    params: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    requires_approval: bool = True
    status: str = "pending"  # pending, approved, rejected, executed


class PermissionManager:
    """Manages action permissions and user approvals.

    Usage:
        pm = PermissionManager()

        # Register callbacks for user approval
        pm.set_approval_callback(lambda action: input(f"Approve {action.tool_name}? [y/N] ") == 'y')

        # Propose an action
        action = pm.propose("send_email", ActionCategory.NETWORK, {"to": "x@y.com"})
        if pm.request_approval(action):
            pm.execute(action)

    Safe actions (never need approval):
        - get_date_time, calculator, list_documents, search
    """

    # Actions that NEVER need approval
    SAFE_ACTIONS = {
        "get_date_time", "calculator", "list_documents",
        "web_search", "search_documents", "retrieve",
    }

    # Actions that are ALWAYS blocked (until configured)
    BLOCKED_ACTIONS = {
        "delete_document", "delete_task", "reset_system",
        "execute_shell", "install_package",
    }

    def __init__(self):
        self._approval_callback: Optional[Callable[[ProposedAction], bool]] = None
        self._pending: List[ProposedAction] = []
        self._history: List[ProposedAction] = []
        self._custom_safe: set = set()
        self._custom_blocked: set = set()

    def set_approval_callback(self, callback: Callable[[ProposedAction], bool]):
        """Set the function that will be called for user approval."""
        self._approval_callback = callback

    def add_safe_action(self, tool_name: str):
        """Mark a tool as safe (no approval needed)."""
        self._custom_safe.add(tool_name)

    def add_blocked_action(self, tool_name: str):
        """Block a tool entirely."""
        self._custom_blocked.add(tool_name)

    def propose(
        self,
        tool_name: str,
        category: ActionCategory,
        params: Optional[Dict[str, Any]] = None,
        description: str = "",
    ) -> ProposedAction:
        """Create a proposed action and determine if it needs approval."""
        action_id = f"act_{len(self._history)}_{tool_name}"

        # Check blocked
        if tool_name in self.BLOCKED_ACTIONS or tool_name in self._custom_blocked:
            action = ProposedAction(
                action_id=action_id, category=category,
                tool_name=tool_name, params=params or {},
                description=description, requires_approval=True,
                status="rejected",
            )
            logger.warning(f"Blocked action attempted: {tool_name}")
            return action

        # Check safe
        needs_approval = True
        if tool_name in self.SAFE_ACTIONS or tool_name in self._custom_safe:
            needs_approval = False
        elif category in (ActionCategory.READ, ActionCategory.COMPUTE):
            needs_approval = False

        action = ProposedAction(
            action_id=action_id, category=category,
            tool_name=tool_name, params=params or {},
            description=description, requires_approval=needs_approval,
        )
        self._pending.append(action)
        return action

    def request_approval(self, action: ProposedAction) -> bool:
        """Request user approval for an action.

        Returns True if approved, False otherwise.
        Safe actions are auto-approved.
        """
        if not action.requires_approval:
            action.status = "approved"
            return True

        if self._approval_callback:
            try:
                approved = self._approval_callback(action)
                action.status = "approved" if approved else "rejected"
                return approved
            except Exception as e:
                logger.error(f"Approval callback failed: {e}")
                action.status = "rejected"
                return False

        # No callback → default deny
        action.status = "rejected"
        return False

    def approve(self, action: ProposedAction):
        """Manually approve an action."""
        action.status = "approved"

    def reject(self, action: ProposedAction):
        """Manually reject an action."""
        action.status = "rejected"

    def mark_executed(self, action: ProposedAction):
        """Mark an approved action as executed."""
        if action.status == "approved":
            action.status = "executed"
            self._history.append(action)
            if action in self._pending:
                self._pending.remove(action)

    def get_pending(self) -> List[ProposedAction]:
        """Get all pending actions needing approval."""
        return [a for a in self._pending if a.status == "pending"]

    def get_history(self, limit: int = 20) -> List[ProposedAction]:
        """Get recent action history."""
        return self._history[-limit:]

    def summary(self) -> Dict[str, Any]:
        """Get permission system status."""
        return {
            "pending_approvals": len(self.get_pending()),
            "total_actions": len(self._history),
            "safe_actions": sorted(self.SAFE_ACTIONS | self._custom_safe),
            "blocked_actions": sorted(self.BLOCKED_ACTIONS | self._custom_blocked),
        }
