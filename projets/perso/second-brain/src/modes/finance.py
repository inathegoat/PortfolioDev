"""src/modes/finance.py — Finance mode: report analysis, portfolio tracking.

Features:
- Analyze financial reports (ingested PDFs/DOCXs)
- Extract key metrics (revenue, profit, ratios)
- Portfolio tracking with positions and alerts
- Simple alert system for thresholds
"""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class FinancialMetrics:
    revenue: Optional[float] = None
    profit: Optional[float] = None
    margin: Optional[float] = None
    debt_ratio: Optional[float] = None
    growth_rate: Optional[float] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PortfolioPosition:
    ticker: str
    name: str = ""
    shares: float = 0.0
    avg_cost: float = 0.0
    current_price: float = 0.0
    sector: str = ""
    alert_below: Optional[float] = None
    alert_above: Optional[float] = None


@dataclass
class PortfolioSummary:
    positions: List[PortfolioPosition] = field(default_factory=list)
    total_value: float = 0.0
    total_cost: float = 0.0
    total_gain_loss: float = 0.0
    total_gain_loss_pct: float = 0.0
    alerts: List[str] = field(default_factory=list)


class FinanceMode:
    """Financial analysis and portfolio tracking."""

    def __init__(self, llm_client=None, rag_pipeline=None):
        self.llm = llm_client
        self.rag = rag_pipeline
        self._positions: Dict[str, PortfolioPosition] = {}

    # ── Report Analysis ───────────────────────────────────────────────

    def analyze_report(self, document_name: str) -> FinancialMetrics:
        """Extract financial metrics from an ingested financial report."""
        if not self.rag:
            return FinancialMetrics()

        chunks = self.rag.retrieve_only(
            f"{document_name} revenu chiffre d'affaires bénéfice marge ratio dette croissance"
        )

        if not chunks:
            logger.warning(f"No financial data found for {document_name}")
            return FinancialMetrics()

        context = "\n".join(
            c.get("content", c.get("text", ""))[:300]
            for c in chunks[:8]
        )

        prompt = (
            f"Extrais les métriques financières suivantes du rapport ci-dessous. "
            f"Si une métrique n'est pas trouvée, mets null.\n\n"
            f"Format JSON strict :\n"
            f'{{"revenue": 123456, "profit": 12345, "margin_pct": 12.5, '
            f'"debt_ratio": 0.3, "growth_rate_pct": 5.2, "key_insights": ["..."]}}\n\n'
            f"Rapport :\n{context[:3000]}"
        )

        try:
            raw = self.llm.generate(
                prompt=prompt,
                system_prompt="Tu es un analyste financier. Extrais UNIQUEMENT les données présentes. Format JSON.",
                temperature=0.1,
                max_tokens=500,
            )
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0:
                data = json.loads(raw[start:end])
                return FinancialMetrics(
                    revenue=data.get("revenue"),
                    profit=data.get("profit"),
                    margin=data.get("margin_pct"),
                    debt_ratio=data.get("debt_ratio"),
                    growth_rate=data.get("growth_rate_pct"),
                    raw=data,
                )
        except Exception as e:
            logger.warning(f"Report analysis failed: {e}")

        return FinancialMetrics()

    def summarize_report(self, document_name: str) -> str:
        """Generate a summary of a financial report."""
        if not self.rag:
            return "Aucun document analysable."

        chunks = self.rag.retrieve_only(f"{document_name} analyse financière rapport annuel")
        if not chunks:
            return f"Aucune information trouvée pour {document_name}."

        context = "\n".join(
            c.get("content", c.get("text", ""))[:300]
            for c in chunks[:5]
        )

        prompt = (
            f"Résume ce rapport financier en 5 points clés, en français :\n\n"
            f"{context[:2500]}"
        )

        try:
            return self.llm.generate(
                prompt=prompt,
                system_prompt="Tu es un analyste financier. Sois concis et factuel.",
                temperature=0.2,
                max_tokens=400,
            )
        except Exception:
            return "Analyse impossible (LLM indisponible)."

    # ── Portfolio ─────────────────────────────────────────────────────

    def add_position(
        self,
        ticker: str,
        name: str = "",
        shares: float = 0,
        avg_cost: float = 0,
        sector: str = "",
        alert_below: Optional[float] = None,
        alert_above: Optional[float] = None,
    ):
        self._positions[ticker.upper()] = PortfolioPosition(
            ticker=ticker.upper(),
            name=name or ticker,
            shares=shares,
            avg_cost=avg_cost,
            current_price=avg_cost,
            sector=sector,
            alert_below=alert_below,
            alert_above=alert_above,
        )

    def update_price(self, ticker: str, price: float):
        """Update current market price."""
        t = ticker.upper()
        if t in self._positions:
            self._positions[t].current_price = price

    def remove_position(self, ticker: str):
        self._positions.pop(ticker.upper(), None)

    def get_portfolio_summary(self) -> PortfolioSummary:
        """Get portfolio summary with alerts."""
        total_value = 0.0
        total_cost = 0.0
        alerts = []

        for pos in self._positions.values():
            value = pos.shares * pos.current_price
            cost = pos.shares * pos.avg_cost
            total_value += value
            total_cost += cost

            # Check alerts
            price = pos.current_price
            if pos.alert_below and price <= pos.alert_below:
                alerts.append(
                    f"⚠️  {pos.ticker} en dessous de {pos.alert_below:.2f} → {price:.2f}"
                )
            if pos.alert_above and price >= pos.alert_above:
                alerts.append(
                    f"📈 {pos.ticker} au-dessus de {pos.alert_above:.2f} → {price:.2f}"
                )

        gain_loss = total_value - total_cost
        gain_loss_pct = (gain_loss / total_cost * 100) if total_cost > 0 else 0.0

        return PortfolioSummary(
            positions=list(self._positions.values()),
            total_value=round(total_value, 2),
            total_cost=round(total_cost, 2),
            total_gain_loss=round(gain_loss, 2),
            total_gain_loss_pct=round(gain_loss_pct, 2),
            alerts=alerts,
        )

    def format_summary(self, summary: PortfolioSummary) -> str:
        """Format portfolio as readable text."""
        lines = [
            "=" * 50,
            "  PORTEFEUILLE",
            "=" * 50,
            f"Valeur totale : {summary.total_value:,.2f} €",
            f"Coût total    : {summary.total_cost:,.2f} €",
            f"Gain/Perte    : {summary.total_gain_loss:+,.2f} € ({summary.total_gain_loss_pct:+.2f}%)",
            "",
        ]
        if summary.positions:
            lines.append("POSITIONS :")
            for p in summary.positions:
                val = p.shares * p.current_price
                gain = (p.current_price - p.avg_cost) / p.avg_cost * 100 if p.avg_cost else 0
                lines.append(
                    f"  {p.ticker:6s} {p.name:15s} x{p.shares:6.0f} @ {p.avg_cost:8.2f} "
                    f"→ {val:10,.2f} € ({gain:+.1f}%)"
                )
        if summary.alerts:
            lines.append("\n🔔 ALERTES :")
            for a in summary.alerts:
                lines.append(f"  {a}")
        lines.append("=" * 50)
        return "\n".join(lines)
