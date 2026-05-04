"""
Second Brain — Brain Loop (Phase 4 — Jarvis Mode)
====================================================
The proactive agent loop that runs in the background.

Every AGENT_LOOP_INTERVAL seconds, it:
1. Loads all memories from history
2. Ranks them using the attention system
3. Filters by the attention threshold
4. Generates insights using the local LLM
5. Converts insights into structured tasks (Phase 4)
6. Checks follow-ups on pending tasks (Phase 4)
7. Sends desktop notifications for important findings + reminders

This transforms the system from reactive (user asks) to
proactive (system drives execution).

Usage:
    python main.py agent              # Start the proactive loop
    python main.py agent --once       # Run one cycle and exit
    python main.py agent --interval 600  # Custom interval (10 min)
"""

import logging
import signal
import sys
import time
import threading

from config.settings import AGENT_LOOP_INTERVAL, ATTENTION_THRESHOLD
from src.memory.history import load_memory
from src.goals import load_goals
from src.tasks import get_pending_tasks
from src.agent.attention import rank_memories
from src.agent.insights import generate_insights
from src.agent.task_generator import generate_tasks
from src.agent.follow_up import check_follow_ups
from src.agent.notifier import notify_insights, notify

logger = logging.getLogger(__name__)


class BrainLoop:
    """
    The proactive brain loop — the heart of Jarvis mode.

    Periodically analyzes the user's memory, identifies important
    patterns, generates insights, creates tasks, sends reminders,
    and notifies proactively.

    Usage:
        loop = BrainLoop(interval=300)
        loop.start()  # Blocks until Ctrl+C
    """

    def __init__(self, interval: int = AGENT_LOOP_INTERVAL):
        """
        Initialize the brain loop.

        Args:
            interval: Seconds between each cycle (default from settings).
        """
        self.interval = interval
        self._stop_event = threading.Event()
        self._cycle_count = 0

    def start(self):
        """
        Start the brain loop (blocking).

        Runs until interrupted with Ctrl+C or stop() is called.
        """
        logger.info(
            f"🧠 Brain Loop started | interval={self.interval}s | "
            f"threshold={ATTENTION_THRESHOLD}"
        )

        # Handle graceful shutdown
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        # Run first cycle immediately
        self._run_cycle()

        # Then loop with intervals
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=self.interval)
            if not self._stop_event.is_set():
                self._run_cycle()

        logger.info("🧠 Brain Loop stopped cleanly")

    def run_once(self):
        """Run a single brain cycle and return the results."""
        return self._run_cycle()

    def stop(self):
        """Signal the loop to stop."""
        self._stop_event.set()

    def _run_cycle(self) -> dict:
        """
        Execute one brain cycle.

        Full pipeline:
        memory → attention → insights → tasks → follow-up → notify

        Returns:
            Dict with cycle results.
        """
        self._cycle_count += 1
        logger.info(f"━━━ Brain Cycle #{self._cycle_count} ━━━")

        result = {
            "cycle": self._cycle_count,
            "memories_loaded": 0,
            "memories_above_threshold": 0,
            "insights_generated": 0,
            "tasks_created": 0,
            "reminders_sent": 0,
            "notifications_sent": 0,
        }

        try:
            # ── Step 1: Load memory ─────────────────────────────────
            memories = load_memory()
            result["memories_loaded"] = len(memories)

            if not memories:
                logger.info("No memories yet — skipping cycle")
                # Still check follow-ups even without new memories
                self._run_follow_ups(result)
                return result

            logger.info(f"Loaded {len(memories)} memories")

            # ── Step 2: Load goals ──────────────────────────────────
            goals = load_goals()
            logger.info(f"Loaded {len(goals)} goals")

            # ── Step 3: Rank memories ───────────────────────────────
            ranked = rank_memories(memories, goals)

            # ── Step 4: Filter by threshold ─────────────────────────
            important = [
                m for m in ranked
                if m["attention_score"] >= ATTENTION_THRESHOLD
            ]
            result["memories_above_threshold"] = len(important)

            if not important:
                logger.info(
                    f"No memories above threshold ({ATTENTION_THRESHOLD}) — "
                    f"top score was {ranked[0]['attention_score']:.3f}"
                )
                self._run_follow_ups(result)
                return result

            logger.info(
                f"{len(important)} memories above threshold | "
                f"top={important[0]['attention_score']:.3f}"
            )

            # Log top 3 for debugging
            for i, mem in enumerate(important[:3]):
                logger.info(
                    f"  #{i+1} [{mem['attention_score']:.3f}] "
                    f"Q: {mem.get('question', '')[:60]}... "
                    f"Goals: {mem.get('matched_goals', [])}"
                )

            # ── Step 5: Generate insights ───────────────────────────
            insights = generate_insights(important, goals)
            result["insights_generated"] = len(insights)

            if not insights:
                logger.info("No actionable insights generated")
                self._run_follow_ups(result)
                return result

            for i, insight in enumerate(insights):
                logger.info(f"  💡 Insight {i+1}: {insight}")

            # ── Step 6: Convert insights → tasks (Phase 4) ─────────
            new_tasks = generate_tasks(
                insights=insights,
                goals=goals,
                ranked_memories=important,
            )
            result["tasks_created"] = len(new_tasks)

            if new_tasks:
                for task in new_tasks:
                    logger.info(
                        f"  📋 Task: {task['title']} "
                        f"({len(task.get('steps', []))} steps)"
                    )

            # ── Step 7: Notify about insights ──────────────────────
            sent = notify_insights(insights)
            result["notifications_sent"] = sent

            # ── Step 8: Follow-ups on existing tasks (Phase 4) ─────
            self._run_follow_ups(result)

            logger.info(
                f"Cycle #{self._cycle_count} complete: "
                f"{len(memories)} memories → "
                f"{len(important)} important → "
                f"{len(insights)} insights → "
                f"{result['tasks_created']} tasks → "
                f"{result['reminders_sent']} reminders"
            )

        except Exception as e:
            logger.error(f"Brain cycle error: {e}", exc_info=True)

        return result

    def _run_follow_ups(self, result: dict) -> None:
        """
        Check pending tasks and send follow-up reminders.

        Mutates `result` to add reminders_sent count.
        """
        try:
            pending = get_pending_tasks()
            if not pending:
                return

            reminders = check_follow_ups(pending)
            for reminder in reminders:
                message = reminder["message"]
                level = reminder["level"]
                title = f"{'⚠️' if level == 'escalade' else '📋'} Second Cerveau"

                success = notify(message, title=title)
                if success:
                    result["reminders_sent"] = result.get("reminders_sent", 0) + 1
                    logger.info(f"  🔔 Reminder ({level}): {message[:80]}...")

        except Exception as e:
            logger.error(f"Follow-up check failed: {e}", exc_info=True)

    def _handle_shutdown(self, signum, frame):
        """Handle Ctrl+C gracefully."""
        logger.info("\n🛑 Shutdown signal received")
        self.stop()
