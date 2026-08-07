"""
dashboard/dashboard_builder.py - Constructeur de tableau de bord Telegram.
Génère un affichage structuré et professionnel pour le bot.
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class DashboardBuilder:
    """
    Construit le tableau de bord complet du bot pour Telegram.
    Affiche les 5 sections : État, Wallet, Positions, Funding, Risk.
    """

    def __init__(self, config, wallet_mgr, position_mgr,
                 risk_mgr, funding_mgr, translator):
        self._cfg = config
        self._wallet = wallet_mgr
        self._pos = position_mgr
        self._risk = risk_mgr
        self._funding = funding_mgr
        self._t = translator
        self._start_time = datetime.utcnow()

    def set_start_time(self, start_time: datetime):
        """Définir l'heure de démarrage pour le calcul de l'uptime."""
        self._start_time = start_time

    async def build(self) -> str:
        """Construit le tableau de bord complet en HTML pour Telegram."""
        t = self._t
        sep = t.t("dashboard.separator")
        sections = []

        # ── En-tête ─────────────────────────────────────────────────────
        bot_name = self._cfg.get("bot_name", default="Delta Neutre Bot")
        sections.append(t.t("dashboard.header", bot_name=bot_name))
        sections.append(sep)

        # ── 1. État du Bot ──────────────────────────────────────────────
        sections.append(await self._build_state_section())
        sections.append(sep)

        # ── 2. Wallet ───────────────────────────────────────────────────
        sections.append(await self._build_wallet_section())
        sections.append(sep)

        # ── 3. Positions ────────────────────────────────────────────────
        sections.append(await self._build_positions_section())
        sections.append(sep)

        # ── 4. Funding ──────────────────────────────────────────────────
        sections.append(self._build_funding_section())
        sections.append(sep)

        # ── 5. Risk ─────────────────────────────────────────────────────
        sections.append(self._build_risk_section())

        return "\n".join(sections)

    async def _build_state_section(self) -> str:
        """Section État du Bot."""
        t = self._t
        strat = self._cfg.strategy
        is_active = strat.get("active", False)
        status = t.t("dashboard.statut_actif") if is_active else t.t("dashboard.statut_pause")

        # Mode : testnet = Paper, mainnet = Live
        is_testnet = self._cfg.get("pacifica", "testnet", default=False)
        mode = t.t("dashboard.mode_paper") if is_testnet else t.t("dashboard.mode_live")

        enabled_pairs = strat.get("enabled_pairs", [])
        uptime = datetime.utcnow() - self._start_time
        uptime_str = str(uptime).split('.')[0]

        lines = [
            t.t("dashboard.section_etat"),
            t.t("dashboard.statut", status=status),
            t.t("dashboard.mode", mode=mode),
            t.t("dashboard.paires_actives", count=len(enabled_pairs)),
            t.t("dashboard.uptime", uptime=uptime_str),
        ]
        return "\n".join(lines)

    async def _build_wallet_section(self) -> str:
        """Section Portefeuille."""
        t = self._t
        w = self._wallet.snapshot()
        exposure = await self._pos.total_exposure()
        avg_lev = self._wallet.get_average_leverage(exposure)

        lines = [
            t.t("dashboard.section_wallet"),
            t.t("wallet.capital_total", amount=w["total_capital"]),
            t.t("wallet.capital_engaged", amount=w["committed_capital"]),
            t.t("wallet.capital_available", amount=w["available_capital"]),
            t.t("wallet.funding_cumule", amount=w["accumulated_funding"]),
            t.t("wallet.roi", pct=w["roi_pct"]),
            t.t("wallet.exposition_totale", amount=exposure),
            t.t("wallet.levier_moyen", lev=avg_lev),
        ]
        return "\n".join(lines)

    async def _build_positions_section(self) -> str:
        """Section Positions."""
        t = self._t
        summaries = await self._pos.all_summaries()
        active = [s for s in summaries if s.get("active")]

        lines = [t.t("dashboard.section_positions")]

        if not active:
            lines.append(t.t("dashboard.no_positions"))
            return "\n".join(lines)

        # Delta global
        total_delta = sum(s.get("net_delta", 0) for s in active)
        lines.append(t.t("dashboard.delta_global", delta=total_delta))

        # Exposition brute
        total_exposure = sum(s.get("gross_exposure", 0) for s in active)
        lines.append(t.t("dashboard.exposition_brute", amount=total_exposure))

        # Levier moyen
        avg_lev = self._wallet.get_average_leverage(total_exposure)
        lines.append(t.t("dashboard.levier_moyen", lev=avg_lev))

        # Distance liquidation la plus proche
        liq_alerts = await self._pos.get_liquidation_alerts()
        if liq_alerts:
            lines.append(t.t("dashboard.liquidation_proche", info=liq_alerts[0]))
        else:
            lines.append(t.t("dashboard.liquidation_ok"))

        return "\n".join(lines)

    def _build_funding_section(self) -> str:
        """Section Funding."""
        t = self._t
        lines = [t.t("dashboard.section_funding")]

        # Top 3 opportunités
        k = self._cfg.get("strategy", "funding_zscore_k", default=1.5)
        min_rate = self._cfg.get("strategy", "funding_threshold", default=0.0003)
        summaries = self._funding.all_summaries()

        # Trier par taux annualisé décroissant
        sorted_funding = sorted(
            summaries,
            key=lambda s: abs(float(str(s.get("annualized_pct", "0%")).rstrip("%"))),
            reverse=True
        )

        top3 = sorted_funding[:3]
        if top3:
            lines.append(t.t("dashboard.top_opportunites"))
            for s in top3:
                lines.append(t.t("dashboard.opp_line",
                                 pair=s["pair"],
                                 rate=s["rate_pct"],
                                 ann=s["annualized_pct"]))
        else:
            lines.append(t.t("dashboard.no_opportunites"))

        # Seuil actuel
        threshold = self._cfg.get("strategy", "funding_threshold", default=0.0003)
        lines.append(t.t("dashboard.seuil_actuel", threshold=threshold * 100))

        return "\n".join(lines)

    def _build_risk_section(self) -> str:
        """Section Gestion du Risque."""
        t = self._t
        st = self._risk.status()
        r = self._cfg.risk

        circuit_status = t.t("dashboard.circuit_on") if st["circuit_open"] else t.t("dashboard.circuit_off")
        max_dd = r.get("max_drawdown_pct", 0.10) * 100

        lines = [
            t.t("dashboard.section_risk"),
            t.t("dashboard.drawdown_actuel", dd=st["drawdown_pct"]),
            t.t("dashboard.max_dd_autorise", max_dd=max_dd),
            t.t("dashboard.perte_journaliere", amount=st["daily_loss_usd"]),
            t.t("dashboard.circuit_breaker", status=circuit_status),
        ]
        return "\n".join(lines)
