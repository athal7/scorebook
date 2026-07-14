import pytest

from scorebook.game_state import (
    AddBatterEvent,
    BaseState,
    Destination,
    EndGameEvent,
    GameState,
    Half,
    OpponentHalfEvent,
    PlateAppearanceRecord,
    Result,
    Side,
)


# ----------------------------------------------------------------------
# BaseState basics
# ----------------------------------------------------------------------


def test_base_state_default_is_empty():
    assert BaseState().is_empty


def test_base_state_with_occupant_is_not_empty():
    assert not BaseState(first="alice").is_empty


def test_base_state_occupied_bases_lists_in_order():
    bases = BaseState(first="a", third="c")
    assert bases.occupied_bases() == ("first", "third")


def test_base_state_occupied_bases_empty_when_no_one_on():
    assert BaseState().occupied_bases() == ()


# ----------------------------------------------------------------------
# default_advances — one representative test per Result, plus force-chain
# and conditional-default edge cases
# ----------------------------------------------------------------------


def _game_with_bases(bases: BaseState, our_side: Side = Side.AWAY) -> GameState:
    game = GameState(our_side, lineup=["a", "b", "c", "d"])
    game._bases = bases  # test-only direct seed of internal state
    return game


def test_default_advances_single_sends_batter_to_first_and_others_stay():
    game = _game_with_bases(BaseState(first="r1", second="r2"))
    assert game.default_advances(Result.SINGLE) == {
        "batter": Destination.FIRST,
        "first": Destination.FIRST,
        "second": Destination.SECOND,
    }


def test_default_advances_double_sends_batter_to_second():
    game = _game_with_bases(BaseState(third="r3"))
    assert game.default_advances(Result.DOUBLE) == {
        "batter": Destination.SECOND,
        "third": Destination.THIRD,
    }


def test_default_advances_triple_sends_batter_to_third():
    game = _game_with_bases(BaseState())
    assert game.default_advances(Result.TRIPLE) == {"batter": Destination.THIRD}


def test_default_advances_home_run_forces_every_runner_home():
    game = _game_with_bases(BaseState(first="r1", second="r2", third="r3"))
    assert game.default_advances(Result.HOME_RUN) == {
        "batter": Destination.HOME,
        "first": Destination.HOME,
        "second": Destination.HOME,
        "third": Destination.HOME,
    }


def test_default_advances_walk_bases_loaded_forces_everyone_up():
    game = _game_with_bases(BaseState(first="r1", second="r2", third="r3"))
    assert game.default_advances(Result.WALK) == {
        "batter": Destination.FIRST,
        "first": Destination.SECOND,
        "second": Destination.THIRD,
        "third": Destination.HOME,
    }


def test_default_advances_walk_only_second_occupied_no_force():
    game = _game_with_bases(BaseState(second="r2"))
    assert game.default_advances(Result.WALK) == {
        "batter": Destination.FIRST,
        "second": Destination.SECOND,
    }


def test_default_advances_walk_only_first_occupied_forces_to_second():
    game = _game_with_bases(BaseState(first="r1"))
    assert game.default_advances(Result.WALK) == {
        "batter": Destination.FIRST,
        "first": Destination.SECOND,
    }


def test_default_advances_walk_only_third_occupied_no_force():
    game = _game_with_bases(BaseState(third="r3"))
    assert game.default_advances(Result.WALK) == {
        "batter": Destination.FIRST,
        "third": Destination.THIRD,
    }


def test_default_advances_intentional_walk_matches_walk_force_chain():
    game = _game_with_bases(BaseState(first="r1", second="r2"))
    assert game.default_advances(Result.INTENTIONAL_WALK) == {
        "batter": Destination.FIRST,
        "first": Destination.SECOND,
        "second": Destination.THIRD,
    }


def test_default_advances_hit_by_pitch_matches_walk_force_chain():
    game = _game_with_bases(BaseState(first="r1"))
    assert game.default_advances(Result.HIT_BY_PITCH) == {
        "batter": Destination.FIRST,
        "first": Destination.SECOND,
    }


