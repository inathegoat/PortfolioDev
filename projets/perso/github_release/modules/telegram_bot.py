"""
modules/telegram_bot.py - Interface de contrôle Telegram complète.
Tous les paramètres de stratégie modifiables sans redémarrage.
Entièrement en français pour l'utilisateur.
"""

import asyncio
import logging
from datetime import datetime
from functools import wraps
from typing import Optional

from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
import telegram.error
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)

logger = logging.getLogger(__name__)


def admin_only(func):
    """Décorateur : restreindre les commandes aux admins autorisés."""
    @wraps(func)
    async def wrapper(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        cid = update.effective_chat.id
        if cid not in self._admin_ids:
            await update.message.reply_text(self._t.t("bot.unauthorized"))
            return
        return await func(self, update, ctx)
    return wrapper


def safe_reply(func):
    """Décorateur : capturer les exceptions et répondre avec l'erreur."""
    @wraps(func)
    async def wrapper(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        try:
            return await func(self, update, ctx)
        except Exception as e:
            logger.exception(f"Erreur commande {func.__name__}: {e}")
            await update.message.reply_text(self._t.t("bot.error", error=str(e)))
    return wrapper


class TelegramBot:
    """
    Interface de contrôle Telegram complète pour le Bot Delta Neutre.
    Intègre stratégie, positions, risque, wallet et dashboard.
    """

    def __init__(self, config, strategy, position_mgr,
                 risk_mgr, funding_mgr, execution_engine,
                 wallet_mgr=None, translator=None, dashboard_builder=None):
        self._cfg = config
        self._strategy = strategy
        self._pos = position_mgr
        self._risk = risk_mgr
        self._funding = funding_mgr
        self._exec = execution_engine
        self._wallet = wallet_mgr
        self._t = translator
        self._dashboard = dashboard_builder
        self._admin_ids: set = set(config.get("telegram", "admin_chat_ids") or [])
        self._app: Optional[Application] = None
        self._start_time = datetime.utcnow()
        self._pending_input: dict = {}  # {chat_id: {"param": ..., "msg_id": ...}}

    # ── Setup ────────────────────────────────────────────────────────────────

    async def setup(self):
        token = self._cfg.get("telegram", "token")
        self._app = Application.builder().token(token).build()
        self._register_handlers()
        await self._set_commands()
        logger.info(self._t.t("bot.telegram_init") if self._t else "Telegram bot initialized")

    def _register_handlers(self):
        cmds = [
            ("start", self.cmd_start),
            ("stop", self.cmd_stop),
            ("status", self.cmd_status),
            ("pnl", self.cmd_pnl),
            ("positions", self.cmd_positions),
            ("funding", self.cmd_funding),
            ("wallet", self.cmd_wallet),
            ("set_threshold", self.cmd_set_threshold),
            ("set_leverage", self.cmd_set_leverage),
            ("set_max_delta", self.cmd_set_max_delta),
            ("set_capital", self.cmd_set_capital),
            ("add_funds", self.cmd_add_funds),
            ("remove_funds", self.cmd_remove_funds),
            ("set_pairs", self.cmd_set_pairs),
            ("enable_pair", self.cmd_enable_pair),
            ("disable_pair", self.cmd_disable_pair),
            ("set_k", self.cmd_set_k),
            ("set_poll_interval", self.cmd_set_poll_interval),
            ("close_all", self.cmd_close_all),
            ("emergency_stop", self.cmd_emergency_stop),
            ("reset_circuit", self.cmd_reset_circuit),
            ("risk_status", self.cmd_risk_status),
            ("help", self.cmd_help),
        ]
        for name, handler in cmds:
            self._app.add_handler(CommandHandler(name, handler))
        # Callback pour les boutons inline
        self._app.add_handler(CallbackQueryHandler(self._button_callback))
        # Handler pour les saisies texte (paramètres)
        self._app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, self._handle_text_input
        ))

    async def _set_commands(self):
        t = self._t
        commands = [
            BotCommand("start", t.t("commands.start")),
            BotCommand("stop", t.t("commands.stop")),
            BotCommand("status", t.t("commands.status")),
            BotCommand("pnl", t.t("commands.pnl")),
            BotCommand("positions", t.t("commands.positions")),
            BotCommand("funding", t.t("commands.funding")),
            BotCommand("wallet", t.t("commands.wallet")),
            BotCommand("set_threshold", t.t("commands.set_threshold")),
            BotCommand("set_leverage", t.t("commands.set_leverage")),
            BotCommand("set_max_delta", t.t("commands.set_max_delta")),
            BotCommand("set_capital", t.t("commands.set_capital")),
            BotCommand("add_funds", t.t("commands.add_funds")),
            BotCommand("remove_funds", t.t("commands.remove_funds")),
            BotCommand("set_pairs", t.t("commands.set_pairs")),
            BotCommand("enable_pair", t.t("commands.enable_pair")),
            BotCommand("disable_pair", t.t("commands.disable_pair")),
            BotCommand("set_k", t.t("commands.set_k")),
            BotCommand("set_poll_interval", t.t("commands.set_poll_interval")),
            BotCommand("close_all", t.t("commands.close_all")),
            BotCommand("emergency_stop", t.t("commands.emergency_stop")),
            BotCommand("reset_circuit", t.t("commands.reset_circuit")),
            BotCommand("risk_status", t.t("commands.risk_status")),
            BotCommand("help", t.t("commands.help")),
        ]
        await self._app.bot.set_my_commands(commands)

    # ── Run ──────────────────────────────────────────────────────────────────

    async def run(self):
        await self.setup()
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)
        logger.info(self._t.t("bot.telegram_polling") if self._t else "Telegram bot polling started")

    async def stop(self):
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()

    async def send_alert(self, message: str):
        """Envoyer une alerte à tous les admins (si notifications activées)."""
        if not self._cfg.get("telegram", "trade_notifications", default=True):
            return
        for cid in self._admin_ids:
            try:
                await self._app.bot.send_message(
                    chat_id=cid, text=message, parse_mode="HTML"
                )
            except Exception as e:
                logger.warning(f"Échec envoi alerte à {cid}: {e}")

    # ── Commandes principales ────────────────────────────────────────────────

    @admin_only
    @safe_reply
    async def cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Démarrer la stratégie et afficher le dashboard."""
        self._cfg.set("strategy", "active", True)
        self._strategy.start()

        # Afficher le dashboard complet avec boutons
        if self._dashboard:
            dashboard = await self._dashboard.build()
            await update.message.reply_text(
                dashboard, parse_mode="HTML",
                reply_markup=self._build_keyboard()
            )
        else:
            await update.message.reply_text(
                self._t.t("bot.started"), parse_mode="HTML",
                reply_markup=self._build_keyboard()
            )

    @admin_only
    @safe_reply
    async def cmd_stop(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        self._cfg.set("strategy", "active", False)
        self._strategy.stop()
        await update.message.reply_text(self._t.t("bot.stopped"), parse_mode="HTML")

    @admin_only
    @safe_reply
    async def cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Afficher le dashboard complet (rafraîchissable)."""
        if self._dashboard:
            dashboard = await self._dashboard.build()
            await update.message.reply_text(
                dashboard, parse_mode="HTML",
                reply_markup=self._build_keyboard()
            )
        else:
            # Fallback si pas de dashboard
            await self._cmd_status_fallback(update)

    async def _cmd_status_fallback(self, update: Update):
        """Fallback status si le dashboard n'est pas configuré."""
        t = self._t
        uptime = datetime.utcnow() - self._start_time
        strat = self._cfg.strategy
        risk_st = self._risk.status()
        total_pnl = await self._pos.total_pnl()
        funding = await self._pos.total_funding_collected()
        exposure = await self._pos.total_exposure()

        is_active = strat.get("active", False)
        status = t.t("dashboard.statut_actif") if is_active else t.t("dashboard.statut_pause")
        circuit = t.t("dashboard.circuit_on") if risk_st["circuit_open"] else t.t("dashboard.circuit_off")

        sep = t.t("dashboard.separator")
        msg = (
            f"🤖 <b>Bot Delta Neutre</b>\n{sep}\n"
            f"⏱ Uptime : {str(uptime).split('.')[0]}\n"
            f"📍 Stratégie : {status}\n"
            f"⚡ Circuit : {circuit}\n{sep}\n"
            f"💰 PnL total : <b>${total_pnl:.4f}</b>\n"
            f"💸 Funding collecté : <b>${funding:.4f}</b>\n"
            f"📊 Exposition brute : <b>${exposure:.2f}</b>\n{sep}\n"
            f"⚙️ Configuration\n"
            f"  Paires : {', '.join(strat.get('enabled_pairs', []))}\n"
            f"  Capital : ${strat.get('total_capital_usdt', 0):.0f}\n"
            f"  Levier : {strat.get('default_leverage', 1)}x\n"
            f"  Seuil : {strat.get('funding_threshold', 0)*100:.4f}%\n"
            f"  Z-score k : {strat.get('funding_zscore_k', 1.5)}\n"
            f"  Max delta : {strat.get('rebalance_delta_threshold', 0.02)*100:.1f}%"
        )
        await update.message.reply_text(msg, parse_mode="HTML")

    # ── Commandes Wallet ─────────────────────────────────────────────────────

    @admin_only
    @safe_reply
    async def cmd_wallet(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Afficher l'état complet du portefeuille."""
        t = self._t
        if not self._wallet:
            await update.message.reply_text("❌ Module wallet non configuré.")
            return

        w = self._wallet.snapshot()
        exposure = await self._pos.total_exposure()
        avg_lev = self._wallet.get_average_leverage(exposure)
        sep = t.t("dashboard.separator")

        lines = [
            t.t("wallet.title"),
            sep,
            t.t("wallet.capital_initial", amount=w["initial_capital"]),
            t.t("wallet.capital_total", amount=w["total_capital"]),
            t.t("wallet.capital_engaged", amount=w["committed_capital"]),
            t.t("wallet.capital_available", amount=w["available_capital"]),
            sep,
            t.t("wallet.funding_cumule", amount=w["accumulated_funding"]),
            t.t("wallet.pnl_realise", amount=w["realized_pnl"]),
            t.t("wallet.pnl_non_realise", amount=w["unrealized_pnl"]),
            t.t("wallet.roi", pct=w["roi_pct"]),
            sep,
            t.t("wallet.exposition_totale", amount=exposure),
            t.t("wallet.levier_moyen", lev=avg_lev),
        ]

        # Allocations par paire
        allocs = w.get("allocations", {})
        if allocs:
            lines.append(sep)
            lines.append(t.t("wallet.par_paire"))
            for pair, amount in allocs.items():
                lines.append(t.t("wallet.pair_line", pair=pair, amount=amount))
        else:
            lines.append(t.t("wallet.no_pairs"))

        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    @admin_only
    @safe_reply
    async def cmd_set_capital(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Définir le capital initial."""
        val = self._parse_float(ctx.args, "capital")
        if self._wallet:
            await self._wallet.set_capital(val)
            await update.message.reply_text(
                self._t.t("wallet.set_capital_ok", amount=val), parse_mode="HTML"
            )
        else:
            self._cfg.set("strategy", "total_capital_usdt", val)
            await update.message.reply_text(
                self._t.t("config_cmds.capital_set", amount=val)
            )

    @admin_only
    @safe_reply
    async def cmd_add_funds(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Ajouter des fonds au portefeuille."""
        val = self._parse_float(ctx.args, "montant")
        if not self._wallet:
            await update.message.reply_text("❌ Module wallet non configuré.")
            return
        await self._wallet.add_funds(val)
        await update.message.reply_text(
            self._t.t("wallet.add_funds_ok", amount=val,
                       total=self._wallet.total_capital),
            parse_mode="HTML"
        )

    @admin_only
    @safe_reply
    async def cmd_remove_funds(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Retirer des fonds du portefeuille."""
        val = self._parse_float(ctx.args, "montant")
        if not self._wallet:
            await update.message.reply_text("❌ Module wallet non configuré.")
            return
        success = await self._wallet.remove_funds(val)
        if success:
            await update.message.reply_text(
                self._t.t("wallet.remove_funds_ok", amount=val,
                           total=self._wallet.total_capital),
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text(
                self._t.t("wallet.remove_funds_fail",
                           available=self._wallet.available_capital)
            )

    # ── Commandes Info ───────────────────────────────────────────────────────

    @admin_only
    @safe_reply
    async def cmd_pnl(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        t = self._t
        summaries = await self._pos.all_summaries()
        if not summaries:
            await update.message.reply_text(t.t("pnl.no_positions"))
            return

        total_pnl = await self._pos.total_pnl()
        total_funding = await self._pos.total_funding_collected()
        total_cap = self._wallet.total_capital if self._wallet else \
            self._cfg.get("strategy", "total_capital_usdt", default=1)

        sep = t.t("dashboard.separator")
        lines = [f"{t.t('pnl.title')}\n{sep}"]
        for s in summaries:
            lines.append(t.t("pnl.pair_line",
                             pair=s["pair"], pnl=s["total_pnl"],
                             roi=s["roi_pct"], funding=s["funding_collected"]))

        roi = total_pnl / total_cap * 100 if total_cap > 0 else 0
        lines.append(
            f"{sep}\n"
            f"{t.t('pnl.total_pnl', amount=total_pnl)}\n"
            f"{t.t('pnl.total_funding', amount=total_funding)}\n"
            f"{t.t('pnl.portfolio_roi', pct=roi)}"
        )
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    @admin_only
    @safe_reply
    async def cmd_positions(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        t = self._t
        summaries = await self._pos.all_summaries()
        if not summaries:
            await update.message.reply_text(t.t("positions.no_positions"))
            return

        sep = t.t("dashboard.separator")
        lines = [f"{t.t('positions.title')}\n{sep}"]
        for s in summaries:
            liq_flag = "🚨" if s.get("near_liquidation") else ""
            lines.append(
                f"{liq_flag}<b>{s['pair']}</b>  {'🟢' if s['active'] else '⚪'}\n"
                f"  Spot : {s['spot_size']} | Short perp : {abs(float(s['perp_size'])):.6f}\n"
                f"  Delta : {s['net_delta']:.6f} ({s['delta_ratio_pct']})\n"
                f"  Exposition : ${s['gross_exposure']:.2f}\n"
                f"  PnL : ${s['total_pnl']} | ROI : {s['roi_pct']}"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    @admin_only
    @safe_reply
    async def cmd_funding(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        t = self._t
        summaries = self._funding.all_summaries()
        if not summaries:
            await update.message.reply_text(t.t("funding_msg.no_data"))
            return

        sep = t.t("dashboard.separator")
        lines = [f"{t.t('funding_msg.title')}\n{sep}"]
        for s in summaries:
            lines.append(t.t("funding_msg.pair_line",
                             pair=s["pair"], rate=s["rate_pct"],
                             ma=f"{float(s['ma'])*100:.4f}%",
                             zscore=s["z_score"], ann=s["annualized_pct"]))
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    # ── Commandes Configuration ──────────────────────────────────────────────

    @admin_only
    @safe_reply
    async def cmd_set_threshold(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        val = self._parse_float(ctx.args, "seuil")
        self._cfg.set("strategy", "funding_threshold", val)
        await update.message.reply_text(
            self._t.t("config_cmds.threshold_set", pct=val * 100)
        )

    @admin_only
    @safe_reply
    async def cmd_set_leverage(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        val = self._parse_float(ctx.args, "levier")
        val = await self._risk.check_leverage(val)
        self._cfg.set("strategy", "default_leverage", val)
        await update.message.reply_text(
            self._t.t("config_cmds.leverage_set", lev=val)
        )

    @admin_only
    @safe_reply
    async def cmd_set_max_delta(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        val = self._parse_float(ctx.args, "max_delta")
        self._cfg.set("strategy", "rebalance_delta_threshold", val)
        await update.message.reply_text(
            self._t.t("config_cmds.max_delta_set", pct=val * 100)
        )

    @admin_only
    @safe_reply
    async def cmd_set_pairs(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not ctx.args:
            await update.message.reply_text(
                self._t.t("config_cmds.usage_pairs")
            )
            return
        pairs = [p.strip().upper() for p in ctx.args[0].split(",")]
        self._cfg.set("strategy", "pairs", pairs)
        self._cfg.set("strategy", "enabled_pairs", pairs)
        await update.message.reply_text(
            self._t.t("config_cmds.pairs_set", pairs=", ".join(pairs))
        )

    @admin_only
    @safe_reply
    async def cmd_enable_pair(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not ctx.args:
            await update.message.reply_text(
                self._t.t("config_cmds.usage_enable")
            )
            return
        pair = ctx.args[0].upper()
        enabled = list(self._cfg.get("strategy", "enabled_pairs") or [])
        if pair not in enabled:
            enabled.append(pair)
            self._cfg.set("strategy", "enabled_pairs", enabled)
        await update.message.reply_text(
            self._t.t("config_cmds.pair_enabled", pair=pair, all=", ".join(enabled))
        )

    @admin_only
    @safe_reply
    async def cmd_disable_pair(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not ctx.args:
            await update.message.reply_text(
                self._t.t("config_cmds.usage_disable")
            )
            return
        pair = ctx.args[0].upper()
        enabled = [p for p in (self._cfg.get("strategy", "enabled_pairs") or [])
                   if p != pair]
        self._cfg.set("strategy", "enabled_pairs", enabled)
        await update.message.reply_text(
            self._t.t("config_cmds.pair_disabled", pair=pair, all=", ".join(enabled))
        )

    @admin_only
    @safe_reply
    async def cmd_set_k(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        val = self._parse_float(ctx.args, "k")
        self._cfg.set("strategy", "funding_zscore_k", val)
        await update.message.reply_text(
            self._t.t("config_cmds.k_set", k=val)
        )

    @admin_only
    @safe_reply
    async def cmd_set_poll_interval(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        val = int(self._parse_float(ctx.args, "intervalle"))
        self._cfg.set("strategy", "funding_poll_interval_seconds", val)
        await update.message.reply_text(
            self._t.t("config_cmds.poll_set", val=val)
        )

    # ── Commandes Urgence ────────────────────────────────────────────────────

    @admin_only
    @safe_reply
    async def cmd_close_all(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        t = self._t
        await update.message.reply_text(t.t("execution.closing_all"))
        summaries = await self._pos.all_summaries()
        closed, failed = 0, 0
        for s in summaries:
            if s.get("active"):
                r = await self._exec.close_delta_neutral(s["pair"])
                if r.success:
                    closed += 1
                    # Libérer le capital dans le wallet
                    if self._wallet:
                        await self._wallet.release(s["pair"], pnl=float(s.get("total_pnl", 0)))
                else:
                    failed += 1
        await update.message.reply_text(
            t.t("execution.closed_result", closed=closed, failed=failed)
        )

    @admin_only
    @safe_reply
    async def cmd_emergency_stop(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        t = self._t
        await update.message.reply_text(
            t.t("execution.emergency_activated"), parse_mode="HTML"
        )
        self._strategy.stop()
        self._cfg.set("strategy", "active", False)
        await self._risk.trip_circuit_breaker("Arrêt d'urgence manuel via Telegram")

        summaries = await self._pos.all_summaries()
        for s in summaries:
            if s.get("active"):
                await self._exec.close_delta_neutral(s["pair"])
                if self._wallet:
                    await self._wallet.release(s["pair"], pnl=float(s.get("total_pnl", 0)))

        await update.message.reply_text(t.t("execution.emergency_done"))

    @admin_only
    @safe_reply
    async def cmd_reset_circuit(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await self._risk.reset_circuit_breaker()
        await update.message.reply_text(self._t.t("risk.circuit_reset"))

    @admin_only
    @safe_reply
    async def cmd_risk_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        t = self._t
        st = self._risk.status()
        r = self._cfg.risk
        sep = t.t("dashboard.separator")

        circuit_status = t.t("risk.circuit_open") if st["circuit_open"] else t.t("risk.circuit_closed")

        msg = (
            f"{t.t('risk.title')}\n{sep}\n"
            f"{t.t('risk.circuit', status=circuit_status)}\n"
            f"{t.t('risk.raison', reason=st.get('circuit_reason', 'N/A'))}\n"
            f"{t.t('risk.equite', amount=st['current_equity'])}\n"
            f"{t.t('risk.pic', amount=st['peak_equity'])}\n"
            f"{t.t('risk.drawdown', dd=st['drawdown_pct'])}\n"
            f"{t.t('risk.perte_jour', amount=st['daily_loss_usd'])}\n"
            f"{sep}\n"
            f"{t.t('risk.limites')}\n"
            f"{t.t('risk.max_dd', pct=r.get('max_drawdown_pct', 0) * 100)}\n"
            f"{t.t('risk.max_perte_jour', pct=r.get('max_daily_loss_pct', 0) * 100)}\n"
            f"{t.t('risk.max_levier', lev=r.get('max_leverage_hard', 5))}\n"
            f"{t.t('risk.max_concentration', pct=r.get('max_concentration_per_pair_pct', 0) * 100)}"
        )
        await update.message.reply_text(msg, parse_mode="HTML")

    @admin_only
    @safe_reply
    async def cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        t = self._t
        msg = (
            f"{t.t('help.title')}\n\n"
            f"{t.t('help.section_control')}\n"
            f"{t.t('help.start')}\n"
            f"{t.t('help.stop')}\n"
            f"{t.t('help.emergency')}\n"
            f"{t.t('help.close_all')}\n"
            f"{t.t('help.reset_circuit')}\n\n"
            f"{t.t('help.section_info')}\n"
            f"{t.t('help.status')}\n"
            f"{t.t('help.pnl')}\n"
            f"{t.t('help.positions')}\n"
            f"{t.t('help.funding')}\n"
            f"{t.t('help.risk_status')}\n\n"
            f"{t.t('help.section_wallet')}\n"
            f"{t.t('help.wallet_cmd')}\n"
            f"{t.t('help.add_funds')}\n"
            f"{t.t('help.remove_funds')}\n\n"
            f"{t.t('help.section_config')}\n"
            f"{t.t('help.set_threshold')}\n"
            f"{t.t('help.set_leverage')}\n"
            f"{t.t('help.set_max_delta')}\n"
            f"{t.t('help.set_capital')}\n"
            f"{t.t('help.set_k')}\n"
            f"{t.t('help.set_poll')}\n"
            f"{t.t('help.set_pairs')}\n"
            f"{t.t('help.enable_pair')}\n"
            f"{t.t('help.disable_pair')}"
        )
        await update.message.reply_text(msg, parse_mode="HTML")

    # ── Claviers Inline ────────────────────────────────────────────────────

    def _kb_main(self) -> InlineKeyboardMarkup:
        """Clavier principal du dashboard."""
        is_active = self._cfg.get("strategy", "active", default=False)
        toggle = ("⏸ Stop", "btn_stop") if is_active else ("▶️ Start", "btn_start")
        notif_on = self._cfg.get("telegram", "trade_notifications", default=True)
        notif_btn = ("🔔 Notifs ON", "btn_notif") if notif_on else ("🔕 Notifs OFF", "btn_notif")
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔄 Refresh", callback_data="btn_refresh"),
                InlineKeyboardButton("📈 PnL", callback_data="btn_pnl"),
                InlineKeyboardButton("📋 Positions", callback_data="btn_positions"),
            ],
            [
                InlineKeyboardButton("💰 Funding", callback_data="btn_funding"),
                InlineKeyboardButton("👛 Wallet", callback_data="menu_wallet"),
                InlineKeyboardButton("🛡 Risque", callback_data="btn_risk"),
            ],
            [
                InlineKeyboardButton("⚙️ Config", callback_data="menu_config"),
                InlineKeyboardButton("📊 Paires", callback_data="menu_pairs"),
                InlineKeyboardButton(toggle[0], callback_data=toggle[1]),
            ],
            [
                InlineKeyboardButton(notif_btn[0], callback_data=notif_btn[1]),
                InlineKeyboardButton("📖 Aide", callback_data="btn_help"),
                InlineKeyboardButton("🚨 Urgence", callback_data="btn_emergency"),
            ],
        ])

    def _kb_config(self) -> InlineKeyboardMarkup:
        """Sous-menu Configuration."""
        strat = self._cfg.strategy
        threshold = strat.get("funding_threshold", 0.0003) * 100
        leverage = strat.get("default_leverage", 2.0)
        max_delta = strat.get("rebalance_delta_threshold", 0.02) * 100
        k = strat.get("funding_zscore_k", 1.5)
        poll = strat.get("funding_poll_interval_seconds", 30)
        cap = self._wallet.total_capital if self._wallet else strat.get("total_capital_usdt", 0)
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(f"📉 Seuil : {threshold:.4f}%", callback_data="set_threshold")],
            [InlineKeyboardButton(f"⚡ Levier : {leverage}x", callback_data="set_leverage")],
            [InlineKeyboardButton(f"📐 Max delta : {max_delta:.1f}%", callback_data="set_max_delta")],
            [InlineKeyboardButton(f"📊 Z-score k : {k}", callback_data="set_k")],
            [InlineKeyboardButton(f"⏱ Polling : {poll}s", callback_data="set_poll")],
            [InlineKeyboardButton(f"💰 Capital : ${cap:.2f}", callback_data="set_capital")],
            [InlineKeyboardButton("🔙 Retour", callback_data="btn_refresh")],
        ])

    def _kb_wallet(self) -> InlineKeyboardMarkup:
        """Sous-menu Wallet."""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("💵 Ajouter fonds", callback_data="input_add_funds")],
            [InlineKeyboardButton("💸 Retirer fonds", callback_data="input_remove_funds")],
            [InlineKeyboardButton("🔄 Refresh", callback_data="menu_wallet")],
            [InlineKeyboardButton("🔙 Retour", callback_data="btn_refresh")],
        ])

    def _kb_pairs(self) -> InlineKeyboardMarkup:
        """Sous-menu Paires — toggle enable/disable."""
        all_pairs = self._cfg.get("strategy", "pairs", default=[])
        enabled = set(self._cfg.get("strategy", "enabled_pairs", default=[]))
        rows = []
        for pair in all_pairs:
            if pair in enabled:
                label = f"✅ {pair}"
                cb = f"disable_{pair}"
            else:
                label = f"❌ {pair}"
                cb = f"enable_{pair}"
            rows.append([InlineKeyboardButton(label, callback_data=cb)])
        rows.append([InlineKeyboardButton("🔙 Retour", callback_data="btn_refresh")])
        return InlineKeyboardMarkup(rows)

    # Alias pour la compatibilité
    def _build_keyboard(self) -> InlineKeyboardMarkup:
        return self._kb_main()

    async def _button_callback(self, update: Update,
                                ctx: ContextTypes.DEFAULT_TYPE):
        """Gérer les appuis sur les boutons inline."""
        query = update.callback_query
        await query.answer()

        cid = query.message.chat_id
        if cid not in self._admin_ids:
            await query.answer("⛔ Non autorisé.", show_alert=True)
            return

        data = query.data
        t = self._t

        try:
            # ── Navigation principale ────────────────────────────────
            if data == "btn_refresh":
                self._pending_input.pop(cid, None)
                if self._dashboard:
                    text = await self._dashboard.build()
                else:
                    text = t.t("bot.started")
                await query.edit_message_text(
                    text, parse_mode="HTML",
                    reply_markup=self._kb_main()
                )

            elif data == "btn_pnl":
                summaries = await self._pos.all_summaries()
                if not summaries:
                    await query.edit_message_text(
                        t.t("pnl.no_positions"),
                        reply_markup=self._kb_main()
                    )
                    return
                total_pnl = await self._pos.total_pnl()
                total_funding = await self._pos.total_funding_collected()
                total_cap = self._wallet.total_capital if self._wallet else \
                    self._cfg.get("strategy", "total_capital_usdt", default=1)
                sep = t.t("dashboard.separator")
                lines = [f"{t.t('pnl.title')}\n{sep}"]
                for s in summaries:
                    lines.append(t.t("pnl.pair_line",
                                     pair=s["pair"], pnl=s["total_pnl"],
                                     roi=s["roi_pct"], funding=s["funding_collected"]))
                roi = total_pnl / total_cap * 100 if total_cap > 0 else 0
                lines.append(
                    f"{sep}\n"
                    f"{t.t('pnl.total_pnl', amount=total_pnl)}\n"
                    f"{t.t('pnl.total_funding', amount=total_funding)}\n"
                    f"{t.t('pnl.portfolio_roi', pct=roi)}"
                )
                await query.edit_message_text(
                    "\n".join(lines), parse_mode="HTML",
                    reply_markup=self._kb_main()
                )

            elif data == "btn_positions":
                summaries = await self._pos.all_summaries()
                if not summaries:
                    await query.edit_message_text(
                        t.t("positions.no_positions"),
                        reply_markup=self._kb_main()
                    )
                    return
                sep = t.t("dashboard.separator")
                lines = [f"{t.t('positions.title')}\n{sep}"]
                for s in summaries:
                    liq_flag = "🚨" if s.get("near_liquidation") else ""
                    lines.append(
                        f"<b>{s['pair']}</b> {liq_flag}\n"
                        f"  Spot : {s['spot_size']} | Short perp : {abs(float(s['perp_size'])):.6f}\n"
                        f"  Delta : {s['net_delta']:.6f} ({s['delta_ratio_pct']})\n"
                        f"  Exposition : ${s['gross_exposure']:.2f}\n"
                        f"  PnL : ${s['total_pnl']} | ROI : {s['roi_pct']}"
                    )
                await query.edit_message_text(
                    "\n".join(lines), parse_mode="HTML",
                    reply_markup=self._kb_main()
                )

            elif data == "btn_funding":
                summaries = self._funding.all_summaries()
                if not summaries:
                    await query.edit_message_text(
                        t.t("funding_msg.no_data"),
                        reply_markup=self._kb_main()
                    )
                    return
                sep = t.t("dashboard.separator")
                lines = [f"{t.t('funding_msg.title')}\n{sep}"]
                for s in summaries:
                    lines.append(t.t("funding_msg.pair_line",
                                     pair=s["pair"], rate=s["rate_pct"],
                                     ma=f"{float(s['ma'])*100:.4f}%",
                                     zscore=s["z_score"], ann=s["annualized_pct"]))
                await query.edit_message_text(
                    "\n".join(lines), parse_mode="HTML",
                    reply_markup=self._kb_main()
                )

            elif data == "btn_risk":
                st = self._risk.status()
                r = self._cfg.risk
                sep = t.t("dashboard.separator")
                circuit_status = t.t("risk.circuit_open") if st["circuit_open"] else t.t("risk.circuit_closed")
                msg = (
                    f"{t.t('risk.title')}\n{sep}\n"
                    f"{t.t('risk.circuit', status=circuit_status)}\n"
                    f"{t.t('risk.equite', amount=st['current_equity'])}\n"
                    f"{t.t('risk.drawdown', dd=st['drawdown_pct'])}\n"
                    f"{t.t('risk.perte_jour', amount=st['daily_loss_usd'])}\n"
                    f"{sep}\n"
                    f"{t.t('risk.max_dd', pct=r.get('max_drawdown_pct', 0) * 100)}\n"
                    f"{t.t('risk.max_levier', lev=r.get('max_leverage_hard', 5))}"
                )
                await query.edit_message_text(
                    msg, parse_mode="HTML",
                    reply_markup=self._kb_main()
                )

            elif data == "btn_start":
                self._cfg.set("strategy", "active", True)
                self._strategy.start()
                if self._dashboard:
                    text = await self._dashboard.build()
                else:
                    text = t.t("bot.started")
                await query.edit_message_text(
                    text, parse_mode="HTML",
                    reply_markup=self._kb_main()
                )

            elif data == "btn_stop":
                self._cfg.set("strategy", "active", False)
                self._strategy.stop()
                await query.edit_message_text(
                    t.t("bot.stopped"), parse_mode="HTML",
                    reply_markup=self._kb_main()
                )

            elif data == "btn_help":
                msg = (
                    f"{t.t('help.title')}\n\n"
                    f"{t.t('help.section_control')}\n"
                    f"{t.t('help.start')}\n{t.t('help.stop')}\n"
                    f"{t.t('help.emergency')}\n{t.t('help.close_all')}\n\n"
                    f"{t.t('help.section_info')}\n"
                    f"{t.t('help.status')}\n{t.t('help.pnl')}\n"
                    f"{t.t('help.positions')}\n{t.t('help.funding')}\n\n"
                    f"{t.t('help.section_wallet')}\n"
                    f"{t.t('help.wallet_cmd')}\n{t.t('help.add_funds')}\n"
                    f"{t.t('help.remove_funds')}"
                )
                await query.edit_message_text(
                    msg, parse_mode="HTML",
                    reply_markup=self._kb_main()
                )

            elif data == "btn_notif":
                current = self._cfg.get("telegram", "trade_notifications", default=True)
                new_val = not current
                self._cfg.set("telegram", "trade_notifications", new_val)
                label = "🔔 Notifications activées" if new_val else "🔕 Notifications désactivées"
                if self._dashboard:
                    text = await self._dashboard.build()
                else:
                    text = label
                await query.edit_message_text(
                    text, parse_mode="HTML",
                    reply_markup=self._kb_main()
                )

            elif data == "btn_emergency":
                await query.edit_message_text(
                    "🚨 <b>ARRÊT D'URGENCE ACTIVÉ</b>", parse_mode="HTML"
                )
                self._strategy.stop()
                self._cfg.set("strategy", "active", False)
                await self._risk.trip_circuit_breaker("Arrêt d'urgence via bouton")
                summaries = await self._pos.all_summaries()
                for s in summaries:
                    try:
                        await self._exec.close_delta_neutral(s["pair"])
                        if self._wallet:
                            await self._wallet.release(s["pair"], pnl=float(s.get("total_pnl", 0)))
                    except Exception:
                        pass
                await query.message.reply_text(
                    "🔴 Toutes les positions fermées. Bot arrêté.",
                    reply_markup=self._kb_main()
                )

            # ── Sous-menu Config ─────────────────────────────────────
            elif data == "menu_config":
                self._pending_input.pop(cid, None)
                strat = self._cfg.strategy
                sep = t.t("dashboard.separator")
                cap = self._wallet.total_capital if self._wallet else strat.get("total_capital_usdt", 0)
                msg = (
                    f"⚙️ <b>Configuration</b>\n{sep}\n"
                    f"Appuyez sur un paramètre pour le modifier.\n"
                    f"Envoyez ensuite la nouvelle valeur."
                )
                await query.edit_message_text(
                    msg, parse_mode="HTML",
                    reply_markup=self._kb_config()
                )

            elif data in ("set_threshold", "set_leverage", "set_max_delta",
                          "set_k", "set_poll", "set_capital"):
                prompts = {
                    "set_threshold": ("Seuil de funding", "en décimal, ex: 0.00005 = 0.005%",
                                     "strategy", "funding_threshold"),
                    "set_leverage": ("Levier", "ex: 2.0",
                                    "strategy", "default_leverage"),
                    "set_max_delta": ("Seuil delta rééquilibrage", "en décimal, ex: 0.02 = 2%",
                                     "strategy", "rebalance_delta_threshold"),
                    "set_k": ("Z-score k", "ex: 1.5",
                              "strategy", "funding_zscore_k"),
                    "set_poll": ("Intervalle polling", "en secondes, ex: 30",
                                 "strategy", "funding_poll_interval_seconds"),
                    "set_capital": ("Capital total", "en USDT, ex: 100",
                                   "strategy", "total_capital_usdt"),
                }
                label, hint, section, key = prompts[data]
                current = self._cfg.get(section, key, default="?")
                self._pending_input[cid] = {
                    "param": data, "section": section, "key": key,
                    "label": label, "msg_id": query.message.message_id,
                }
                await query.edit_message_text(
                    f"✏️ <b>{label}</b>\n\n"
                    f"Valeur actuelle : <code>{current}</code>\n"
                    f"Envoyez la nouvelle valeur ({hint})\n\n"
                    f"Ou appuyez sur 🔙 pour annuler.",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Annuler", callback_data="menu_config")]
                    ])
                )

            # ── Sous-menu Wallet ─────────────────────────────────────
            elif data == "menu_wallet":
                self._pending_input.pop(cid, None)
                await self._show_wallet_view(query)

            elif data in ("input_add_funds", "input_remove_funds"):
                action = "add" if data == "input_add_funds" else "remove"
                label = "Ajouter des fonds" if action == "add" else "Retirer des fonds"
                avail = self._wallet.available_capital if self._wallet else 0
                self._pending_input[cid] = {
                    "param": data, "action": action,
                    "msg_id": query.message.message_id,
                }
                msg = (
                    f"{'💵' if action == 'add' else '💸'} <b>{label}</b>\n\n"
                    f"Capital disponible : <b>${avail:.2f}</b>\n"
                    f"Envoyez le montant en USDT (ex: 50)\n\n"
                    f"Ou appuyez sur 🔙 pour annuler."
                )
                await query.edit_message_text(
                    msg, parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Annuler", callback_data="menu_wallet")]
                    ])
                )

            # ── Sous-menu Paires ─────────────────────────────────────
            elif data == "menu_pairs":
                self._pending_input.pop(cid, None)
                enabled = self._cfg.get("strategy", "enabled_pairs", default=[])
                all_p = self._cfg.get("strategy", "pairs", default=[])
                sep = t.t("dashboard.separator")
                msg = (
                    f"📊 <b>Gestion des paires</b>\n{sep}\n"
                    f"Actives : {', '.join(enabled) or 'Aucune'}\n"
                    f"Total disponibles : {len(all_p)}\n\n"
                    f"Appuyez pour activer/désactiver :"
                )
                await query.edit_message_text(
                    msg, parse_mode="HTML",
                    reply_markup=self._kb_pairs()
                )

            elif data.startswith("enable_"):
                pair = data.replace("enable_", "")
                enabled = list(self._cfg.get("strategy", "enabled_pairs") or [])
                if pair not in enabled:
                    enabled.append(pair)
                    self._cfg.set("strategy", "enabled_pairs", enabled)
                await query.edit_message_text(
                    f"✅ <b>{pair}</b> activée\n\nPaires actives : {', '.join(enabled)}",
                    parse_mode="HTML",
                    reply_markup=self._kb_pairs()
                )

            elif data.startswith("disable_"):
                pair = data.replace("disable_", "")
                enabled = [p for p in (self._cfg.get("strategy", "enabled_pairs") or [])
                           if p != pair]
                self._cfg.set("strategy", "enabled_pairs", enabled)
                await query.edit_message_text(
                    f"❌ <b>{pair}</b> désactivée\n\nPaires actives : {', '.join(enabled) or 'Aucune'}",
                    parse_mode="HTML",
                    reply_markup=self._kb_pairs()
                )

        except telegram.error.BadRequest as e:
            if "not modified" in str(e).lower():
                pass  # Message identique, on ignore
            else:
                logger.exception(f"Erreur bouton {data}: {e}")
                try:
                    await query.edit_message_text(
                        f"❌ Erreur : {e}",
                        reply_markup=self._kb_main()
                    )
                except Exception:
                    pass
        except Exception as e:
            logger.exception(f"Erreur bouton {data}: {e}")
            try:
                await query.edit_message_text(
                    f"❌ Erreur : {e}",
                    reply_markup=self._kb_main()
                )
            except Exception:
                pass

    async def _show_wallet_view(self, query):
        """Afficher la vue wallet avec boutons."""
        t = self._t
        if not self._wallet:
            await query.edit_message_text(
                "❌ Module wallet non configuré.",
                reply_markup=self._kb_main()
            )
            return
        w = self._wallet.snapshot()
        exposure = await self._pos.total_exposure()
        avg_lev = self._wallet.get_average_leverage(exposure)
        sep = t.t("dashboard.separator")
        lines = [
            t.t("wallet.title"), sep,
            t.t("wallet.capital_total", amount=w["total_capital"]),
            t.t("wallet.capital_engaged", amount=w["committed_capital"]),
            t.t("wallet.capital_available", amount=w["available_capital"]),
            sep,
            t.t("wallet.funding_cumule", amount=w["accumulated_funding"]),
            t.t("wallet.pnl_realise", amount=w["realized_pnl"]),
            t.t("wallet.roi", pct=w["roi_pct"]),
            sep,
            t.t("wallet.exposition_totale", amount=exposure),
            t.t("wallet.levier_moyen", lev=avg_lev),
        ]
        await query.edit_message_text(
            "\n".join(lines), parse_mode="HTML",
            reply_markup=self._kb_wallet()
        )

    async def _handle_text_input(self, update: Update,
                                  ctx: ContextTypes.DEFAULT_TYPE):
        """Recevoir la valeur tapée par l'utilisateur pour un paramètre."""
        cid = update.effective_chat.id
        if cid not in self._admin_ids:
            return
        if cid not in self._pending_input:
            return  # Pas en mode saisie

        pending = self._pending_input.pop(cid)
        text = update.message.text.strip()

        try:
            val = float(text)
        except ValueError:
            await update.message.reply_text(
                f"❌ Valeur invalide : {text}\nEnvoyez un nombre.",
                reply_markup=self._kb_main()
            )
            return

        param = pending["param"]

        # ── Config parameters ────────────────────────────────────
        if param in ("set_threshold", "set_leverage", "set_max_delta",
                      "set_k", "set_poll", "set_capital"):
            section = pending["section"]
            key = pending["key"]
            label = pending["label"]

            # Validation spécifique
            if param == "set_leverage":
                val = await self._risk.check_leverage(val)
            elif param == "set_poll":
                val = int(val)
            elif param == "set_capital" and self._wallet:
                await self._wallet.set_capital(val)

            self._cfg.set(section, key, val)

            await update.message.reply_text(
                f"✅ <b>{label}</b> → <code>{val}</code>",
                parse_mode="HTML",
                reply_markup=self._kb_config()
            )

        # ── Wallet add/remove ────────────────────────────────────
        elif param == "input_add_funds":
            if self._wallet:
                await self._wallet.add_funds(val)
                await update.message.reply_text(
                    f"✅ <b>${val:.2f}</b> ajoutés\n"
                    f"Capital total : <b>${self._wallet.total_capital:.2f}</b>",
                    parse_mode="HTML",
                    reply_markup=self._kb_wallet()
                )
            else:
                await update.message.reply_text("❌ Module wallet non configuré.")

        elif param == "input_remove_funds":
            if self._wallet:
                success = await self._wallet.remove_funds(val)
                if success:
                    await update.message.reply_text(
                        f"✅ <b>${val:.2f}</b> retirés\n"
                        f"Capital total : <b>${self._wallet.total_capital:.2f}</b>",
                        parse_mode="HTML",
                        reply_markup=self._kb_wallet()
                    )
                else:
                    await update.message.reply_text(
                        f"❌ Fonds insuffisants. Disponible : ${self._wallet.available_capital:.2f}",
                        reply_markup=self._kb_wallet()
                    )
            else:
                await update.message.reply_text("❌ Module wallet non configuré.")

    def _parse_float(self, args, name: str) -> float:
        t = self._t
        if not args:
            raise ValueError(t.t("config_cmds.missing_value", name=name))
        try:
            return float(args[0])
        except ValueError:
            raise ValueError(t.t("config_cmds.invalid_value", name=name, val=args[0]))

