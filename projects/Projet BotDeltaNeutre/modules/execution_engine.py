"""
modules/execution_engine.py - Order execution adapted for Pacifica DEX.

⚠️  IMPORTANT ARCHITECTURE NOTE — Pacifica is a perp-only DEX (Solana).
    There is NO native spot market on Pacifica.

    Delta-Neutral implementation options:
    A) "Perp Split" (same exchange, two sub-accounts or wallet pairs):
       - Sub-account A: Long perp at 1x leverage (synthetic spot exposure)
       - Sub-account B: Short perp at 1x leverage (hedge)
       → Delta = +1x (long) + (-1x) (short) = 0
       → Both positions earn/pay funding. Net funding = 2 × rate if same rate.
       → This is the recommended approach for Pacifica.

    B) "Cross-venue" (spot on CEX/Solana DEX + short perp on Pacifica):
       - Buy spot on e.g. Jupiter/Binance
       - Short perp on Pacifica
       → True delta-neutral: captures funding while hedging price risk.
       → Requires managing two separate exchange connections.

    This engine implements Option A (Perp Split) by default, with a
    cross_venue flag to plug in an external spot connector.

    Pacifica specifics:
    - side: "bid" = long/buy, "ask" = short/sell
    - amount: base token denomination (e.g. 0.1 for 0.1 BTC)
    - symbol: "BTC", "ETH" (no suffix)
    - funding: 1h interval, sampled every 5s, TWAP applied
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from modules.position_manager import PositionManager
from modules.risk_manager import RiskManager
from core.logger import TradeLogger

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    success: bool
    pair: str
    action: str
    long_order_id: Optional[str] = None
    short_order_id: Optional[str] = None
    fill_price: float = 0.0
    qty: float = 0.0
    total_fees: float = 0.0
    error: Optional[str] = None


class ExecutionEngine:
    """
    Handles entry, exit, and rebalance execution on Pacifica.
    Uses market orders for speed; configurable slippage tolerance.

    Delta-Neutral via Perp Split:
    - Long leg:  bid (long perp) at 1x leverage = synthetic spot
    - Short leg: ask (short perp) at 1x leverage = hedge
    Both legs on same symbol, potentially same account with cross-margin
    or via two configured wallets.
    """

    def __init__(self, api, position_mgr: PositionManager,
                 risk_mgr: RiskManager, config, trade_logger: TradeLogger):
        self._api = api
        self._pos = position_mgr
        self._risk = risk_mgr
        self._cfg = config
        self._trade_log = trade_logger
        self._lock = asyncio.Lock()

    # ── Profitability Check ─────────────────────────────────────────────────

    def _net_annual_yield(self, funding_rate: float) -> float:
        """
        Pacifica: 1h funding interval, 8760 intervals/year.
        Net yield = gross funding − round-trip fees (entry + exit).
        Uses abs(rate) since we always take the receiving side.
        """
        hours_per_year = 8760   # Pacifica: 1h intervals
        gross = abs(funding_rate) * hours_per_year
        taker = self._cfg.get("strategy", "taker_fee_pct", default=0.0006)
        slippage = self._cfg.get("strategy", "slippage_pct", default=0.001)
        # 2 legs round-trip: open + close
        round_trip_cost = (taker + slippage) * 2
        return gross - round_trip_cost

    def is_profitable_entry(self, funding_rate: float) -> bool:
        return self._net_annual_yield(funding_rate) > 0

    # ── Open Delta-Neutral (Perp Split) ────────────────────────────────────

    async def open_delta_neutral(
        self, pair: str, capital_usd: float,
        funding_rate: float, mark_price: float
    ) -> ExecutionResult:
        """
        Open a delta-neutral position to capture funding:
        - funding > 0 : SHORT perp + BUY spot (shorts receive funding)
        - funding < 0 : LONG perp + SELL spot (longs receive funding)
        Capital is split 50/50 between perp margin and spot hedge.
        Falls back to perp-only if spot hedge fails.
        """
        async with self._lock:
            strat = self._cfg.strategy
            min_size = float(strat.get("min_order_size_usd", 10.0))
            slippage = float(strat.get("slippage_pct", 0.001)) * 100

            if not self.is_profitable_entry(funding_rate):
                return ExecutionResult(False, pair, "open",
                                       error="Entry not profitable after fees")

            if capital_usd < min_size:
                return ExecutionResult(
                    False, pair, "open",
                    error=f"Capital too small: ${capital_usd:.2f} < ${min_size} min"
                )

            # Split capital: half for perp, half for spot hedge
            perp_capital = capital_usd / 2
            spot_capital = capital_usd / 2
            qty = perp_capital / mark_price

            # Choisir le côté qui REÇOIT le funding
            if funding_rate > 0:
                perp_side = "ask"      # Short perp reçoit quand funding > 0
                spot_is_buy = True     # Buy spot pour hedger le short
                pos_sign = -1
                side_label = "SHORT"
            else:
                perp_side = "bid"      # Long perp reçoit quand funding < 0
                spot_is_buy = False    # Sell spot pour hedger le long
                pos_sign = 1
                side_label = "LONG"

            try:
                await self._api.update_leverage(pair, leverage=1)
            except Exception as e:
                logger.warning(f"[{pair}] Set leverage warning: {e}")

            logger.info(f"[{pair}] Opening DN {side_label} {qty:.6f} "
                        f"@ ${mark_price:.2f} | funding={funding_rate*100:.4f}%/h")

            # ── Leg 1: Perp ──
            try:
                result = await self._safe_market_order(pair, perp_side, qty, slippage, False)
            except Exception as e:
                logger.error(f"[{pair}] Perp entry failed: {e}")
                return ExecutionResult(False, pair, "open",
                                       error=f"Order failed: {e}")

            # ── Leg 2: Spot hedge ──
            spot_hedged = False
            spot_qty = qty
            try:
                if spot_is_buy:
                    # Buy spot to hedge short perp
                    await self._api.place_spot_market_order(pair, True, spot_qty, slippage)
                    spot_hedged = True
                    logger.info(f"[{pair}] Spot BUY hedge {spot_qty:.6f} ✓")
                else:
                    # Sell spot to hedge long perp — need to hold spot first
                    spot_balance = await self._api.get_spot_balance(pair)
                    if spot_balance >= spot_qty * 0.9:
                        await self._api.place_spot_market_order(pair, False, min(spot_qty, spot_balance), slippage)
                        spot_hedged = True
                        logger.info(f"[{pair}] Spot SELL hedge {spot_qty:.6f} ✓")
                    else:
                        logger.warning(f"[{pair}] No spot {pair} to sell for hedge "
                                     f"(have {spot_balance:.4f}, need {spot_qty:.4f})")
            except Exception as e:
                logger.warning(f"[{pair}] Spot hedge failed: {e} — running unhedged")

            taker = self._cfg.get("strategy", "taker_fee_pct", default=0.0006)
            fees = capital_usd * taker * (2 if spot_hedged else 1)

            state = await self._pos.get_or_create(pair)
            state.active = True
            state.entry_capital = capital_usd
            state.perp.size = pos_sign * qty
            state.perp.avg_price = mark_price
            state.perp.current_price = mark_price
            state.perp.leverage = 1.0
            state.spot.size = (1 if spot_is_buy else -1) * spot_qty if spot_hedged else 0

            hedge_status = "✅ hedgé" if spot_hedged else "⚠️ non-hedgé"

            self._trade_log.log_trade(
                pair=pair, side="OPEN", market_type=f"DN_{side_label}",
                qty=qty, price=mark_price, fee=fees,
                notes=f"funding={funding_rate:.6f}/h ann={self._net_annual_yield(funding_rate)*100:.2f}% {hedge_status}"
            )

            logger.info(f"[{pair}] DN {side_label} opened ✓ | {hedge_status} | fees=${fees:.4f} | "
                        f"est.APY={self._net_annual_yield(funding_rate)*100:.2f}%")
            return ExecutionResult(True, pair, "open", qty=qty, total_fees=fees)

    # ── Close Position ──────────────────────────────────────────────────────

    async def close_delta_neutral(self, pair: str) -> ExecutionResult:
        async with self._lock:
            state = await self._pos.get_or_create(pair)
            if not state.active or state.spot.size == 0:
                return ExecutionResult(False, pair, "close",
                                       error="No active position")

            qty = state.spot.size
            slippage = float(self._cfg.get("strategy", "slippage_pct",
                                           default=0.001)) * 100

            logger.info(f"[{pair}] Closing DN: close long {qty:.6f} + close short {qty:.6f}")

            # Close both legs (reverse sides, reduce_only=True)
            long_close, short_close = await asyncio.gather(
                self._safe_market_order(pair, "ask", qty, slippage, True),   # close long
                self._safe_market_order(pair, "bid", qty, slippage, True),   # close short
                return_exceptions=True
            )

            if isinstance(long_close, Exception) or isinstance(short_close, Exception):
                logger.error(f"[{pair}] DN close partial: {long_close} / {short_close}")
                # Still update state — position may be partially closed
                # Operator should verify on exchange

            realized = state.total_pnl
            await self._pos.record_realized_pnl(pair, realized)
            state.active = False
            state.spot.size = 0
            state.perp.size = 0

            self._trade_log.log_trade(
                pair=pair, side="CLOSE", market_type="DN_PERP_SPLIT",
                qty=qty, price=state.spot.current_price,
                pnl=realized, funding_collected=state.perp.funding_collected
            )
            return ExecutionResult(True, pair, "close", qty=qty)

    # ── Rebalance ────────────────────────────────────────────────────────────

    async def rebalance(self, pair: str) -> ExecutionResult:
        """
        Adjust the short perp leg to restore delta neutrality.
        Net delta = long_size + short_size (short is negative).
        If delta > 0: short leg too small → increase short.
        If delta < 0: short leg too large → reduce short.
        """
        async with self._lock:
            state = await self._pos.get_or_create(pair)
            if not state.active:
                return ExecutionResult(False, pair, "rebalance",
                                       error="No active position")

            delta = state.net_delta
            if abs(delta) < 0.0001:
                return ExecutionResult(True, pair, "rebalance")

            slippage = float(self._cfg.get("strategy", "slippage_pct",
                                           default=0.001)) * 100

            if delta > 0:
                # Too long → sell more short perp
                side, reduce = "ask", False
            else:
                # Too short → buy back short perp
                side, reduce = "bid", True

            qty = abs(delta)
            logger.info(f"[{pair}] Rebalance: {side} {qty:.6f} "
                        f"(delta={delta:+.6f})")

            result = await self._safe_market_order(pair, side, qty,
                                                   slippage, reduce)
            if isinstance(result, Exception):
                return ExecutionResult(False, pair, "rebalance", error=str(result))

            # Adjust short leg
            state.perp.size += (-qty if side == "ask" else qty)
            return ExecutionResult(True, pair, "rebalance", qty=qty)

    # ── Helpers ──────────────────────────────────────────────────────────────

    async def _safe_market_order(self, symbol: str, side: str, qty: float,
                                  slippage_pct: float,
                                  reduce_only: bool) -> dict:
        try:
            r = await self._api.place_market_order(
                symbol, side, qty,
                reduce_only=reduce_only,
                slippage_percent=slippage_pct
            )
            oid = r.get("order_id", "?") if isinstance(r, dict) else "?"
            logger.info(f"[{symbol}] {side} {qty:.6f} "
                        f"reduce={reduce_only} → order {oid}")
            return r
        except Exception as e:
            logger.error(f"[{symbol}] Order failed ({side} {qty:.6f}): {e}")
            raise

    async def _rollback(self, pair: str, long_r, short_r, qty: float,
                        slippage: float):
        """Close the leg that succeeded if the other failed."""
        if not isinstance(long_r, Exception):
            logger.warning(f"[{pair}] Rolling back long leg")
            try:
                await self._safe_market_order(pair, "ask", qty, slippage, True)
            except Exception as e:
                logger.error(f"[{pair}] Rollback long failed: {e}")
        if not isinstance(short_r, Exception):
            logger.warning(f"[{pair}] Rolling back short leg")
            try:
                await self._safe_market_order(pair, "bid", qty, slippage, True)
            except Exception as e:
                logger.error(f"[{pair}] Rollback short failed: {e}")