def test_default_advances_strikeout_swinging_batter_out_others_stay():
    game = _game_with_bases(BaseState(second="r2"))
    assert game.default_advances(Result.STRIKEOUT_SWINGING) == {
        "batter": Destination.OUT,
        "second": Destination.SECOND,
    }


def test_default_advances_strikeout_looking_batter_out():
    game = _game_with_bases(BaseState())
    assert game.default_advances(Result.STRIKEOUT_LOOKING) == {"batter": Destination.OUT}


def test_default_advances_in_play_out_batter_out_others_stay():
    game = _game_with_bases(BaseState(first="r1"))
    assert game.default_advances(Result.IN_PLAY_OUT) == {
        "batter": Destination.OUT,
        "first": Destination.FIRST,
    }


def test_default_advances_sacrifice_batter_out_others_stay():
    game = _game_with_bases(BaseState(third="r3"))
    assert game.default_advances(Result.SACRIFICE) == {
        "batter": Destination.OUT,
        "third": Destination.THIRD,
    }


def test_default_advances_sacrifice_fly_scores_runner_from_third():
    game = _game_with_bases(BaseState(third="r3"))
    assert game.default_advances(Result.SACRIFICE_FLY) == {
        "batter": Destination.OUT,
        "third": Destination.HOME,
    }


def test_default_advances_sacrifice_fly_without_third_occupied_just_stays():
    game = _game_with_bases(BaseState(first="r1"))
    assert game.default_advances(Result.SACRIFICE_FLY) == {
        "batter": Destination.OUT,
        "first": Destination.FIRST,
    }


def test_default_advances_fielders_choice_does_not_default_any_out():
    game = _game_with_bases(BaseState(first="r1"))
    assert game.default_advances(Result.FIELDERS_CHOICE) == {
        "batter": Destination.FIRST,
        "first": Destination.FIRST,
    }


def test_default_advances_error_batter_to_first_others_stay():
    game = _game_with_bases(BaseState(second="r2"))
    assert game.default_advances(Result.ERROR) == {
        "batter": Destination.FIRST,
        "second": Destination.SECOND,
    }


def test_default_advances_reached_on_error_batter_to_first_others_stay():
    game = _game_with_bases(BaseState(second="r2"))
    assert game.default_advances(Result.REACHED_ON_ERROR) == {
        "batter": Destination.FIRST,
        "second": Destination.SECOND,
    }


def test_default_advances_double_play_with_first_occupied_forces_runner_out():
    game = _game_with_bases(BaseState(first="r1", third="r3"))
    assert game.default_advances(Result.DOUBLE_PLAY) == {
        "batter": Destination.OUT,
        "first": Destination.OUT,
        "third": Destination.THIRD,
    }


def test_default_advances_double_play_without_first_occupied_leaves_ambiguous():
    game = _game_with_bases(BaseState(second="r2"))
    assert game.default_advances(Result.DOUBLE_PLAY) == {
        "batter": Destination.OUT,
        "second": Destination.SECOND,
    }


# ----------------------------------------------------------------------
# commit_plate_appearance — happy path per Result
# ----------------------------------------------------------------------


def test_commit_single_advances_batter_only():
    game = GameState(Side.AWAY, lineup=["a"])
    record = game.commit_plate_appearance(Result.SINGLE, {"batter": Destination.FIRST})
    assert record.outs_on_play == 0
    assert record.runs_scored == ()
    assert record.rbi == 0
    assert record.base_state_after == BaseState(first="a")
    assert game.our_score == 0
    assert game.outs == 0


def test_commit_double_scores_runner_from_second():
    game = GameState(Side.AWAY, lineup=["a", "b"])
    game.commit_plate_appearance(Result.SINGLE, {"batter": Destination.FIRST})
    record = game.commit_plate_appearance(
        Result.DOUBLE, {"batter": Destination.SECOND, "first": Destination.HOME}
    )
    assert record.runs_scored == ("a",)
    assert record.rbi == 1
    assert record.base_state_after == BaseState(second="b")
    assert game.our_score == 1


