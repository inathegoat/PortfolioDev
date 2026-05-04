"""plugins/calendar_plugin.py — Calendar plugin (local ICS + Apple Calendar).

Read/write calendar events. macOS: uses AppleScript for system Calendar.
Cross-platform: uses .ics file in data/.
"""
import logging
import os
import subprocess
import platform
from datetime import datetime
from pathlib import Path
from src.tools.base import BaseTool, PERMISSION_SAFE_WRITE, PERMISSION_READ_ONLY

logger = logging.getLogger(__name__)


class CalendarTool(BaseTool):
    name = "calendar"
    description = "Lire ou ajouter des événements au calendrier."
    permission_level = PERMISSION_SAFE_WRITE

    def schema(self) -> dict:
        return {
            "action": {"type": "string", "required": True, "description": "list ou add"},
            "title": {"type": "string", "required": False, "description": "Titre de l'événement (si add)"},
            "date": {"type": "string", "required": False, "description": "Date YYYY-MM-DD (si add)"},
            "time": {"type": "string", "required": False, "description": "Heure HH:MM (si add)"},
        }

    def execute(self, action: str = "list", title: str = "", date: str = "",
                time: str = "", **kwargs) -> dict:
        if action == "list":
            return self._list_events()
        elif action == "add":
            return self._add_event(title, date, time)
        return {"status": "error", "message": f"Action inconnue: {action}. Utilisez 'list' ou 'add'."}

    def _list_events(self) -> dict:
        if platform.system() == "Darwin":
            return self._list_macos()
        return self._list_ics()

    def _list_macos(self) -> dict:
        try:
            script = """
            tell application "Calendar"
                set todayStart to (current date) - (time of (current date))
                set todayEnd to todayStart + 24 * hours
                set eventList to {}
                repeat with cal in calendars
                    set evs to (every event of cal whose start date ≥ todayStart and start date < todayEnd)
                    repeat with ev in evs
                        set end of eventList to summary of ev & " | " & start date of ev
                    end repeat
                end repeat
                return eventList as string
            end tell
            """
            result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
            events = [e.strip() for e in result.stdout.strip().split(", ") if e.strip()]
            return {"status": "success", "message": f"{len(events)} événement(s) aujourd'hui.", "events": events}
        except Exception as e:
            logger.warning(f"macOS calendar failed: {e}")
            return {"status": "error", "message": str(e)}

    def _list_ics(self) -> dict:
        ics_path = Path("data/calendar.ics")
        if not ics_path.exists():
            return {"status": "success", "message": "Aucun événement.", "events": []}
        content = ics_path.read_text()
        events = []
        for line in content.split("\n"):
            if line.startswith("SUMMARY:"):
                events.append(line.replace("SUMMARY:", "").strip())
        return {"status": "success", "message": f"{len(events)} événement(s).", "events": events}

    def _add_event(self, title: str, date: str, time: str) -> dict:
        if not title:
            return {"status": "error", "message": "Titre requis pour ajouter un événement."}

        if platform.system() == "Darwin":
            return self._add_macos(title, date, time)

        # Fallback: write to ICS file
        ics_path = Path("data/calendar.ics")
        dt = f"{date}T{time}:00" if date and time else datetime.now().strftime("%Y%m%dT%H%M%S")
        entry = f"\nBEGIN:VEVENT\nSUMMARY:{title}\nDTSTART:{dt}\nEND:VEVENT\n"
        if not ics_path.exists():
            ics_path.write_text("BEGIN:VCALENDAR\nVERSION:2.0\n" + entry + "END:VCALENDAR\n")
        else:
            content = ics_path.read_text()
            content = content.replace("END:VCALENDAR", entry + "END:VCALENDAR")
            ics_path.write_text(content)
        return {"status": "success", "message": f"Événement ajouté : {title}"}

    def _add_macos(self, title: str, date: str, time: str) -> dict:
        try:
            script = f"""
            tell application "Calendar"
                tell calendar "Personnel"
                    make new event with properties {{summary:"{title}", start date:date "{date} {time or '09:00'}:00"}}
                end tell
            end tell
            """
            subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
            return {"status": "success", "message": f"Événement ajouté : {title}"}
        except Exception as e:
            # Fallback to ICS
            return self._add_event(title, date, time)
