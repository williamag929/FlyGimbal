"""Tests for the football probability model."""

import math
import pytest
from datetime import date

from football.model.poisson import (
    FootballPoissonModel,
    MatchRecord,
    _score_matrix,
    _outcomes,
    _elo_to_lambda,
    _time_weight,
)
from football.data.elo_table import get_elo, resolve


# ── Elo table tests ───────────────────────────────────────────────────────

def test_elo_known_teams():
    assert get_elo("Brazil") > 2000
    assert get_elo("Colombia") > 1900
    assert get_elo("DR Congo") is not None


def test_elo_alias_resolution():
    assert resolve("DR Congo") == "DR Congo"
    assert resolve("democratic republic of congo") == "DR Congo"
    assert resolve("united states") == "USA"


def test_elo_unknown_returns_none():
    assert get_elo("Atlantis FC") is None


# ── Time decay tests ──────────────────────────────────────────────────────

def test_time_weight_same_day():
    w = _time_weight("2024-06-01", "2024-06-01")
    assert w == pytest.approx(1.0)


def test_time_weight_decays():
    w1 = _time_weight("2024-01-01", "2024-06-01")
    w2 = _time_weight("2023-01-01", "2024-06-01")
    assert w1 > w2
    assert 0 < w2 < w1 < 1.0


# ── Score matrix tests ────────────────────────────────────────────────────

def test_score_matrix_sums_to_one():
    mat = _score_matrix(1.3, 1.1)
    assert mat.sum() == pytest.approx(1.0, abs=1e-6)


def test_score_matrix_all_nonneg():
    mat = _score_matrix(1.3, 1.1)
    assert (mat >= 0).all()


def test_outcomes_sum_to_one():
    mat = _score_matrix(1.5, 1.0)
    hw, dw, aw = _outcomes(mat)
    assert hw + dw + aw == pytest.approx(1.0, abs=1e-6)
    assert hw > 0 and dw > 0 and aw > 0


def test_stronger_team_wins_more():
    mat_balanced = _score_matrix(1.2, 1.2)
    mat_biased   = _score_matrix(2.0, 0.8)
    hw_b, _, aw_b = _outcomes(mat_balanced)
    hw_s, _, aw_s = _outcomes(mat_biased)
    assert abs(hw_b - aw_b) < 0.05        # balanced → near equal
    assert hw_s > hw_b                     # stronger home team wins more


# ── Elo → lambda tests ────────────────────────────────────────────────────

def test_equal_elos_give_similar_lambdas():
    lh, la = _elo_to_lambda(1900.0, 1900.0, is_home=False)
    assert lh == pytest.approx(la, rel=0.05)


def test_home_advantage_increases_home_lambda():
    lh_home, la_home   = _elo_to_lambda(1900.0, 1900.0, is_home=True)
    lh_neut, la_neut   = _elo_to_lambda(1900.0, 1900.0, is_home=False)
    assert lh_home > lh_neut
    assert la_home < la_neut


def test_higher_elo_gives_higher_lambda():
    lh_strong, _ = _elo_to_lambda(2100.0, 1700.0, is_home=False)
    lh_weak,   _ = _elo_to_lambda(1700.0, 2100.0, is_home=False)
    assert lh_strong > lh_weak


# ── Full model integration tests ──────────────────────────────────────────

SAMPLE_MATCHES = [
    MatchRecord("Brazil", "Argentina",    2, 1, "2024-03-01", "Friendly"),
    MatchRecord("Argentina", "Colombia",  1, 0, "2024-02-15", "Friendly"),
    MatchRecord("Colombia", "Brazil",     1, 2, "2024-01-20", "Friendly"),
    MatchRecord("Brazil", "Colombia",     3, 1, "2023-11-10", "WC Q"),
    MatchRecord("Argentina", "Brazil",    0, 0, "2023-09-05", "WC Q"),
    MatchRecord("Colombia", "Argentina",  2, 2, "2023-07-20", "Copa"),
    MatchRecord("Brazil", "Argentina",    1, 0, "2023-06-15", "Copa"),
    MatchRecord("Colombia", "Brazil",     0, 3, "2023-05-01", "Friendly"),
    MatchRecord("Argentina", "Colombia",  2, 0, "2023-03-25", "WC Q"),
    MatchRecord("Brazil", "Colombia",     2, 2, "2023-01-30", "Friendly"),
]


def test_model_predict_elo_fallback():
    model = FootballPoissonModel()
    # No fit → Elo fallback
    result = model.predict("DR Congo", "Colombia", venue="neutral")
    assert result.data_source == "elo_fallback"
    assert result.home_win_prob + result.draw_prob + result.away_win_prob == pytest.approx(1.0, abs=1e-4)
    assert result.home_xg > 0
    assert result.away_xg > 0


def test_model_predict_historical_fit():
    model = FootballPoissonModel()
    model.fit(SAMPLE_MATCHES, reference_date="2024-06-01")
    result = model.predict("Brazil", "Colombia", venue="home")
    assert result.data_source == "historical_fit"
    assert result.home_win_prob + result.draw_prob + result.away_win_prob == pytest.approx(1.0, abs=1e-4)
    assert result.most_likely_score != ""
    assert len(result.scorelines) == 15


def test_model_predict_confidence_elo_below_hist():
    model_elo  = FootballPoissonModel()
    model_hist = FootballPoissonModel()
    model_hist.fit(SAMPLE_MATCHES * 3, reference_date="2024-06-01")
    r_elo  = model_elo.predict("DR Congo", "Colombia")
    r_hist = model_hist.predict("Brazil", "Colombia")
    assert r_elo.model_confidence < r_hist.model_confidence


def test_model_dominant_factors_nonempty():
    model = FootballPoissonModel()
    result = model.predict("Colombia", "Argentina", venue="neutral")
    assert len(result.dominant_factors) >= 2


def test_model_scorelines_sorted():
    model = FootballPoissonModel()
    result = model.predict("Brazil", "Argentina", venue="neutral")
    probs = [s["prob"] for s in result.scorelines]
    assert probs == sorted(probs, reverse=True)


def test_model_unknown_team_raises():
    model = FootballPoissonModel()
    with pytest.raises(ValueError, match="Insufficient data"):
        model.predict("Atlantis FC", "Colombia")
