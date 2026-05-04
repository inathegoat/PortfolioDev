"""plugins/gmail_plugin.py — Gmail/email plugin via SMTP/IMAP.

Send and read emails. Requires credentials in .env:
  GMAIL_EMAIL=user@gmail.com
  GMAIL_APP_PASSWORD=xxxx  (App Password, not your real password)

All send actions require user confirmation (restricted).
"""
import logging
import os
import smtplib
import email.message
from src.tools.base import BaseTool, PERMISSION_RESTRICTED, PERMISSION_READ_ONLY

logger = logging.getLogger(__name__)


class SendEmailTool(BaseTool):
    name = "send_email"
    description = "Envoyer un email via Gmail SMTP. Nécessite confirmation."
    permission_level = PERMISSION_RESTRICTED

    def schema(self) -> dict:
        return {
            "to": {"type": "string", "required": True, "description": "Destinataire"},
            "subject": {"type": "string", "required": True, "description": "Sujet"},
            "body": {"type": "string", "required": True, "description": "Corps du message"},
        }

    def execute(self, to: str = "", subject: str = "", body: str = "", **kwargs) -> dict:
        gmail_user = os.getenv("GMAIL_EMAIL", "")
        gmail_pass = os.getenv("GMAIL_APP_PASSWORD", "")

        if not gmail_user or not gmail_pass:
            return {"status": "error", "message": "GMAIL_EMAIL et GMAIL_APP_PASSWORD doivent être définis dans .env"}

        if not to or not subject:
            return {"status": "error", "message": "Destinataire et sujet requis."}

        try:
            msg = email.message.EmailMessage()
            msg["From"] = gmail_user
            msg["To"] = to
            msg["Subject"] = subject
            msg.set_content(body)

            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(gmail_user, gmail_pass)
                server.send_message(msg)

            return {"status": "success", "message": f"Email envoyé à {to}", "details": f"Sujet: {subject}"}
        except Exception as e:
            logger.error(f"Send email failed: {e}")
            return {"status": "error", "message": str(e)}


class ReadEmailsTool(BaseTool):
    name = "read_emails"
    description = "Lire les derniers emails non lus de la boîte Gmail."
    permission_level = PERMISSION_READ_ONLY

    def schema(self) -> dict:
        return {
            "max_results": {"type": "int", "required": False, "description": "Nombre max d'emails", "default": 5},
        }

    def execute(self, max_results: int = 5, **kwargs) -> dict:
        gmail_user = os.getenv("GMAIL_EMAIL", "")
        gmail_pass = os.getenv("GMAIL_APP_PASSWORD", "")

        if not gmail_user or not gmail_pass:
            return {"status": "error", "message": "GMAIL_EMAIL et GMAIL_APP_PASSWORD non configurés."}

        try:
            import imaplib
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(gmail_user, gmail_pass)
            mail.select("inbox")

            status, messages = mail.search(None, "UNSEEN")
            if status != "OK" or not messages[0]:
                return {"status": "success", "message": "Aucun email non lu.", "emails": []}

            email_ids = messages[0].split()[-max_results:]
            emails = []
            for eid in email_ids:
                status, data = mail.fetch(eid, "(RFC822)")
                if status == "OK":
                    msg = email.message_from_bytes(data[0][1])
                    emails.append({
                        "from": msg["From"],
                        "subject": msg["Subject"] or "(sans sujet)",
                        "date": msg["Date"],
                    })

            mail.close()
            mail.logout()
            return {"status": "success", "message": f"{len(emails)} email(s) non lu(s).", "emails": emails}
        except Exception as e:
            logger.error(f"Read emails failed: {e}")
            return {"status": "error", "message": str(e)}