def test_commit_triple_clears_bases_of_scoring_runners():
    game = GameState(Side.AWAY, lineup=["a", "b"])
    game.commit_plate_appearance(Result.SINGLE, {"batter": Destination.FIRST})
    record = game.commit_plate_appearance(
        Result.TRIPLE, {"batter": Destination.THIRD, "first": Destination.HOME}
    )
    assert record.runs_scored == ("a",)
    assert record.base_state_after == BaseState(third="b")


def test_commit_home_run_with_bases_loaded_scores_four():
    game = GameState(Side.AWAY, lineup=["a", "b", "c", "d"])
    game.commit_plate_appearance(Result.SINGLE, {"batter": Destination.FIRST})
    game.commit_plate_appearance(
        Result.SINGLE, {"batter": Destination.FIRST, "first": Destination.SECOND}
    )
    game.commit_plate_appearance(
        Result.SINGLE,
        {"batter": Destination.FIRST, "first": Destination.SECOND, "second": Destination.THIRD},
    )
    record = game.commit_plate_appearance(
        Result.HOME_RUN,
        {
            "batter": Destination.HOME,
            "first": Destination.HOME,
            "second": Destination.HOME,
            "third": Destination.HOME,
        },
    )
    assert set(record.runs_scored) == {"a", "b", "c", "d"}
    assert record.rbi == 4
    assert record.base_state_after == BaseState()
    assert game.our_score == 4


def test_commit_walk_forces_runner_from_first_to_second():
    game = GameState(Side.AWAY, lineup=["a", "b"])
    game.commit_plate_appearance(Result.SINGLE, {"batter": Destination.FIRST})
    record = game.commit_plate_appearance(
        Result.WALK, {"batter": Destination.FIRST, "first": Destination.SECOND}
    )
    assert record.base_state_after == BaseState(first="b", second="a")
    assert record.runs_scored == ()


def test_commit_intentional_walk_same_shape_as_walk():
    game = GameState(Side.AWAY, lineup=["a"])
    record = game.commit_plate_appearance(Result.INTENTIONAL_WALK, {"batter": Destination.FIRST})
    assert record.base_state_after == BaseState(first="a")


def test_commit_hit_by_pitch_same_shape_as_walk():
    game = GameState(Side.AWAY, lineup=["a"])
    record = game.commit_plate_appearance(Result.HIT_BY_PITCH, {"batter": Destination.FIRST})
    assert record.base_state_after == BaseState(first="a")


def test_commit_strikeout_swinging_records_one_out_no_runs():
    game = GameState(Side.AWAY, lineup=["a"])
    record = game.commit_plate_appearance(Result.STRIKEOUT_SWINGING, {"batter": Destination.OUT})
    assert record.outs_on_play == 1
    assert record.base_state_after == BaseState()
    assert game.outs == 1


def test_commit_strikeout_looking_records_one_out():
    game = GameState(Side.AWAY, lineup=["a"])
    record = game.commit_plate_appearance(Result.STRIKEOUT_LOOKING, {"batter": Destination.OUT})
    assert record.outs_on_play == 1


def test_commit_in_play_out_requires_fielder_and_records_out():
    game = GameState(Side.AWAY, lineup=["a"])
    record = game.commit_plate_appearance(
        Result.IN_PLAY_OUT, {"batter": Destination.OUT}, fielder_position=6
    )
    assert record.outs_on_play == 1
    assert record.fielder_position == 6


def test_commit_fielders_choice_puts_out_the_designated_runner():
    game = GameState(Side.AWAY, lineup=["a", "b"])
    game.commit_plate_appearance(Result.SINGLE, {"batter": Destination.FIRST})
    record = game.commit_plate_appearance(
        Result.FIELDERS_CHOICE,
        {"batter": Destination.FIRST, "first": Destination.OUT},
        fielder_position=6,
    )
    assert record.outs_on_play == 1
    assert record.base_state_after == BaseState(first="b")


