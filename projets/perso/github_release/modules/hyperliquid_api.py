"""
modules/hyperliquid_api.py - Hyperliquid DEX API client.

Drop-in replacement for PacificaAPI using the official hyperliquid-python-sdk.
Uses EVM wallet (eth_account) for order signing.
"""

import asyncio
import logging
from typing import Any, Optional
from functools import partial

logger = logging.getLogger(__name__)

FUNDING_INTERVAL_HOURS = 1  # Hyperliquid: hourly funding (8h formula ÷ 8)


class HyperliquidAPI:
    """Async-compatible wrapper around the Hyperliquid Python SDK."""

    def __init__(
        self,
        account: str = "",
        private_key: str = "",
        base_url: str = "https://api.hyperliquid.xyz",
        testnet: bool = False,
    ):
        from hyperliquid.info import Info
        from hyperliquid.utils import constants

        url = constants.TESTNET_API_URL if testnet else base_url
        self._account = account
        self._private_key = private_key
        self._info = Info(url, skip_ws=True)

        # Exchange requires a valid private key
        self._exchange = None
        if private_key:
            try:
                from hyperliquid.exchange import Exchange
                self._exchange = Exchange(
                    wallet=None,  # We'll sign manually
                    base_url=url,
                    account_address=account,
                )
                # The SDK expects the wallet directly — let's use eth_account
                from eth_account import Account
                wallet = Account.from_key(private_key)
                self._exchange = Exchange(
                    wallet=wallet,
                    base_url=url,
                    account_address=account or wallet.address,
                )
                if not account:
                    self._account = wallet.address
                logger.info(f"🔑 Signer EVM configuré — Compte : {self._account}")
            except Exception as e:
                logger.error(f"❌ Erreur configuration signer EVM : {e}")
                self._exchange = None

        # Cache: symbol → asset index mapping
        self._symbol_to_idx: dict[str, int] = {}
        self._meta_cache: Optional[dict] = None

    async def _run_sync(self, func, *args, **kwargs):
        """Run a synchronous SDK call in a thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, partial(func, *args, **kwargs)
        )

    async def _ensure_meta(self):
        """Load symbol → index mapping if not cached."""
        if self._meta_cache:
            return
        meta = await self._run_sync(self._info.meta)
        self._meta_cache = meta
        for i, asset in enumerate(meta.get("universe", [])):
            self._symbol_to_idx[asset["name"]] = i

    def _get_asset_idx(self, symbol: str) -> int:
        """Get the numeric asset index for a symbol."""
        return self._symbol_to_idx.get(symbol, -1)

    # ── Market Data ──────────────────────────────────────────────────────────

    async def get_market_info(self) -> list[dict]:
        """Get all perpetual markets metadata + asset contexts."""
        data = await self._run_sync(self._info.meta_and_asset_ctxs)
        meta = data[0]  # universe + margin tables
        ctxs = data[1]  # per-asset contexts

        await self._ensure_meta()

        result = []
        for i, asset in enumerate(meta.get("universe", [])):
            ctx = ctxs[i] if i < len(ctxs) else {}
            result.append({
                "symbol": asset["name"],
                "szDecimals": asset.get("szDecimals", 0),
                "maxLeverage": asset.get("maxLeverage", 50),
                "funding_rate": ctx.get("funding", "0"),
                "mark_price": ctx.get("markPx", "0"),
                "open_interest": ctx.get("openInterest", "0"),
                "oracle_price": ctx.get("oraclePx", "0"),
                "premium": ctx.get("premium", "0"),
            })
        return result

    async def get_market_info_for(self, symbol: str) -> Optional[dict]:
        """Get info for a single symbol."""
        markets = await self.get_market_info()
        for m in markets:
            if m["symbol"] == symbol:
                return m
        return None

    async def get_funding_rate(self, symbol: str) -> dict:
        """Get current funding rate for a symbol.
        Returns: {"funding_rate": float, "next_funding_rate": None}
        """
        markets = await self.get_market_info()
        for m in markets:
            if m["symbol"] == symbol:
                return {
                    "funding_rate": m["funding_rate"],
                    "next_funding_rate": None,
                }
        return {"funding_rate": "0", "next_funding_rate": None}

    async def get_funding_history(self, symbol: str, limit: int = 200,
                                   cursor: str = None) -> dict:
        """Get historical funding rates."""
        import time
        end_ms = int(time.time() * 1000)
        start_ms = end_ms - (limit * 3600 * 1000)  # limit hours back
        data = await self._run_sync(
            self._info.funding_history, symbol, start_ms, end_ms
        )
        return {"data": data, "has_more": False}

    async def get_mark_price(self, symbol: str) -> float:
        """Get current mark price for a symbol."""
        info = await self.get_market_info_for(symbol)
        if info:
            return float(info["mark_price"])
        return 0.0

    async def get_orderbook(self, symbol: str) -> dict:
        """Get L2 order book snapshot."""
        data = await self._run_sync(self._info.l2_snapshot, symbol)
        return data

    # ── Account ──────────────────────────────────────────────────────────────

    async def get_account(self) -> dict:
        """Get account state (balance, equity, positions)."""
        if not self._account:
            return {}
        data = await self._run_sync(self._info.user_state, self._account)
        margin = data.get("marginSummary", {})
        return {
            "balance": margin.get("accountValue", "0"),
            "account_equity": margin.get("accountValue", "0"),
            "available_to_spend": margin.get("totalRawUsd", "0"),
            "total_margin_used": margin.get("totalMarginUsed", "0"),
            "positions_count": len(data.get("assetPositions", [])),
        }

    async def get_positions(self) -> list[dict]:
        """Get all open positions."""
        if not self._account:
            return []
        data = await self._run_sync(self._info.user_state, self._account)
        positions = []
        for pos_data in data.get("assetPositions", []):
            pos = pos_data.get("position", {})
            size = float(pos.get("szi", "0"))
            positions.append({
                "symbol": pos.get("coin", ""),
                "side": "bid" if size > 0 else "ask",
                "amount": str(abs(size)),
                "entry_price": pos.get("entryPx", "0"),
                "margin": pos.get("marginUsed", "0"),
                "unrealized_pnl": pos.get("unrealizedPnl", "0"),
                "leverage": pos.get("leverage", {}).get("value", "1"),
            })
        return positions

    async def get_position(self, symbol: str) -> Optional[dict]:
        """Get position for a specific symbol."""
        positions = await self.get_positions()
        for p in positions:
            if p["symbol"] == symbol:
                return p
        return None

    async def get_account_funding_history(self, limit: int = 100,
                                           cursor: str = None) -> dict:
        """Get user's funding payment history."""
        import time
        end_ms = int(time.time() * 1000)
        start_ms = end_ms - (limit * 3600 * 1000)
        data = await self._run_sync(
            self._info.user_funding_history, self._account, start_ms, end_ms
        )
        return {"data": data, "has_more": False}

    # ── Trading ──────────────────────────────────────────────────────────────

    async def update_leverage(self, symbol: str, leverage: int = 1) -> dict:
        """Set leverage for a symbol."""
        if not self._exchange:
            raise RuntimeError("No signer configured — read-only mode")
        await self._ensure_meta()
        idx = self._get_asset_idx(symbol)
        if idx < 0:
            raise ValueError(f"Unknown symbol: {symbol}")

        result = await self._run_sync(
            self._exchange.update_leverage,
            leverage, symbol, is_cross=True
        )
        logger.info(f"[{symbol}] Leverage set to {leverage}x")
        return result

    async def place_market_order(
        self, symbol: str, side: str, qty: float,
        slippage_percent: float = 1.0, reduce_only: bool = False
    ) -> dict:
        """Place a market order.
        side: "bid" (buy/long) or "ask" (sell/short)
        """
        if not self._exchange:
            raise RuntimeError("No signer configured — read-only mode")

        # Round qty to the asset's szDecimals to avoid float_to_wire error
        await self._ensure_meta()
        sz_decimals = 0
        for asset in self._meta_cache.get("universe", []):
            if asset["name"] == symbol:
                sz_decimals = asset.get("szDecimals", 0)
                break
        import math
        qty = math.floor(qty * 10**sz_decimals) / 10**sz_decimals
        if qty <= 0:
            raise RuntimeError(f"Order qty rounds to 0 for {symbol} (szDecimals={sz_decimals})")

        is_buy = (side == "bid")

        result = await self._run_sync(
            self._exchange.market_open if not reduce_only else self._exchange.market_close,
            symbol, is_buy, qty, None, slippage_percent / 100
        )

        status = result.get("status", "unknown")
        if status == "ok":
            fills = result.get("response", {}).get("data", {}).get("statuses", [])
            logger.info(f"[{symbol}] Market order {side} {qty:.6f} — OK | fills={len(fills)}")
        else:
            error_msg = result.get("response", str(result))
            raise RuntimeError(f"Order failed: {error_msg}")

        return result

    async def get_trade_history(self, limit: int = 100) -> list:
        """Get recent fills."""
        if not self._account:
            return []
        data = await self._run_sync(
            self._info.user_fills, self._account
        )
        return data[:limit] if data else []

    async def get_account_settings(self) -> dict:
        """Get account settings (not directly supported, return defaults)."""
        return {"leverage_mode": "cross"}

    # ── Spot Trading ─────────────────────────────────────────────────────────

    async def _ensure_spot_meta(self):
        """Load spot token metadata if not cached."""
        if hasattr(self, '_spot_meta_cache') and self._spot_meta_cache:
            return
        data = await self._run_sync(self._info.spot_meta_and_asset_ctxs)
        self._spot_meta_cache = data[0]  # tokens + universe

    async def get_spot_balance(self, coin: str) -> float:
        """Get spot balance for a specific coin."""
        if not self._account:
            return 0.0
        data = await self._run_sync(self._info.spot_user_state, self._account)
        for bal in data.get("balances", []):
            if bal.get("coin") == coin:
                return float(bal.get("total", "0"))
        return 0.0

    async def place_spot_market_order(
        self, symbol: str, is_buy: bool, qty: float,
        slippage_percent: float = 1.0
    ) -> dict:
        """Place a spot market order using the perp exchange's order method.
        Hyperliquid spot uses asset index = 10000 + token_index.
        """
        if not self._exchange:
            raise RuntimeError("No signer configured — read-only mode")

        import math
        await self._ensure_spot_meta()

        # Find the spot token's szDecimals
        sz_decimals = 2  # default
        token_index = None
        for token in self._spot_meta_cache.get("tokens", []):
            if token.get("name") == symbol:
                sz_decimals = token.get("szDecimals", 2)
                token_index = token.get("index")
                break

        if token_index is None:
            raise ValueError(f"Spot token not found: {symbol}")

        # Round qty
        qty = math.floor(qty * 10**sz_decimals) / 10**sz_decimals
        if qty <= 0:
            raise RuntimeError(f"Spot order qty rounds to 0 for {symbol}")

        # Use the SDK's order method with spot notation
        # Spot pairs use format like "@150" for token index 150
        # The SDK market_open works with coin name for spot too
        spot_coin = f"{symbol}"

        # Get mid price for limit calculation
        try:
            all_mids = await self._run_sync(self._info.all_mids)
            mid_price = float(all_mids.get(f"{symbol}", 0))
        except Exception:
            mid_price = 0

        if mid_price <= 0:
            raise RuntimeError(f"Cannot get spot mid price for {symbol}")

        # Calculate limit price with slippage
        if is_buy:
            limit_price = mid_price * (1 + slippage_percent / 100)
        else:
            limit_price = mid_price * (1 - slippage_percent / 100)

        # Round price to 5 significant figures (Hyperliquid requirement)
        limit_price = float(f"{limit_price:.5g}")

        # Place order via SDK - spot uses the order method directly
        order_result = await self._run_sync(
            self._exchange.order,
            spot_coin,  # coin name
            is_buy,
            qty,
            limit_price,
            {"limit": {"tif": "Ioc"}},  # IOC = immediate or cancel (market-like)
        )

        status = order_result.get("status", "unknown")
        side_str = "BUY" if is_buy else "SELL"
        if status == "ok":
            statuses = order_result.get("response", {}).get("data", {}).get("statuses", [])
            logger.info(f"[{symbol}] Spot {side_str} {qty} — OK | statuses={statuses}")
        else:
            error_msg = order_result.get("response", str(order_result))
            raise RuntimeError(f"Spot order failed: {error_msg}")

        return order_result

    # ── Cleanup ──────────────────────────────────────────────────────────────

    async def close(self):
        """Cleanup resources."""
        pass
