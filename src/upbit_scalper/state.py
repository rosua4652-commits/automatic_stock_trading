from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class BotPosition:
    market: str
    entry_price: float
    volume: float
    budget_krw: float
    take_profit_price: float
    stop_loss_price: float
    trailing_stop_pct: float
    highest_price: float
    opened_at: str
    mode: str


@dataclass
class BotState:
    realized_pnl_krw: float = 0.0
    consecutive_losses: int = 0
    position: BotPosition | None = None


class StateStore:
    def __init__(self, path: str = "data/bot_state.json") -> None:
        self.path = Path(path)

    def load(self) -> BotState:
        if not self.path.exists():
            return BotState()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        position_data = data.get("position")
        position = BotPosition(**position_data) if position_data else None
        return BotState(
            realized_pnl_krw=float(data.get("realized_pnl_krw", 0.0)),
            consecutive_losses=int(data.get("consecutive_losses", 0)),
            position=position,
        )

    def save(self, state: BotState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(state), ensure_ascii=False, indent=2), encoding="utf-8")
