"""Swing Desk — domain contracts.

Every value the UI renders as market state comes from a typed record produced
by the data layer (demo adapter now, MT5 bridge later). The UI never invents
values.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class Verdict(str, Enum):
    ACTIVE = "ACTIVE"
    WATCHING = "WATCHING"
    INVALID = "INVALID"
    NOT_PRESENT = "NOT_PRESENT"


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NONE = "NONE"


class UniverseScope(str, Enum):
    ALL = "ALL"
    MARKET_WATCH = "MARKET_WATCH"
    MAPPED = "MAPPED"
    ACTIVE_SETUPS = "ACTIVE_SETUPS"


class LifecycleState(str, Enum):
    SCANNING = "SCANNING"
    WATCHING = "WATCHING"
    THESIS = "THESIS"
    WAITING = "WAITING"
    TRIGGERED = "TRIGGERED"
    OPEN = "OPEN"
    MANAGING = "MANAGING"
    CLOSED = "CLOSED"
    REVIEW = "REVIEW"


# Valid forward transitions (human-confirmed; never automatic).
LIFECYCLE_TRANSITIONS: dict[LifecycleState, list[LifecycleState]] = {
    LifecycleState.SCANNING: [LifecycleState.WATCHING],
    LifecycleState.WATCHING: [LifecycleState.THESIS, LifecycleState.SCANNING],
    LifecycleState.THESIS: [LifecycleState.WAITING, LifecycleState.SCANNING],
    LifecycleState.WAITING: [LifecycleState.TRIGGERED, LifecycleState.THESIS],
    LifecycleState.TRIGGERED: [LifecycleState.OPEN, LifecycleState.WAITING],
    LifecycleState.OPEN: [LifecycleState.MANAGING, LifecycleState.CLOSED],
    LifecycleState.MANAGING: [LifecycleState.CLOSED, LifecycleState.OPEN],
    LifecycleState.CLOSED: [LifecycleState.REVIEW],
    LifecycleState.REVIEW: [],
}


@dataclass(frozen=True)
class Bar:
    time_utc: datetime
    open: float
    high: float
    low: float
    close: float
    tick_volume: int = 0
    spread: int | None = None
    real_volume: int | None = None


@dataclass(frozen=True)
class ContractSpec:
    """Canonical broker contract. Only this type reads raw contract fields."""
    digits: int
    point: float
    tick_size: float
    tick_value: float          # account-currency value of one tick per lot
    contract_size: float
    volume_min: float
    volume_max: float
    volume_step: float
    stops_level_points: int
    freeze_level_points: int
    trade_mode: str = "FULL"
    filling_mode: str = "FOK"


@dataclass(frozen=True)
class SymbolRecord:
    broker_symbol: str
    canonical_name: str
    family: str
    asset_class: str
    base_currency: str
    profit_currency: str
    mapping_source: str
    mapping_confidence: float
    visible_in_market_watch: bool
    contract: ContractSpec
    bid: float = 0.0
    ask: float = 0.0
    timeframes: tuple[str, ...] = ("H1", "H4", "D1", "W1")


@dataclass(frozen=True)
class Reason:
    rule_key: str
    text: str
    weight: float = 1.0


@dataclass(frozen=True)
class EvidenceLevel:
    price: float
    label: str
    kind: str = "level"        # level | zone
    upper: float | None = None


@dataclass(frozen=True)
class EngineResult:
    engine_id: str
    verdict: Verdict
    strength: float            # 0..100, decomposed into reasons
    direction: Direction
    reasons: list[Reason] = field(default_factory=list)
    evidence: list[EvidenceLevel] = field(default_factory=list)
    timeframes_used: list[str] = field(default_factory=list)
    computed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    spec_version: str = "demo-1.0"


@dataclass
class Plan:
    id: str
    broker_symbol: str
    canonical_name: str
    direction: str             # LONG | SHORT
    entry: float
    stop: float
    target: float
    risk_percent: float
    volume: float
    thesis: str
    state: LifecycleState
    created_at: str
    updated_at: str
    engine_snapshot: str = ""  # JSON of engine results at planning time
    actual_fill: float | None = None
    realised_r: float | None = None
    behaviour_flags: list[str] = field(default_factory=list)
    review_note: str = ""
    review_completed: bool = False
    closed_at: str | None = None


@dataclass
class Position:
    ticket: int
    broker_symbol: str
    canonical_name: str
    direction: str
    volume: float
    entry: float
    stop: float
    take_profit: float
    current_price: float
    profit: float


@dataclass
class AlertRule:
    id: str
    broker_symbol: str
    kind: str                  # price_touch_above | price_touch_below | session_open
    level: float
    note: str
    enabled: bool
    created_at: str
    fired_at: str | None = None


@dataclass
class CalendarEvent:
    time_utc: datetime
    title: str
    currency: str
    impact: str                # HIGH | MEDIUM | LOW
    zone: str
    affects: tuple[str, ...]


@dataclass
class SessionWindow:
    label: str
    canonical_tz: str
    start_local: str
    end_local: str
    weekdays: tuple[int, ...]


DEFAULT_SESSIONS: tuple[SessionWindow, ...] = (
    SessionWindow("New York Setup", "America/New_York", "08:30", "11:30", (0, 1, 2, 3, 4)),
    SessionWindow("London Kill Zone", "Europe/London", "08:00", "10:00", (0, 1, 2, 3, 4)),
    SessionWindow("Asian Range", "America/New_York", "20:00", "00:00", (0, 1, 2, 3, 4)),
)