def test_commit_error_batter_reaches_first_no_out():
    game = GameState(Side.AWAY, lineup=["a"])
    record = game.commit_plate_appearance(Result.ERROR, {"batter": Destination.FIRST})
    assert record.outs_on_play == 0
    assert record.base_state_after == BaseState(first="a")


def test_commit_sacrifice_records_out_and_requires_fielder():
    game = GameState(Side.AWAY, lineup=["a", "b"])
    game.commit_plate_appearance(Result.SINGLE, {"batter": Destination.FIRST})  # a reaches first
    record = game.commit_plate_appearance(
        Result.SACRIFICE,
        {"batter": Destination.OUT, "first": Destination.SECOND},
        fielder_position=1,
    )
    assert record.outs_on_play == 1
    assert record.base_state_after == BaseState(second="a")


def test_commit_sacrifice_fly_scores_runner_from_third():
    game = GameState(Side.AWAY, lineup=["a", "b"])
    game.commit_plate_appearance(
        Result.TRIPLE, {"batter": Destination.THIRD}
    )
    record = game.commit_plate_appearance(
        Result.SACRIFICE_FLY,
        {"batter": Destination.OUT, "third": Destination.HOME},
        fielder_position=8,
    )
    assert record.runs_scored == ("a",)
    assert record.rbi == 1
    assert record.outs_on_play == 1


def test_commit_double_play_records_two_outs():
    game = GameState(Side.AWAY, lineup=["a", "b"])
    game.commit_plate_appearance(Result.SINGLE, {"batter": Destination.FIRST})
    record = game.commit_plate_appearance(
        Result.DOUBLE_PLAY,
        {"batter": Destination.OUT, "first": Destination.OUT},
        fielder_position=4,
    )
    assert record.outs_on_play == 2
    assert record.base_state_after == BaseState()


def test_commit_reached_on_error_batter_reaches_first():
    game = GameState(Side.AWAY, lineup=["a"])
    record = game.commit_plate_appearance(Result.REACHED_ON_ERROR, {"batter": Destination.FIRST})
    assert record.outs_on_play == 0
    assert record.base_state_after == BaseState(first="a")


# ----------------------------------------------------------------------
# RBI-counts-every-run rule (intentional non-traditional behavior)
# ----------------------------------------------------------------------


def test_rbi_credited_on_error_scoring_run_despite_traditional_convention():
    game = GameState(Side.AWAY, lineup=["a", "b"])
    game.commit_plate_appearance(Result.TRIPLE, {"batter": Destination.THIRD})
    record = game.commit_plate_appearance(
        Result.ERROR, {"batter": Destination.FIRST, "third": Destination.HOME}
    )
    # Traditional scorekeeping withholds RBI on an error; this model does not.
    assert record.runs_scored == ("a",)
    assert record.rbi == 1


def test_rbi_credited_on_double_play_with_no_run_is_zero():
    game = GameState(Side.AWAY, lineup=["a", "b"])
    game.commit_plate_appearance(Result.SINGLE, {"batter": Destination.FIRST})
    record = game.commit_plate_appearance(
        Result.DOUBLE_PLAY,
        {"batter": Destination.OUT, "first": Destination.OUT},
        fielder_position=6,
    )
    assert record.outs_on_play == 2
    assert record.runs_scored == ()
    assert record.rbi == 0


def test_rbi_credited_on_fielders_choice_that_also_scores_a_runner_from_third():
    # Runners on first (b) and third (a); the FC takes first, third scores home.
    game = GameState(Side.AWAY, lineup=["a", "b", "c"])
    game.commit_plate_appearance(Result.TRIPLE, {"batter": Destination.THIRD})
    game.commit_plate_appearance(
        Result.SINGLE, {"batter": Destination.FIRST, "third": Destination.THIRD}
    )
    record = game.commit_plate_appearance(
        Result.FIELDERS_CHOICE,
        {"batter": Destination.FIRST, "first": Destination.OUT, "third": Destination.HOME},
        fielder_position=5,
    )
    # Traditional scorekeeping withholds RBI on a fielder's-choice out; this model does not.
    assert record.outs_on_play == 1
    assert record.runs_scored == ("a",)
    assert record.rbi == 1


