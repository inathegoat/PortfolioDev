"""
strategies/delta_neutral.py - Orchestrateur de la boucle stratégie principale.
Interroge le funding, détecte les signaux, gère les entrées/sorties/rééquilibrages.
Intégré avec le wallet interne pour le sizing dynamique.
"""

import asyncio
import logging
from datetime import datetime

from modules.pacifica_api import PacificaAPI
from modules.funding_analyzer import FundingAnalyzerManager, FundingSnapshot
from modules.position_manager import PositionManager
from modules.execution_engine import ExecutionEngine
from modules.risk_manager import RiskManager
from core.logger import FundingLogger

from typing import Optional

logger = logging.getLogger(__name__)


class DeltaNeutralStrategy:
    """
    Boucle stratégie principale.
    - Interroge les taux de funding pour les paires actives
    - Déclenche les signaux d'entrée quand les conditions sont remplies
    - Rééquilibre quand le delta dépasse le seuil
    - Exécute les contrôles de risque et le circuit breaker
    - Utilise le wallet interne pour le sizing des positions
    """

    def __init__(self, api: PacificaAPI, funding_mgr: FundingAnalyzerManager,
                 position_mgr: PositionManager, execution: ExecutionEngine,
                 risk_mgr: RiskManager, config, funding_log: FundingLogger,
                 wallet_mgr=None, translator=None):
        self._api = api
        self._funding_mgr = funding_mgr
        self._pos = position_mgr
        self._exec = execution
        self._risk = risk_mgr
        self._cfg = config
        self._funding_log = funding_log
        self._wallet = wallet_mgr
        self._t = translator
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._alert_callbacks: list = []

    # ── Contrôle ─────────────────────────────────────────────────────────────

    def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Stratégie DÉMARRÉE")

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("Stratégie ARRÊTÉE")

    def add_alert_callback(self, cb):
        """cb(msg: str) sera appelé pour les alertes."""
        self._alert_callbacks.append(cb)

    async def _alert(self, msg: str):
        logger.warning(f"ALERTE: {msg}")
        for cb in self._alert_callbacks:
            try:
                await cb(msg)
            except Exception as e:
                logger.error(f"Erreur callback alerte : {e}")

    # ── Boucle principale ────────────────────────────────────────────────────

    async def _loop(self):
        poll_interval = self._cfg.get("strategy", "funding_poll_interval_seconds",
                                      default=10)
        rebal_interval = self._cfg.get("strategy", "rebalance_check_interval_seconds",
                                       default=30)
        last_rebal_check = 0.0

        while self._running:
            try:
                now = asyncio.get_event_loop().time()

                # 1. Interrogation funding
                await self._poll_funding()

                # 2. Vérification signaux d'entrée
                if self._cfg.get("strategy", "active", default=True):
                    if not self._risk.circuit_open:
                        await self._check_entries()
                    else:
                        logger.warning("Circuit breaker OUVERT — aucune nouvelle entrée")

                # 3. Vérification rééquilibrage (moins fréquent)
                if now - last_rebal_check > rebal_interval:
                    await self._check_rebalances()
                    last_rebal_check = now

                # 4. Contrôle de risque
                await self._run_risk_checks()

                # 5. Alertes anomalies
                drop_thresh = self._cfg.get("risk", "funding_drop_alert_pct",
                                            default=0.50)
                for msg in self._funding_mgr.check_anomalies(drop_thresh):
                    await self._alert(msg)

                # 6. Mise à jour PnL non réalisé dans le wallet
                if self._wallet:
                    unrealized = await self._pos.total_pnl()
                    await self._wallet.update_unrealized_pnl(unrealized)

                await asyncio.sleep(poll_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Erreur boucle stratégie : {e}")
                await asyncio.sleep(5)

    async def _poll_funding(self):
        enabled = self._cfg.get("strategy", "enabled_pairs", default=[])
        for pair in enabled:
            try:
                # GET /api/v1/info retourne funding_rate + next_funding_rate par symbole
                market_info = await self._api.get_funding_rate(pair)
                # Aussi récupérer le mark price depuis /prices
                mark_price = await self._api.get_mark_price(pair)

                snap = FundingSnapshot(
                    pair=pair,
                    rate=float(market_info.get("funding_rate", 0)),
                    next_funding_ts=0,
                    open_interest=0,
                    volume_24h=0,
                )
                analyzer = self._funding_mgr.get(pair)
                await analyzer.update(snap)

                # Estimer le funding collecté pour les positions actives
                state = await self._pos.get_or_create(pair)
                if state.active and abs(state.perp.size) > 0:
                    # Mettre à jour le mark price
                    state.spot.current_price = mark_price
                    state.perp.current_price = mark_price
                    est_usd = analyzer.funding_collected_usd(state.perp.notional)
                    self._funding_log.log_funding(
                        pair, snap.rate, 1,  # intervalle 1h
                        state.perp.notional, est_usd
                    )

                    # Enregistrer le funding dans le wallet
                    if self._wallet and est_usd > 0:
                        await self._wallet.record_funding(pair, est_usd)

            except Exception as e:
                logger.warning(f"[{pair}] Erreur polling funding : {e}")

    async def _check_entries(self):
        k = self._cfg.get("strategy", "funding_zscore_k", default=1.5)
        min_rate = self._cfg.get("strategy", "funding_threshold", default=0.0003)
        cap_pct = self._cfg.get("strategy", "capital_per_pair_pct", default=0.4)

        # Utiliser le wallet pour le capital total si disponible
        if self._wallet:
            total_capital = self._wallet.total_capital
        else:
            total_capital = self._cfg.get("strategy", "total_capital_usdt", default=10000.0)

        candidates = self._funding_mgr.top_opportunities(k=k, min_rate=min_rate)

        if not candidates:
            # Log tous les taux pour debug
            all_analyzers = self._funding_mgr._analyzers
            for p, a in all_analyzers.items():
                if len(a._history) > 0:
                    logger.info(
                        f"[{p}] rate={a.current_rate:.6f} "
                        f"ma={a.moving_average:.6f} std={a.std_dev:.6f} "
                        f"history={len(a._history)}/{a.ma_period} "
                        f"signal={a.is_signal(k, min_rate)}"
                    )
        else:
            logger.info(f"Candidats trouvés : {candidates}")

        for pair in candidates:
            state = await self._pos.get_or_create(pair)
            if state.active:
                continue  # Déjà en position

            pair_capital = total_capital * cap_pct

            # Vérifier le capital disponible dans le wallet
            if self._wallet:
                if not self._wallet.can_allocate(pair_capital):
                    logger.warning(
                        f"[{pair}] Capital insuffisant. "
                        f"Disponible : ${self._wallet.available_capital:.2f}, "
                        f"Requis : ${pair_capital:.2f}"
                    )
                    await self._alert(
                        f"❌ Capital insuffisant pour {pair}\n"
                        f"Disponible : ${self._wallet.available_capital:.2f}\n"
                        f"Requis : ${pair_capital:.2f}"
                    )
                    continue

                # Vérifier allocation max par paire
                max_alloc_pct = self._cfg.get("wallet", "max_allocation_per_pair_pct",
                                               default=0.4)
                if not self._wallet.check_max_allocation(pair_capital, max_alloc_pct):
                    logger.warning(f"[{pair}] Allocation dépasse le max autorisé")
                    continue

                # Vérifier le levier global
                max_lev = self._cfg.get("wallet", "max_leverage_global", default=5.0)
                current_exposure = await self._pos.total_exposure()
                new_exposure = current_exposure + pair_capital
                if not self._wallet.check_leverage(new_exposure, max_lev):
                    logger.warning(f"[{pair}] Levier global dépasserait le seuil")
                    await self._alert(
                        f"🚨 Levier global trop élevé pour ouvrir {pair}"
                    )
                    continue

            # Vérification concentration (existante)
            ok = await self._risk.check_concentration(
                pair_capital, total_capital, pair
            )
            if not ok:
                continue

            analyzer = self._funding_mgr.get(pair)
            mark_price = await self._api.get_mark_price(pair)
            if mark_price <= 0:
                logger.warning(f"[{pair}] Mark price indisponible, passage")
                continue

            logger.info(f"[{pair}] Signal d'entrée : rate={analyzer.current_rate:.6f}/h "
                        f"z={analyzer.z_score:.2f} ann={analyzer.annualized_rate*100:.2f}%")

            result = await self._exec.open_delta_neutral(
                pair, pair_capital, analyzer.current_rate, mark_price
            )
            if result.success:
                # Allouer le capital dans le wallet
                if self._wallet:
                    await self._wallet.allocate(pair, pair_capital)

                await self._alert(
                    f"✅ Position DN ouverte <b>{pair}</b>\n"
                    f"Capital : ${pair_capital:.0f}\n"
                    f"Funding : {analyzer.current_rate*100:.4f}%/h\n"
                    f"Annualisé : {analyzer.annualized_rate*100:.2f}%\n"
                    f"Z-score : {analyzer.z_score:.2f}"
                )
            else:
                logger.warning(f"[{pair}] Entrée échouée : {result.error}")

    async def _check_rebalances(self):
        threshold = self._cfg.get("strategy", "rebalance_delta_threshold",
                                  default=0.02)
        pairs = await self._pos.get_pairs_needing_rebalance(threshold)
        for pair in pairs:
            logger.info(f"[{pair}] Rééquilibrage du delta")
            result = await self._exec.rebalance(pair)
            if result.success:
                await self._alert(f"⚖️ Delta rééquilibré : {pair}")

    async def _run_risk_checks(self):
        try:
            account = await self._api.get_account()
        except Exception:
            # Compte non encore créé sur Pacifica — skip les checks equity
            return
        equity = float(account.get("account_equity", 0))

        violation = await self._risk.auto_check_and_trip(equity)
        if violation:
            await self._alert(f"🚨 LIMITE DE RISQUE ATTEINTE : {violation}")

        # Alertes liquidation
        liq_alerts = await self._pos.get_liquidation_alerts()
        for msg in liq_alerts:
            await self._alert(msg)

        # Alertes delta
        delta_thresh = self._cfg.get("risk", "delta_alert_threshold", default=0.05)
        summaries = await self._pos.all_summaries()
        for s in summaries:
            dr = abs(float(s["delta_ratio_pct"].rstrip("%"))) / 100
            if dr > delta_thresh:
                await self._alert(
                    f"⚠️ Delta élevé : {s['pair']} ratio_delta={s['delta_ratio_pct']}"
                )

        # Vérifier le levier global via le wallet
        if self._wallet:
            total_exposure = await self._pos.total_exposure()
            max_lev = self._cfg.get("wallet", "max_leverage_global", default=5.0)
            lev_ok = await self._risk.check_global_leverage(
                total_exposure, self._wallet.total_capital, max_lev
            )
            if not lev_ok:
                await self._alert(
                    f"🚨 Levier global excessif : "
                    f"{self._wallet.get_average_leverage(total_exposure):.1f}x "
                    f"> {max_lev:.1f}x"
                )
