"""src/agents_v2/coordinator.py — Minimalist agentic coordinator.

Flow: User request → Plan → Research → Execute → Validate → Respond

Integrates:
- Planner:     breaks down request into steps
- Retriever:   searches documents
- Executor:    generates final answer
- PermissionManager: validates dangerous actions
- ProfileManager: personalizes responses
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CoordinatorResponse:
    """Result of a coordinator cycle."""
    answer: str
    plan: List[Dict[str, Any]] = field(default_factory=list)
    sources: List[Dict[str, Any]] = field(default_factory=list)
    actions_proposed: List[Dict[str, Any]] = field(default_factory=list)
    actions_approved: List[Dict[str, Any]] = field(default_factory=list)
    actions_rejected: List[Dict[str, Any]] = field(default_factory=list)
    confidence: str = "low"
    profile_used: bool = False


class Coordinator:
    """Minimalist agentic coordinator.

    Usage:
        coord = Coordinator(llm_client, rag_pipeline, profile_manager, permission_manager)
        response = coord.handle("Prépare-moi un plan de révision pour mon partiel de macro.")
        print(response.answer)
    """

    def __init__(
        self,
        llm_client=None,
        rag_pipeline=None,
        profile_manager=None,
        permission_manager=None,
    ):
        from src.agents_v2.planner import Planner
        from src.agents_v2.retriever import Retriever
        from src.agents_v2.executor import Executor

        self.llm = llm_client
        self.planner = Planner(llm_client)
        self.retriever = Retriever(rag_pipeline=rag_pipeline)
        self.executor = Executor(llm_client)
        self.profile = profile_manager
        self.permissions = permission_manager

    def handle(self, user_request: str) -> CoordinatorResponse:
        """Full coordinator cycle: Plan → Research → Execute → Validate.

        Args:
            user_request: The user's natural language request.

        Returns:
            CoordinatorResponse with answer, plan, sources, and action status.
        """
        # ── Load profile context ─────────────────────────────────────
        profile_context = ""
        profile_used = False
        if self.profile:
            profile_context = self.profile.format_for_prompt()
            profile_used = bool(profile_context)

        # ── Step 1: Plan ─────────────────────────────────────────────
        logger.info(f"Coordinator: planning for '{user_request[:60]}...'")
        plan_context = user_request
        if profile_context:
            plan_context = f"{profile_context}\n\nDemande : {user_request}"
        steps = self.planner.plan(plan_context)
        logger.info(f"Coordinator: plan has {len(steps)} steps")

        # ── Step 2: Research ─────────────────────────────────────────
        all_sources = []
        all_context = []
        for step in steps:
            if step.type == "retrieve":
                query = step.params.get("query", user_request)
                chunks = self.retriever.search(query)
                if chunks:
                    all_sources.extend(chunks)
                    all_context.append(self.retriever.format_context(chunks))

            elif step.type == "web_search":
                query = step.params.get("query", user_request)
                try:
                    from src.ai.tools import web_search as ws
                    wr = ws(query, max_results=3)
                    if wr.get("status") == "ok" and wr.get("results"):
                        web_ctx = "\n".join(
                            f"- {r['title']}: {r['snippet']} ({r['url']})"
                            for r in wr["results"]
                        )
                        all_context.append(f"[Résultats web pour: {query}]\n{web_ctx}")
                        all_sources.append({
                            "source_file": "web",
                            "content": web_ctx,
                            "relevance": 0.8,
                        })
                except Exception as e:
                    logger.warning(f"Web search failed: {e}")

        context_text = "\n\n".join(all_context) if all_context else ""
        logger.info(f"Coordinator: retrieved {len(all_sources)} chunks")

        # ── Step 3: Execute ──────────────────────────────────────────
        actions_proposed = []
        actions_approved = []
        actions_rejected = []

        if self.permissions:
            for step in steps:
                tool_name = step.params.get("tool_name", "")
                if not tool_name:
                    continue
                from src.core.permissions import ActionCategory
                category = self._classify_action(tool_name)
                action = self.permissions.propose(
                    tool_name=tool_name,
                    category=category,
                    params=step.params,
                    description=f"Step: {step.type}",
                )
                actions_proposed.append({
                    "tool": tool_name,
                    "params": step.params,
                    "needs_approval": action.requires_approval,
                    "status": action.status,
                })
                if action.status == "approved":
                    actions_approved.append({"tool": tool_name, "params": step.params})
                elif action.status == "rejected":
                    actions_rejected.append({"tool": tool_name, "params": step.params})

        # ── Step 4: Generate answer ──────────────────────────────────
        result = self.executor.execute(
            steps=steps,
            context=context_text,
            user_message=user_request,
        )

        # ── Step 5: Build response ───────────────────────────────────
        sources = [
            {
                "source_file": r.get("source_file", "unknown"),
                "relevance": r.get("relevance", 0),
                "preview": (r.get("content", "")[:150] + "...") if len(r.get("content", "")) > 150 else r.get("content", ""),
            }
            for r in all_sources[:5]
        ]

        confidence = "medium"
        if not all_sources:
            confidence = "low"
        elif len(all_sources) >= 3:
            confidence = "high"

        return CoordinatorResponse(
            answer=result.get("answer", "Je n'ai pas pu traiter cette demande."),
            plan=[
                {"type": s.type, "params": s.params}
                for s in steps
            ],
            sources=sources,
            actions_proposed=actions_proposed,
            actions_approved=actions_approved,
            actions_rejected=actions_rejected,
            confidence=confidence,
            profile_used=profile_used,
        )

    def _classify_action(self, tool_name: str):
        """Classify a tool action by risk category."""
        from src.core.permissions import ActionCategory
        safe = {"get_date_time", "calculator", "list_documents", "web_search", "retrieve"}
        write = {"create_task", "create_note", "export_data", "update_task"}
        delete = {"delete_document", "delete_task", "reset_system"}
        if tool_name in delete:
            return ActionCategory.DELETE
        if tool_name in write:
            return ActionCategory.WRITE
        return ActionCategory.READ
