"""
Second Brain — Telegram Bot Interface
=====================================
Allows secure, mobile access to the Second Brain via Telegram.
"""

import sys
import time
import logging
from pathlib import Path
import telebot

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USERS
from src.ai.llm_client import LLMClient
from src.memory.history import load_memory, add_interaction
from src.goals import load_goals
from src.agent.attention import rank_memories

logger = logging.getLogger("telegram_bot")

def start_telegram_bot():
    """Starts the Telegram Bot listener."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set in .env")
        print("❌ Erreur: TELEGRAM_BOT_TOKEN n'est pas défini dans le fichier .env")
        return
        
    allowed_users = []
    if TELEGRAM_ALLOWED_USERS:
        allowed_users = [u.strip().replace('@', '') for u in TELEGRAM_ALLOWED_USERS.split(',')]
    
    if not allowed_users:
        logger.warning("TELEGRAM_ALLOWED_USERS is empty — Telegram access is DISABLED (deny-by-default)")
        print("⚠️  TELEGRAM_ALLOWED_USERS is empty. Telegram access is disabled.")
        print("   Add usernames/IDs to .env to enable: TELEGRAM_ALLOWED_USERS=user1,user2")
        return
        
    bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
    llm = LLMClient()
    
    def is_authorized(message):
        username = message.from_user.username
        user_id = str(message.from_user.id)
        if username in allowed_users or user_id in allowed_users:
            return True
        logger.warning(f"Unauthorized access attempt: username={username}, id={user_id}")
        return False

    @bot.message_handler(commands=['start', 'help'])
    def send_welcome(message):
        if not is_authorized(message):
            bot.reply_to(message, "⛔️ Accès refusé. Vous n'êtes pas autorisé à utiliser ce Second Brain.")
            return
            
        welcome_text = (
            "🧠 **Second Brain Mobile**\\n\\n"
            "Bonjour ! Je suis connecté à votre base de connaissances locale.\\n"
            "Posez-moi n'importe quelle question sur vos documents ou vos projets."
        )
        bot.reply_to(message, welcome_text, parse_mode='Markdown')

    @bot.message_handler(func=lambda message: True)
    def echo_all(message):
        if not is_authorized(message):
            bot.reply_to(message, "⛔️ Accès refusé. Vous n'êtes pas autorisé à utiliser ce Second Brain.")
            return
            
        question = message.text
        
        # Send typing action
        bot.send_chat_action(message.chat.id, 'typing')
        
        try:
            memories = load_memory()
            goals = load_goals()
            
            # Context
            ranked = rank_memories(memories, goals)
            context_text = "\\n".join([f"- {m.get('question', '')} : {m.get('answer', '')}" for m in ranked[:3]])
            
            recent_history = ""
            if len(memories) > 0:
                recent = memories[-4:]
                recent_history = "\\n\\n[HISTORIQUE RÉCENT]\\n"
                recent_history += "\\n".join([f"User: {m.get('question', '')}\\nAI: {m.get('answer', '')}" for m in recent])
            
            # Initialize tools
            from src.tools import init_all_tools
            init_all_tools()
            
            # Check if we should use a tool (Plugin / Built-in)
            tool_context = ""
            from src.tools.llm_router import route_query
            from src.tools.registry import execute_tool
            
            route_result = route_query(question, context_text, llm=llm)
            if route_result and route_result.get("tool"):
                tool_name = route_result["tool"]
                tool_args = route_result.get("args", {})
                logger.info(f"LLM decided to use tool '{tool_name}' with args {tool_args}")
                try:
                    exec_res = execute_tool(tool_name, tool_args, confirm_fn=lambda x: True)
                    if exec_res.get("status") == "success":
                        tool_context = f"\\n\\n[RÉSULTAT DE L'OUTIL '{tool_name}']\\n{exec_res.get('message', '')}\\n{exec_res.get('details', '')}"
                    else:
                        tool_context = f"\\n\\n[ERREUR DE L'OUTIL '{tool_name}']\\n{exec_res.get('message', '')}"
                except Exception as e:
                    logger.error(f"Error executing tool {tool_name}: {e}")
                    tool_context = f"\\n\\n[ERREUR DE L'OUTIL '{tool_name}']\\n{e}"
            
            system_prompt = f"""
            Tu es un assistant IA local, tu communiques avec l'utilisateur via Telegram (mobile).
            RÈGLES :
            1. Sois très direct et concis (les messages Telegram doivent être courts).
            2. Utilise du formatage simple (*gras*, _italique_).
            3. Réponds en français.
            
            Contexte issu du Second Brain :
            {context_text}{recent_history}{tool_context}
            """
            
            answer = llm.generate(prompt=question, system_prompt=system_prompt)
            
            # Save interaction
            add_interaction(question, answer)
            
            # Reply
            bot.reply_to(message, answer)
            
        except Exception as e:
            logger.error(f"Telegram processing error: {e}")
            bot.reply_to(message, f"❌ Erreur lors de la génération: {e}")

    logger.info("Starting Telegram Bot Polling...")
    print("✅ Telegram Bot connecté et en écoute...")
    
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            logger.error(f"Bot polling crashed: {e}")
            time.sleep(5)

if __name__ == "__main__":
    start_telegram_bot()
