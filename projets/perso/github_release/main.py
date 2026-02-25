"""
main.py - Point d'entrée de l'application.
Initialise tous les modules et démarre la boucle d'événements asynchrone.
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path

# S'assurer que la racine du projet est dans le path
sys.path.insert(0, str(Path(__file__).parent))

from core.config import get_config
from core.logger import setup_logging, TradeLogger, FundingLogger
from localization.translator import get_translator
from wallet.wallet_manager import WalletManager
from dashboard.dashboard_builder import DashboardBuilder
from modules.hyperliquid_api import HyperliquidAPI
from modules.funding_analyzer import FundingAnalyzerManager
from modules.position_manager import PositionManager
from modules.risk_manager import RiskManager
from modules.execution_engine import ExecutionEngine
from modules.telegram_bot import TelegramBot
from strategies.delta_neutral import DeltaNeutralStrategy


logger = logging.getLogger(__name__)


async def main():
    # ── Configuration & Logging ──────────────────────────────────────────────
    cfg = get_config("config.json")
    setup_logging(
        log_dir=cfg.get("logging", "log_dir", default="logs"),
        level=cfg.get("logging", "level", default="INFO"),
        console=cfg.get("logging", "console_output", default=True),
    )

    # ── Traduction ───────────────────────────────────────────────────────────
    translator = get_translator("fr")

    logger.info("=" * 60)
    logger.info("  Bot Delta Neutre Funding — Démarrage")
    logger.info("=" * 60)

    # ── Loggers CSV ──────────────────────────────────────────────────────────
    trade_log = TradeLogger(cfg.get("logging", "csv_export_dir", default="data"))
    funding_log = FundingLogger(cfg.get("logging", "csv_export_dir", default="data"))

    # ── Client API Hyperliquid ───────────────────────────────────────────────
    hl_cfg = cfg.get("hyperliquid") or {}
    private_key = hl_cfg.get("private_key", "")
    account = hl_cfg.get("account", "")

    if private_key:
        try:
            from eth_account import Account
            wallet = Account.from_key(private_key)
            if not account:
                account = wallet.address
            logger.info(f"🔑 Signer EVM configuré — Compte : {account}")
        except Exception as e:
            logger.error(f"❌ Erreur configuration signer EVM : {e}")
            logger.warning("Le bot démarrera en mode lecture seule (pas d'ordres)")
    else:
        logger.warning("⚠️ Aucune clé privée configurée — mode lecture seule")

    api = HyperliquidAPI(
        account=account,
        private_key=private_key,
        base_url=hl_cfg.get("api_url", "https://api.hyperliquid.xyz"),
        testnet=hl_cfg.get("testnet", False),
    )

    # ── Modules principaux ───────────────────────────────────────────────────
    pairs = cfg.get("strategy", "pairs", default=["BTC", "ETH"])
    ma_period = cfg.get("strategy", "funding_ma_period", default=24)

    funding_mgr = FundingAnalyzerManager(pairs, ma_period)
    position_mgr = PositionManager()
    risk_mgr = RiskManager(cfg)

    execution = ExecutionEngine(api, position_mgr, risk_mgr, cfg, trade_log)

    # ── Wallet interne ───────────────────────────────────────────────────────
    wallet_state_file = cfg.get("wallet", "state_file", default="data/wallet_state.json")
    wallet_initial = cfg.get("wallet", "initial_capital",
                             default=cfg.get("strategy", "total_capital_usdt", default=10000.0))

    # Récupérer le solde réel depuis l'API si un compte est configuré
    if account:
        try:
            acct_data = await api.get_account()
            real_balance = float(acct_data.get("account_equity", 0) or
                                 acct_data.get("balance", 0))
            if real_balance > 0:
                wallet_initial = real_balance
                logger.info(f"💰 Solde réel récupéré depuis Hyperliquid : ${real_balance:.2f}")
            else:
                logger.warning(f"⚠️ Solde API = $0 — utilisation du capital config : ${wallet_initial:.2f}")
        except Exception as e:
            logger.warning(f"⚠️ Impossible de récupérer le solde API : {e}")
            logger.info(f"Utilisation du capital configuré : ${wallet_initial:.2f}")

    wallet_mgr = WalletManager(
        state_file=wallet_state_file,
        initial_capital=wallet_initial,
    )
    logger.info(f"Portefeuille initialisé : capital=${wallet_mgr.total_capital:.2f}")

    # ── Stratégie ────────────────────────────────────────────────────────────
    strategy = DeltaNeutralStrategy(
        api, funding_mgr, position_mgr,
        execution, risk_mgr, cfg, funding_log,
        wallet_mgr=wallet_mgr, translator=translator
    )

    # ── Dashboard ────────────────────────────────────────────────────────────
    dashboard = DashboardBuilder(
        config=cfg,
        wallet_mgr=wallet_mgr,
        position_mgr=position_mgr,
        risk_mgr=risk_mgr,
        funding_mgr=funding_mgr,
        translator=translator,
    )

    # ── Bot Telegram ─────────────────────────────────────────────────────────
    tg_bot = TelegramBot(
        config=cfg,
        strategy=strategy,
        position_mgr=position_mgr,
        risk_mgr=risk_mgr,
        funding_mgr=funding_mgr,
        execution_engine=execution,
        wallet_mgr=wallet_mgr,
        translator=translator,
        dashboard_builder=dashboard,
    )

    # Relier les alertes stratégie → Telegram
    async def alert_handler(msg: str):
        await tg_bot.send_alert(msg)

    strategy.add_alert_callback(alert_handler)

    # ── Arrêt gracieux ───────────────────────────────────────────────────────
    shutdown_event = asyncio.Event()

    def _signal_handler():
        logger.info(translator.t("bot.shutdown_signal"))
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    # ── Démarrage des services ───────────────────────────────────────────────
    logger.info(translator.t("bot.telegram_starting"))
    await tg_bot.run()

    if cfg.get("strategy", "active", default=True):
        logger.info(translator.t("bot.strategy_auto_start"))
        strategy.start()

    logger.info(translator.t("bot.online"))
    await shutdown_event.wait()

    # ── Nettoyage ────────────────────────────────────────────────────────────
    logger.info(translator.t("bot.shutting_down"))
    strategy.stop()
    await tg_bot.stop()
    await api.close()
    logger.info(translator.t("bot.shutdown_complete"))


if __name__ == "__main__":
    asyncio.run(main())
