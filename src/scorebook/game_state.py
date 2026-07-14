"""Pure domain state machine for scoring a softball game.

No I/O, no hardware dependencies — this module is importable and
testable in complete isolation from the Kindle/display/input layers.

Key modeling decisions (see docs/design.md, "Tier B" scoring fidelity):

- **Force-advance-only, not a full baserunning simulation.** Existing
  runners can never be thrown out attempting a discretionary advance
  (no "runner thrown out at third") — the only ways a runner is
  removed from the bases are (a) a walk/HBP force chain, (b) scoring,
  or (c) being the explicitly-designated extra out on a double play or
  fielder's choice. This keeps input burden low on a touchscreen while
  still deriving runs/RBI/base-state automatically.
- **Every run scored counts as an RBI, with no exceptions** for
  errors, fielder's choices, or double plays. This is a deliberate
  departure from traditional scorekeeping (which withholds RBI in
  those cases) — a simplifying product decision, not an oversight.
- **The opponent's offense is tracked at line-score level only**
  (`record_opponent_half` takes a single run total). We never track
  opponent batters or baserunners, which is why `outs`/`bases` reset
  to empty at the boundary of every half-inning regardless of which
  side is transitioning.
- **Whole roster bats.** The lineup is an append-only, uncapped list;
  the batting-order cursor rotates modulo the *current* lineup length,
  so a batter added mid-game slots in at the end without disrupting
  whoever is currently up.
- **Undo is replay-based, not inverse-operation-based.** Every mutation
  is recorded as an event in an append-only log; `undo()` drops the
  last event and rebuilds all derived state from scratch by replaying
  the remaining events in order. This makes undo correct-by-construction
  for every event type, including undoing an `end_game()`.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple, Union


class Side(Enum):
    HOME = "home"
    AWAY = "away"


class Half(Enum):
    TOP = "top"  # away team bats
    BOTTOM = "bottom"  # home team bats


class Result(Enum):
    SINGLE = "1B"
    DOUBLE = "2B"
    TRIPLE = "3B"
    HOME_RUN = "HR"
    WALK = "BB"
    INTENTIONAL_WALK = "IBB"
    HIT_BY_PITCH = "HBP"
    STRIKEOUT_SWINGING = "K"
    STRIKEOUT_LOOKING = "KL"
    IN_PLAY_OUT = "IP_OUT"
    FIELDERS_CHOICE = "FC"
    ERROR = "E"
    SACRIFICE = "SAC"
    SACRIFICE_FLY = "SF"
    DOUBLE_PLAY = "DP"
    REACHED_ON_ERROR = "ROE"


class Destination(Enum):
    FIRST = "1"
    SECOND = "2"
    THIRD = "3"
    HOME = "H"  # scored
    OUT = "OUT"


# Ordering used to reject backward runner movement (batter starts
# "before FIRST", so any destination is a forward move for the batter).
_BASE_ADVANCE_ORDER = {
    Destination.FIRST: 1,
    Destination.SECOND: 2,
    Destination.THIRD: 3,
    Destination.HOME: 4,
}

_CURRENT_BASE_ORDER = {"first": 1, "second": 2, "third": 3}
_CURRENT_BASE_DESTINATION = {
    "first": Destination.FIRST,
    "second": Destination.SECOND,
    "third": Destination.THIRD,
}

_MUST_BE_OUT = frozenset(
    {
        Result.STRIKEOUT_SWINGING,
        Result.STRIKEOUT_LOOKING,
        Result.IN_PLAY_OUT,
        Result.SACRIFICE,
        Result.SACRIFICE_FLY,
        Result.DOUBLE_PLAY,
    }
)
_MUST_BE_FIRST = frozenset({Result.SINGLE, Result.WALK, Result.INTENTIONAL_WALK, Result.HIT_BY_PITCH})
_MUST_BE_SECOND = frozenset({Result.DOUBLE})
_MUST_BE_THIRD = frozenset({Result.TRIPLE})
_MUST_BE_HOME = frozenset({Result.HOME_RUN})
_MUST_NOT_BE_OUT = frozenset({Result.FIELDERS_CHOICE, Result.ERROR, Result.REACHED_ON_ERROR})

_RUNNER_OUT_ALLOWED = frozenset({Result.DOUBLE_PLAY, Result.FIELDERS_CHOICE})

_WALK_LIKE = frozenset({Result.WALK, Result.INTENTIONAL_WALK, Result.HIT_BY_PITCH})

_FIELDER_REQUIRED = frozenset(
    {
        Result.IN_PLAY_OUT,
        Result.FIELDERS_CHOICE,
        Result.SACRIFICE,
        Result.SACRIFICE_FLY,
        Result.DOUBLE_PLAY,
    }
)


@dataclass(frozen=True)
class BaseState:
    first: Optional[str] = None  # occupant batter_id or None
    second: Optional[str] = None
    third: Optional[str] = None

    @property
    def is_empty(self) -> bool:
        return self.first is None and self.second is None and self.third is None

    def occupied_bases(self) -> Tuple[str, ...]:
        """Names of currently-occupied bases, in first/second/third order."""
        return tuple(
            name
            for name in ("first", "second", "third")
            if getattr(self, name) is not None
        )


@dataclass(frozen=True)
class PlateAppearanceRecord:
    batter_id: str
    result: Result
    advances: Mapping[str, Destination]
    fielder_position: Optional[int]
    outs_on_play: int
    runs_scored: Tuple[str, ...]
    rbi: int
    base_state_before: BaseState
    base_state_after: BaseState
    inning: int
    half: Half


@dataclass(frozen=True)
class AddBatterEvent:
    batter_id: str


@dataclass(frozen=True)
class OpponentHalfEvent:
    runs: int


@dataclass(frozen=True)
class EndGameEvent:
    pass


_Event = Union[PlateAppearanceRecord, AddBatterEvent, OpponentHalfEvent, EndGameEvent]


def _walk_force_advances(bases: BaseState) -> Dict[str, Destination]:
    """Classic walk/HBP force-chain, keyed by occupied existing runners only.

    Shared by `default_advances` and `commit_plate_appearance` validation
    so the two can never disagree about what's forced vs. a required stay.
    """
    advances: Dict[str, Destination] = {}
    if bases.first is not None:
        advances["first"] = Destination.SECOND
    if bases.second is not None:
        advances["second"] = Destination.THIRD if bases.first is not None else Destination.SECOND
    if bases.third is not None:
        advances["third"] = (
            Destination.HOME
            if (bases.first is not None and bases.second is not None)
            else Destination.THIRD
        )
    return advances


def _stay_advances(bases: BaseState) -> Dict[str, Destination]:
    """Default 'no change' advance for every currently-occupied base."""
    return {name: _CURRENT_BASE_DESTINATION[name] for name in bases.occupied_bases()}


class GameState:
    """Mutable domain state machine for one team's half of a softball game."""

    def __init__(self, our_side: Side, lineup: Sequence[str] = ()) -> None:
        self._our_side = our_side
        self._initial_lineup: Tuple[str, ...] = tuple(lineup)
        self._events: List[_Event] = []
        self._reset_derived_state()

    # ------------------------------------------------------------------
    # derived-state reset / replay
    # ------------------------------------------------------------------

    def _reset_derived_state(self) -> None:
        self._inning = 1
        self._half = Half.TOP
        self._outs = 0
        self._bases = BaseState()
        self._our_score = 0
        self._opponent_score = 0
        self._lineup: List[str] = list(self._initial_lineup)
        self._next_batter_index = 0
        self._is_game_over = False

    def _replay(self) -> None:
        self._reset_derived_state()
        for event in self._events:
            self._apply(event)

    def _apply(self, event: _Event) -> None:
        if isinstance(event, PlateAppearanceRecord):
            self._apply_plate_appearance(event)
        elif isinstance(event, OpponentHalfEvent):
            self._apply_opponent_half(event)
        elif isinstance(event, AddBatterEvent):
            self._lineup.append(event.batter_id)
        elif isinstance(event, EndGameEvent):
            self._is_game_over = True
        else:  # pragma: no cover - defensive
            raise TypeError(f"unknown event type: {type(event)!r}")

    def _apply_plate_appearance(self, record: PlateAppearanceRecord) -> None:
        self._our_score += len(record.runs_scored)
        self._outs += record.outs_on_play
        self._bases = record.base_state_after
        self._next_batter_index = (self._next_batter_index + 1) % len(self._lineup)
        if self._outs >= 3:
            self._end_half_inning()

    def _apply_opponent_half(self, event: OpponentHalfEvent) -> None:
        self._opponent_score += event.runs
        self._end_half_inning()

    def _end_half_inning(self) -> None:
        self._outs = 0
        self._bases = BaseState()
        if self._half is Half.TOP:
            self._half = Half.BOTTOM
        else:
            self._half = Half.TOP
            self._inning += 1

    # ------------------------------------------------------------------
    # queries
    # ------------------------------------------------------------------

    @property
    def inning(self) -> int:
        return self._inning

    @property
    def half(self) -> Half:
        return self._half

    @property
    def outs(self) -> int:
        return self._outs

    @property
    def bases(self) -> BaseState:
        return self._bases

    @property
    def our_score(self) -> int:
        return self._our_score

    @property
    def opponent_score(self) -> int:
        return self._opponent_score

    @property
    def is_our_turn(self) -> bool:
        our_batting_half = Half.TOP if self._our_side is Side.AWAY else Half.BOTTOM
        return self._half is our_batting_half

    @property
    def current_batter(self) -> Optional[str]:
        if not self._lineup:
            return None
        return self._lineup[self._next_batter_index]

    @property
    def lineup(self) -> Tuple[str, ...]:
        return tuple(self._lineup)

    @property
    def history(self) -> Tuple[_Event, ...]:
        return tuple(self._events)

    @property
    def is_game_over(self) -> bool:
        return self._is_game_over

    # ------------------------------------------------------------------
    # mutation
    # ------------------------------------------------------------------

    def add_batter(self, batter_id: str) -> None:
        if self._is_game_over:
            raise ValueError("cannot add a batter after the game has ended")
        event = AddBatterEvent(batter_id=batter_id)
        self._apply(event)
        self._events.append(event)

    def default_advances(self, result: Result) -> Dict[str, Destination]:
        bases = self._bases
        if result is Result.SINGLE:
            return {"batter": Destination.FIRST, **_stay_advances(bases)}
        if result is Result.DOUBLE:
            return {"batter": Destination.SECOND, **_stay_advances(bases)}
        if result is Result.TRIPLE:
            return {"batter": Destination.THIRD, **_stay_advances(bases)}
        if result is Result.HOME_RUN:
            forced_home = {name: Destination.HOME for name in bases.occupied_bases()}
            return {"batter": Destination.HOME, **forced_home}
        if result in _WALK_LIKE:
            return {"batter": Destination.FIRST, **_walk_force_advances(bases)}
        if result in (Result.STRIKEOUT_SWINGING, Result.STRIKEOUT_LOOKING, Result.IN_PLAY_OUT):
            return {"batter": Destination.OUT, **_stay_advances(bases)}
        if result is Result.SACRIFICE:
            return {"batter": Destination.OUT, **_stay_advances(bases)}
        if result is Result.SACRIFICE_FLY:
            advances = {"batter": Destination.OUT, **_stay_advances(bases)}
            if bases.third is not None:
                advances["third"] = Destination.HOME
            return advances
        if result is Result.FIELDERS_CHOICE:
            return {"batter": Destination.FIRST, **_stay_advances(bases)}
        if result in (Result.ERROR, Result.REACHED_ON_ERROR):
            return {"batter": Destination.FIRST, **_stay_advances(bases)}
        if result is Result.DOUBLE_PLAY:
            advances = {"batter": Destination.OUT, **_stay_advances(bases)}
            if bases.first is not None:
                advances["first"] = Destination.OUT
            return advances
        raise AssertionError(f"unhandled result type: {result!r}")  # pragma: no cover

    def commit_plate_appearance(
        self,
        result: Result,
        advances: Mapping[str, Destination],
        fielder_position: Optional[int] = None,
    ) -> PlateAppearanceRecord:
        if self._is_game_over:
            raise ValueError("cannot record a plate appearance after the game has ended")
        if not self.is_our_turn:
            raise ValueError("cannot record a plate appearance during the opponent's half-inning")
        batter_id = self.current_batter
        if batter_id is None:
            raise ValueError("cannot record a plate appearance with an empty lineup")

        bases_before = self._bases
        self._validate_advances(result, advances, bases_before)
        self._validate_fielder_position(result, fielder_position)

        outs_on_play = sum(1 for dest in advances.values() if dest is Destination.OUT)

        occupant_of = {"batter": batter_id, **{
            name: getattr(bases_before, name) for name in bases_before.occupied_bases()
        }}

        runs_scored = tuple(
            occupant_of[key]
            for key in ("first", "second", "third", "batter")
            if key in advances and advances[key] is Destination.HOME
        )
        rbi = len(runs_scored)

        base_positions: Dict[str, Optional[str]] = {"first": None, "second": None, "third": None}
        for key, dest in advances.items():
            if dest in (Destination.FIRST, Destination.SECOND, Destination.THIRD):
                target = {"1": "first", "2": "second", "3": "third"}[dest.value]
                base_positions[target] = occupant_of[key]

        base_state_after = BaseState(
            first=base_positions["first"],
            second=base_positions["second"],
            third=base_positions["third"],
        )

        record = PlateAppearanceRecord(
            batter_id=batter_id,
            result=result,
            advances=dict(advances),
            fielder_position=fielder_position,
            outs_on_play=outs_on_play,
            runs_scored=runs_scored,
            rbi=rbi,
            base_state_before=bases_before,
            base_state_after=base_state_after,
            inning=self._inning,
            half=self._half,
        )

        self._apply(record)
        self._events.append(record)
        return record

    def record_opponent_half(self, runs: int) -> None:
        if self._is_game_over:
            raise ValueError("cannot record the opponent's half after the game has ended")
        if self.is_our_turn:
            raise ValueError("cannot record the opponent's half during our own half-inning")
        if runs < 0:
            raise ValueError("runs must be >= 0")
        event = OpponentHalfEvent(runs=runs)
        self._apply(event)
        self._events.append(event)

    def undo(self) -> None:
        if not self._events:
            raise ValueError("nothing to undo")
        self._events.pop()
        self._replay()

    def end_game(self) -> None:
        if self._is_game_over:
            raise ValueError("game is already over")
        event = EndGameEvent()
        self._apply(event)
        self._events.append(event)

    # ------------------------------------------------------------------
    # validation helpers
    # ------------------------------------------------------------------

    def _validate_advances(
        self,
        result: Result,
        advances: Mapping[str, Destination],
        bases_before: BaseState,
    ) -> None:
        occupied = bases_before.occupied_bases()
        expected_keys = {"batter", *occupied}
        actual_keys = set(advances.keys())
        missing = expected_keys - actual_keys
        extra = actual_keys - expected_keys
        if missing:
            raise ValueError(f"advances is missing required key(s): {sorted(missing)}")
        if extra:
            raise ValueError(f"advances has extraneous key(s) not currently on base: {sorted(extra)}")

        batter_dest = advances["batter"]
        self._validate_batter_destination(result, batter_dest)

        runner_outs = 0
        for name in occupied:
            dest = advances[name]
            if dest is Destination.OUT:
                runner_outs += 1
                if result not in _RUNNER_OUT_ALLOWED:
                    raise ValueError(
                        f"runner on {name} cannot be marked OUT for result {result.value} "
                        "(force-advance-only model: no discretionary outs on the bases)"
                    )
            else:
                current_order = _CURRENT_BASE_ORDER[name]
                dest_order = _BASE_ADVANCE_ORDER[dest]
                if dest_order < current_order:
                    raise ValueError(
                        f"runner on {name} cannot move backward to {dest.value}"
                    )

        if result is Result.DOUBLE_PLAY and runner_outs != 1:
            raise ValueError(
                f"double play requires exactly one runner OUT in addition to the batter, got {runner_outs}"
            )
        if result is Result.FIELDERS_CHOICE and runner_outs != 1:
            raise ValueError(
                f"fielder's choice requires exactly one runner OUT, got {runner_outs}"
            )

        if result is Result.HOME_RUN:
            expected = {name: Destination.HOME for name in occupied}
            actual = {name: advances[name] for name in occupied}
            if actual != expected:
                raise ValueError(
                    f"home run requires every existing runner to score; expected {expected}, got {actual}"
                )

        if result in _WALK_LIKE:
            expected = _walk_force_advances(bases_before)
            actual = {name: advances[name] for name in occupied}
            if actual != expected:
                raise ValueError(
                    f"{result.value} force-chain mismatch: expected {expected}, got {actual}"
                )

        self._validate_no_collisions(advances, occupied)

    def _validate_batter_destination(self, result: Result, batter_dest: Destination) -> None:
        if result in _MUST_BE_OUT and batter_dest is not Destination.OUT:
            raise ValueError(f"{result.value} requires the batter to be OUT, got {batter_dest.value}")
        if result in _MUST_BE_FIRST and batter_dest is not Destination.FIRST:
            raise ValueError(f"{result.value} requires the batter to reach FIRST, got {batter_dest.value}")
        if result in _MUST_BE_SECOND and batter_dest is not Destination.SECOND:
            raise ValueError(f"{result.value} requires the batter to reach SECOND, got {batter_dest.value}")
        if result in _MUST_BE_THIRD and batter_dest is not Destination.THIRD:
            raise ValueError(f"{result.value} requires the batter to reach THIRD, got {batter_dest.value}")
        if result in _MUST_BE_HOME and batter_dest is not Destination.HOME:
            raise ValueError(f"{result.value} requires the batter to reach HOME, got {batter_dest.value}")
        if result in _MUST_NOT_BE_OUT and batter_dest is Destination.OUT:
            raise ValueError(f"{result.value} requires the batter to reach base safely, got OUT")

    def _validate_no_collisions(self, advances: Mapping[str, Destination], occupied: Sequence[str]) -> None:
        occupants_by_base: Dict[Destination, int] = {}
        for key in ("batter", *occupied):
            dest = advances[key]
            if dest in (Destination.FIRST, Destination.SECOND, Destination.THIRD):
                occupants_by_base[dest] = occupants_by_base.get(dest, 0) + 1
        collisions = {dest: count for dest, count in occupants_by_base.items() if count > 1}
        if collisions:
            raise ValueError(f"advances produce a base collision: {collisions}")

    def _validate_fielder_position(self, result: Result, fielder_position: Optional[int]) -> None:
        if result in _FIELDER_REQUIRED:
            if fielder_position is None or not (1 <= fielder_position <= 9):
                raise ValueError(
                    f"{result.value} requires fielder_position in 1..9, got {fielder_position!r}"
                )
        else:
            if fielder_position is not None:
                raise ValueError(
                    f"{result.value} does not accept a fielder_position, got {fielder_position!r}"
                )
