"""
src/agents/jarvis.py
====================
Wrapper JarvisAgent autour de BrainLoop pour l'API FastAPI.
Expose : start(), stop(), get_status(), is_running, insights
"""

import logging
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class JarvisAgent:
    """
    Agent proactif Jarvis — tourne en background thread.
    Compatible avec l'API FastAPI (src/api/main.py).
    """

    def __init__(
        self,
        llm_client=None,
        vector_store=None,
        memory=None,
        interval_minutes: int = 15,
    ):
        self.llm = llm_client
        self.vector_store = vector_store
        self.memory = memory
        self.interval = interval_minutes * 60

        self.is_running: bool = False
        self.insights: List[Dict[str, Any]] = []
        self.cycle_count: int = 0
        self.last_run: Optional[str] = None
        self.last_error: Optional[str] = None

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ── Cycle principal ──────────────────────────────────────────────

    def _run_cycle(self) -> Dict[str, Any]:
        """Un cycle complet : charge mémoire → génère insights → crée tâches."""
        self.cycle_count += 1
        self.last_run = datetime.now().isoformat()
        result = {"cycle": self.cycle_count, "insights_generated": 0, "tasks_created": 0}

        try:
            # --- Charger la mémoire ---
            memories = []
            try:
                from src.memory.history import load_memory
                memories = load_memory()
            except ImportError:
                logger.debug("src.memory.history not found, skipping memory load")

            # --- Charger les objectifs ---
            goals = []
            try:
                from src.goals import load_goals
                goals = load_goals()
            except ImportError:
                pass

            # --- Ranker les mémoires ---
            important = []
            if memories:
                try:
                    from src.agent.attention import rank_memories
                    from config.settings import ATTENTION_THRESHOLD
                    ranked = rank_memories(memories, goals)
                    important = [m for m in ranked if m.get("attention_score", 0) >= ATTENTION_THRESHOLD]
                except ImportError:
                    important = memories[-10:]  # fallback : 10 dernières

            # --- Générer insights via LLM ---
            if important and self.llm and self.llm.is_available():
                new_insights = self._generate_insights(important, goals)
                self.insights.extend(new_insights)
                result["insights_generated"] = len(new_insights)

                # --- Créer des tâches depuis les insights ---
                try:
                    from src.agent.task_generator import generate_tasks
                    new_tasks = generate_tasks(insights=new_insights, goals=goals)
                    result["tasks_created"] = len(new_tasks)
                except ImportError:
                    pass

            logger.info(
                f"[Jarvis] Cycle {self.cycle_count} — "
                f"{len(memories)} memories | "
                f"{result['insights_generated']} insights | "
                f"{result['tasks_created']} tasks"
            )

        except Exception as e:
            self.last_error = str(e)
            logger.error(f"[Jarvis] Cycle error: {e}", exc_info=True)

        return result

    def _generate_insights(self, memories: list, goals: list) -> List[Dict[str, Any]]:
        """Génère des insights structurés via le LLM local."""
        if not self.llm or not self.llm.is_available():
            return []

        mem_summary = "\n".join(
            f"- {m.get('question', str(m))[:120]}"
            for m in memories[:5]
        )
        goal_summary = "\n".join(
            f"- {g.get('title', str(g))}" if isinstance(g, dict) else f"- {g}"
            for g in goals[:3]
        )

        prompt = (
            "Tu es un assistant personnel proactif. Analyse ces mémoires et objectifs.\n\n"
            f"OBJECTIFS:\n{goal_summary or 'Aucun objectif défini.'}\n\n"
            f"MÉMOIRES RÉCENTES:\n{mem_summary}\n\n"
            "Génère 2-3 insights courts et actionnables (une phrase chacun). "
            "Format : une ligne par insight, commençant par un emoji pertinent."
        )

        try:
            response = self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            lines = [l.strip() for l in response.strip().split("\n") if l.strip()]
            return [
                {"text": line, "timestamp": datetime.now().isoformat(), "cycle": self.cycle_count}
                for line in lines[:3]
                if len(line) > 10
            ]
        except Exception as e:
            logger.debug(f"Insight generation failed: {e}")
            return []

    # ── Thread loop ──────────────────────────────────────────────────

    def _loop(self):
        """Boucle background : run → wait → run → ..."""
        logger.info(f"[Jarvis] Loop started (interval={self.interval}s)")
        self._run_cycle()
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=self.interval)
            if not self._stop_event.is_set():
                self._run_cycle()
        logger.info("[Jarvis] Loop stopped")

    # ── API publique ──────────────────────────────────────────────────

    def start(self):
        """Démarre Jarvis en background thread (non-bloquant)."""
        if self.is_running:
            logger.warning("[Jarvis] Already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="JarvisThread")
        self._thread.start()
        self.is_running = True
        logger.info("[Jarvis] Started")

    def stop(self):
        """Arrête proprement la boucle Jarvis."""
        if not self.is_running:
            return
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        self.is_running = False
        logger.info("[Jarvis] Stopped")

    def get_status(self) -> Dict[str, Any]:
        """Retourne l'état complet de Jarvis (pour /api/jarvis/status)."""
        return {
            "running": self.is_running,
            "cycle_count": self.cycle_count,
            "last_run": self.last_run,
            "last_error": self.last_error,
            "insights_total": len(self.insights),
            "interval_seconds": self.interval,
            "thread_alive": self._thread.is_alive() if self._thread else False,
        }