def test_rbi_credited_on_double_play_that_also_scores_a_runner_from_third():
    # Runners on first (b) and third (a); the DP takes batter+first, third scores home.
    game = GameState(Side.AWAY, lineup=["a", "b", "c"])
    game.commit_plate_appearance(Result.TRIPLE, {"batter": Destination.THIRD})
    game.commit_plate_appearance(
        Result.SINGLE, {"batter": Destination.FIRST, "third": Destination.THIRD}
    )
    record = game.commit_plate_appearance(
        Result.DOUBLE_PLAY,
        {"batter": Destination.OUT, "first": Destination.OUT, "third": Destination.HOME},
        fielder_position=4,
    )
    # Traditional scorekeeping withholds RBI on a GIDP; this model does not.
    assert record.outs_on_play == 2
    assert record.runs_scored == ("a",)
    assert record.rbi == 1


# ----------------------------------------------------------------------
# Validation failures — one per violation type
# ----------------------------------------------------------------------


def test_wrong_batter_destination_for_fixed_destination_result_raises():
    game = GameState(Side.AWAY, lineup=["a"])
    with pytest.raises(ValueError, match="requires the batter to reach FIRST"):
        game.commit_plate_appearance(Result.SINGLE, {"batter": Destination.SECOND})


def test_runner_marked_out_on_non_dp_fc_result_raises():
    game = GameState(Side.AWAY, lineup=["a", "b"])
    game.commit_plate_appearance(Result.SINGLE, {"batter": Destination.FIRST})
    with pytest.raises(ValueError, match="cannot be marked OUT"):
        game.commit_plate_appearance(
            Result.SINGLE, {"batter": Destination.FIRST, "first": Destination.OUT}
        )


def test_double_play_with_zero_runners_out_raises():
    game = GameState(Side.AWAY, lineup=["a", "b"])
    game.commit_plate_appearance(Result.SINGLE, {"batter": Destination.FIRST})
    with pytest.raises(ValueError, match="double play requires exactly one runner OUT"):
        game.commit_plate_appearance(
            Result.DOUBLE_PLAY,
            {"batter": Destination.OUT, "first": Destination.SECOND},
            fielder_position=4,
        )


def test_double_play_with_two_runners_out_raises():
    game = GameState(Side.AWAY, lineup=["a", "b", "c"])
    game.commit_plate_appearance(Result.SINGLE, {"batter": Destination.FIRST})
    game.commit_plate_appearance(
        Result.SINGLE, {"batter": Destination.FIRST, "first": Destination.SECOND}
    )
    with pytest.raises(ValueError, match="double play requires exactly one runner OUT"):
        game.commit_plate_appearance(
            Result.DOUBLE_PLAY,
            {"batter": Destination.OUT, "first": Destination.OUT, "second": Destination.OUT},
            fielder_position=4,
        )


def test_fielders_choice_with_zero_runners_out_raises():
    game = GameState(Side.AWAY, lineup=["a", "b"])
    game.commit_plate_appearance(Result.SINGLE, {"batter": Destination.FIRST})
    with pytest.raises(ValueError, match="fielder's choice requires exactly one runner OUT"):
        game.commit_plate_appearance(
            Result.FIELDERS_CHOICE,
            {"batter": Destination.FIRST, "first": Destination.SECOND},
            fielder_position=6,
        )


def test_fielders_choice_with_two_runners_out_raises():
    game = GameState(Side.AWAY, lineup=["a", "b", "c"])
    game.commit_plate_appearance(Result.SINGLE, {"batter": Destination.FIRST})
    game.commit_plate_appearance(
        Result.SINGLE, {"batter": Destination.FIRST, "first": Destination.SECOND}
    )
    with pytest.raises(ValueError, match="fielder's choice requires exactly one runner OUT"):
        game.commit_plate_appearance(
            Result.FIELDERS_CHOICE,
            {"batter": Destination.FIRST, "first": Destination.OUT, "second": Destination.OUT},
            fielder_position=6,
        )


