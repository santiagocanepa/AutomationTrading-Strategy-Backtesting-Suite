"""Portfolio monitor — real-time state tracking and alerting.

Watches portfolio state, strategy health, and triggers alerts
when thresholds are breached.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from loguru import logger


class AlertLevel(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Alert:
    """A portfolio alert."""

    level: AlertLevel
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    strategy_id: str | None = None
    metric: str | None = None
    value: float | None = None
    threshold: float | None = None


class PortfolioMonitor:
    """Monitor portfolio health and generate alerts.

    Tracks equity, drawdown, strategy drift, and correlation changes.
    """

    def __init__(
        self,
        *,
        max_drawdown_warning: float = 10.0,
        max_drawdown_critical: float = 20.0,
        max_strategy_drift: float = 0.20,
        max_correlation_increase: float = 0.15,
        check_interval_bars: int = 100,
    ) -> None:
        self._dd_warn = max_drawdown_warning
        self._dd_crit = max_drawdown_critical
        self._drift_th = max_strategy_drift
        self._corr_th = max_correlation_increase
        self._interval = check_interval_bars
        self._alerts: list[Alert] = []
        self._bar_count: int = 0
        self._baseline_weights: dict[str, float] | None = None
        self._baseline_correlation: float | None = None

    def set_baseline(
        self,
        weights: dict[str, float],
        avg_correlation: float,
    ) -> None:
        """Set baseline metrics for drift detection."""
        self._baseline_weights = dict(weights)
        self._baseline_correlation = avg_correlation

    def check(
        self,
        *,
        equity: float,
        peak_equity: float,
        current_weights: dict[str, float] | None = None,
        current_correlation: float | None = None,
        strategy_returns: dict[str, float] | None = None,
    ) -> list[Alert]:
        """Run monitoring checks and return new alerts."""
        self._bar_count += 1
        new_alerts: list[Alert] = []

        # Drawdown check
        if peak_equity > 0:
            dd_pct = (peak_equity - equity) / peak_equity * 100.0
            if dd_pct >= self._dd_crit:
                alert = Alert(
                    level=AlertLevel.CRITICAL,
                    message=f"Portfolio drawdown {dd_pct:.1f}% exceeds critical threshold {self._dd_crit:.1f}%",
                    metric="drawdown_pct",
                    value=dd_pct,
                    threshold=self._dd_crit,
                )
                new_alerts.append(alert)
            elif dd_pct >= self._dd_warn:
                alert = Alert(
                    level=AlertLevel.WARNING,
                    message=f"Portfolio drawdown {dd_pct:.1f}% exceeds warning threshold {self._dd_warn:.1f}%",
                    metric="drawdown_pct",
                    value=dd_pct,
                    threshold=self._dd_warn,
                )
                new_alerts.append(alert)

        # Weight drift check (periodic)
        if (
            self._bar_count % self._interval == 0
            and current_weights is not None
            and self._baseline_weights is not None
        ):
            for sid, baseline_w in self._baseline_weights.items():
                current_w = current_weights.get(sid, 0.0)
                drift = abs(current_w - baseline_w)
                if drift > self._drift_th:
                    alert = Alert(
                        level=AlertLevel.WARNING,
                        message=f"Strategy {sid} weight drifted by {drift:.3f} from baseline",
                        strategy_id=sid,
                        metric="weight_drift",
                        value=drift,
                        threshold=self._drift_th,
                    )
                    new_alerts.append(alert)

        # Correlation shift check (periodic)
        if (
            self._bar_count % self._interval == 0
            and current_correlation is not None
            and self._baseline_correlation is not None
        ):
            corr_change = current_correlation - self._baseline_correlation
            if corr_change > self._corr_th:
                alert = Alert(
                    level=AlertLevel.WARNING,
                    message=(
                        f"Avg correlation increased by {corr_change:.3f} "
                        f"({self._baseline_correlation:.3f} → {current_correlation:.3f})"
                    ),
                    metric="correlation_shift",
                    value=corr_change,
                    threshold=self._corr_th,
                )
                new_alerts.append(alert)

        self._alerts.extend(new_alerts)
        for alert in new_alerts:
            log_fn = logger.critical if alert.level == AlertLevel.CRITICAL else logger.warning
            log_fn("[{}] {}", alert.level.value.upper(), alert.message)

        return new_alerts

    def get_alerts(
        self,
        level: AlertLevel | None = None,
        last_n: int | None = None,
    ) -> list[Alert]:
        """Return alerts, optionally filtered by level."""
        alerts = self._alerts
        if level is not None:
            alerts = [a for a in alerts if a.level == level]
        if last_n is not None:
            alerts = alerts[-last_n:]
        return alerts

    def clear_alerts(self) -> None:
        """Clear all stored alerts."""
        self._alerts.clear()