def test_walk_force_chain_under_advancing_raises():
    game = GameState(Side.AWAY, lineup=["a", "b"])
    game.commit_plate_appearance(Result.SINGLE, {"batter": Destination.FIRST})
    with pytest.raises(ValueError, match="force-chain mismatch"):
        game.commit_plate_appearance(
            Result.WALK, {"batter": Destination.FIRST, "first": Destination.FIRST}
        )


def test_walk_force_chain_over_advancing_raises():
    game = GameState(Side.AWAY, lineup=["a", "b"])
    game.commit_plate_appearance(Result.SINGLE, {"batter": Destination.FIRST})
    with pytest.raises(ValueError, match="force-chain mismatch"):
        game.commit_plate_appearance(
            Result.WALK, {"batter": Destination.FIRST, "first": Destination.THIRD}
        )


def test_home_run_where_not_all_runners_scored_raises():
    game = GameState(Side.AWAY, lineup=["a", "b"])
    game.commit_plate_appearance(Result.SINGLE, {"batter": Destination.FIRST})
    with pytest.raises(ValueError, match="home run requires every existing runner to score"):
        game.commit_plate_appearance(
            Result.HOME_RUN, {"batter": Destination.HOME, "first": Destination.SECOND}
        )


def test_backward_movement_attempt_raises():
    game = GameState(Side.AWAY, lineup=["a", "b"])
    game.commit_plate_appearance(
        Result.DOUBLE, {"batter": Destination.SECOND}
    )
    with pytest.raises(ValueError, match="cannot move backward"):
        game.commit_plate_appearance(
            Result.SINGLE, {"batter": Destination.FIRST, "second": Destination.FIRST}
        )


def test_missing_required_key_raises():
    game = GameState(Side.AWAY, lineup=["a", "b"])
    game.commit_plate_appearance(Result.SINGLE, {"batter": Destination.FIRST})
    with pytest.raises(ValueError, match="missing required key"):
        game.commit_plate_appearance(Result.SINGLE, {"batter": Destination.FIRST})


def test_extraneous_key_raises():
    game = GameState(Side.AWAY, lineup=["a"])
    with pytest.raises(ValueError, match="extraneous key"):
        game.commit_plate_appearance(
            Result.SINGLE, {"batter": Destination.FIRST, "second": Destination.THIRD}
        )


def test_fielder_position_missing_when_required_raises():
    game = GameState(Side.AWAY, lineup=["a"])
    with pytest.raises(ValueError, match="requires fielder_position"):
        game.commit_plate_appearance(Result.IN_PLAY_OUT, {"batter": Destination.OUT})


def test_fielder_position_provided_when_not_allowed_raises():
    game = GameState(Side.AWAY, lineup=["a"])
    with pytest.raises(ValueError, match="does not accept a fielder_position"):
        game.commit_plate_appearance(
            Result.SINGLE, {"batter": Destination.FIRST}, fielder_position=6
        )


def test_fielder_position_out_of_range_raises():
    game = GameState(Side.AWAY, lineup=["a"])
    with pytest.raises(ValueError, match="requires fielder_position"):
        game.commit_plate_appearance(
            Result.IN_PLAY_OUT, {"batter": Destination.OUT}, fielder_position=10
        )


# ----------------------------------------------------------------------
# Turn/inning mechanics
# ----------------------------------------------------------------------


def test_game_starts_at_top_of_first_regardless_of_our_side():
    away_game = GameState(Side.AWAY, lineup=["a"])
    home_game = GameState(Side.HOME, lineup=["a"])
    assert away_game.inning == 1 and away_game.half is Half.TOP
    assert home_game.inning == 1 and home_game.half is Half.TOP


def test_is_our_turn_true_at_top_when_away():
    game = GameState(Side.AWAY, lineup=["a"])
    assert game.is_our_turn


def test_is_our_turn_false_at_top_when_home():
    game = GameState(Side.HOME, lineup=["a"])
    assert not game.is_our_turn


def test_three_outs_during_our_half_resets_outs_and_bases_and_flips_half():
    game = GameState(Side.AWAY, lineup=["a"])
    for _ in range(3):
        game.commit_plate_appearance(Result.STRIKEOUT_SWINGING, {"batter": Destination.OUT})
    assert game.outs == 0
    assert game.bases == BaseState()
    assert game.half is Half.BOTTOM
    assert game.inning == 1  # TOP->BOTTOM does not increment inning


def test_bottom_to_top_flip_increments_inning():
    game = GameState(Side.HOME, lineup=["a"])
    # It's the opponent's (away's) top half first; not our turn yet.
    game.record_opponent_half(runs=0)
    assert game.half is Half.BOTTOM
    assert game.inning == 1
    for _ in range(3):
        game.commit_plate_appearance(Result.STRIKEOUT_SWINGING, {"batter": Destination.OUT})
    assert game.half is Half.TOP
    assert game.inning == 2


def test_record_opponent_half_illegal_during_our_own_half():
    game = GameState(Side.AWAY, lineup=["a"])
    with pytest.raises(ValueError, match="our own half-inning"):
        game.record_opponent_half(runs=1)


def test_record_opponent_half_adds_to_opponent_score():
    game = GameState(Side.HOME, lineup=["a"])
    game.record_opponent_half(runs=3)
    assert game.opponent_score == 3


def test_record_opponent_half_negative_runs_raises():
    game = GameState(Side.HOME, lineup=["a"])
    with pytest.raises(ValueError, match="runs must be >= 0"):
        game.record_opponent_half(runs=-1)


def test_full_inning_cycle_increments_inning_once_when_away():
    game = GameState(Side.AWAY, lineup=["a"])
    assert game.inning == 1
    for _ in range(3):
        game.commit_plate_appearance(Result.STRIKEOUT_SWINGING, {"batter": Destination.OUT})
    assert game.inning == 1
    game.record_opponent_half(runs=0)
    assert game.inning == 2
    assert game.half is Half.TOP


def test_full_inning_cycle_increments_inning_once_when_home():
    game = GameState(Side.HOME, lineup=["a"])
    assert game.inning == 1
    game.record_opponent_half(runs=0)
    assert game.inning == 1
    for _ in range(3):
        game.commit_plate_appearance(Result.STRIKEOUT_SWINGING, {"batter": Destination.OUT})
    assert game.inning == 2
    assert game.half is Half.TOP


# ----------------------------------------------------------------------
# Batting order
# ----------------------------------------------------------------------


def test_batting_order_wraps_around():
    game = GameState(Side.AWAY, lineup=["a", "b"])
    assert game.current_batter == "a"
    game.commit_plate_appearance(Result.STRIKEOUT_SWINGING, {"batter": Destination.OUT})
    assert game.current_batter == "b"
    game.commit_plate_appearance(Result.STRIKEOUT_SWINGING, {"batter": Destination.OUT})
    assert game.current_batter == "a"


def test_add_batter_mid_game_slots_in_at_end_without_disrupting_cursor():
    game = GameState(Side.AWAY, lineup=["a", "b"])
    game.commit_plate_appearance(Result.STRIKEOUT_SWINGING, {"batter": Destination.OUT})
    assert game.current_batter == "b"
    game.add_batter("c")
    assert game.current_batter == "b"
    assert game.lineup == ("a", "b", "c")
    game.commit_plate_appearance(Result.STRIKEOUT_SWINGING, {"batter": Destination.OUT})
    assert game.current_batter == "c"


def test_current_batter_is_none_on_empty_lineup():
    game = GameState(Side.AWAY, lineup=[])
    assert game.current_batter is None


def test_commit_plate_appearance_raises_on_empty_lineup():
    game = GameState(Side.AWAY, lineup=[])
    with pytest.raises(ValueError, match="empty lineup"):
        game.commit_plate_appearance(Result.SINGLE, {"batter": Destination.FIRST})


# ----------------------------------------------------------------------
# undo
# ----------------------------------------------------------------------


def test_undo_after_commit_plate_appearance_restores_prior_state():
    game = GameState(Side.AWAY, lineup=["a", "b"])
    game.commit_plate_appearance(Result.SINGLE, {"batter": Destination.FIRST})
    assert game.current_batter == "b"
    assert game.bases == BaseState(first="a")

    game.undo()

    assert game.current_batter == "a"
    assert game.bases == BaseState()
    assert game.our_score == 0
    assert game.outs == 0
    assert len(game.history) == 0


def test_undo_after_record_opponent_half_restores_prior_state():
    game = GameState(Side.HOME, lineup=["a"])
    game.record_opponent_half(runs=5)
    assert game.opponent_score == 5
    assert game.half is Half.BOTTOM

    game.undo()

    assert game.opponent_score == 0
    assert game.half is Half.TOP
    assert len(game.history) == 0


def test_undo_after_add_batter_restores_prior_lineup():
    game = GameState(Side.AWAY, lineup=["a"])
    game.add_batter("b")
    assert game.lineup == ("a", "b")

    game.undo()

    assert game.lineup == ("a",)


def test_undo_after_end_game_restores_playability():
    game = GameState(Side.AWAY, lineup=["a"])
    game.end_game()
    assert game.is_game_over

    game.undo()

    assert not game.is_game_over
    game.commit_plate_appearance(Result.SINGLE, {"batter": Destination.FIRST})  # no raise


def test_multiple_sequential_undos_return_to_initial_state():
    game = GameState(Side.AWAY, lineup=["a", "b"])
    game.commit_plate_appearance(Result.SINGLE, {"batter": Destination.FIRST})
    game.commit_plate_appearance(
        Result.SINGLE, {"batter": Destination.FIRST, "first": Destination.SECOND}
    )
    game.add_batter("c")

    game.undo()
    game.undo()
    game.undo()

    assert game.lineup == ("a", "b")
    assert game.bases == BaseState()
    assert game.current_batter == "a"
    assert game.our_score == 0
    assert len(game.history) == 0


def test_undo_on_empty_history_raises():
    game = GameState(Side.AWAY, lineup=["a"])
    with pytest.raises(ValueError, match="nothing to undo"):
        game.undo()


# ----------------------------------------------------------------------
# end_game
# ----------------------------------------------------------------------


def test_end_game_sets_is_game_over():
    game = GameState(Side.AWAY, lineup=["a"])
    game.end_game()
    assert game.is_game_over


def test_end_game_blocks_commit_plate_appearance():
    game = GameState(Side.AWAY, lineup=["a"])
    game.end_game()
    with pytest.raises(ValueError, match="game has ended"):
        game.commit_plate_appearance(Result.SINGLE, {"batter": Destination.FIRST})


def test_end_game_blocks_record_opponent_half():
    game = GameState(Side.HOME, lineup=["a"])
    game.end_game()
    with pytest.raises(ValueError, match="game has ended"):
        game.record_opponent_half(runs=1)


def test_end_game_blocks_add_batter():
    game = GameState(Side.AWAY, lineup=["a"])
    game.end_game()
    with pytest.raises(ValueError, match="game has ended"):
        game.add_batter("b")


def test_end_game_raises_if_called_twice():
    game = GameState(Side.AWAY, lineup=["a"])
    game.end_game()
    with pytest.raises(ValueError, match="already over"):
        game.end_game()


# ----------------------------------------------------------------------
# history / event log
# ----------------------------------------------------------------------


def test_history_records_events_in_order_most_recent_last():
    game = GameState(Side.AWAY, lineup=["a"])
    game.add_batter("b")
    record = game.commit_plate_appearance(Result.SINGLE, {"batter": Destination.FIRST})
    assert len(game.history) == 2
    assert isinstance(game.history[0], AddBatterEvent)
    assert game.history[1] is record


def test_history_is_a_read_only_view():
    game = GameState(Side.AWAY, lineup=["a"])
    game.add_batter("b")
    history = game.history
    assert isinstance(history, tuple)
