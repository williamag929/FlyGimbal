"""
Bivariate Dixon-Coles Poisson model for international football.

Key references:
  Dixon & Coles (1997) — low-score correction (tau)
  Karlis & Ntzoufras (2003) — bivariate Poisson
  Constantinou et al. — temporal decay weighting
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import numpy as np
from scipy.optimize import minimize
from scipy.stats import poisson

from football.data.elo_table import get_elo, resolve

log = logging.getLogger(__name__)

MAX_GOALS = 9       # Scoreline matrix dimension (0..MAX_GOALS each axis)
DECAY_PHI = 0.004   # ~half-life 6 months (1/φ * ln2 ≈ 173 days)
DC_RHO    = -0.10   # Dixon-Coles low-score correction; negative → draws rarer than Poisson predicts
HOME_ELO_BONUS = 65 # Elo points representing home advantage


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class MatchRecord:
    home_team:  str
    away_team:  str
    home_goals: int
    away_goals: int
    match_date: str   # ISO-8601
    competition: str = ""
    venue: str = "neutral"


@dataclass
class PredictionResult:
    home_team:   str
    away_team:   str

    home_win_prob: float
    draw_prob:     float
    away_win_prob: float

    home_xg: float
    away_xg: float

    most_likely_score: str           # "1-1"
    scorelines: list[dict]           # [{"score": "1-0", "prob": 0.12}, ...]

    model_confidence: float          # 0-1
    data_source: str                 # "historical_fit" | "elo_fallback" | "hybrid"
    dominant_factors: list[str]

    n_home_matches: int = 0
    n_away_matches: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _time_weight(match_date: str, reference_date: str, phi: float = DECAY_PHI) -> float:
    d0 = date.fromisoformat(reference_date)
    dm = date.fromisoformat(match_date)
    days = max(0, (d0 - dm).days)
    return math.exp(-phi * days)


def _dc_tau(x: int, y: int, lam_h: float, lam_a: float, rho: float) -> float:
    """Dixon-Coles correction for under/over-representation of low scores."""
    if x == 0 and y == 0:
        return 1.0 - lam_h * lam_a * rho
    if x == 0 and y == 1:
        return 1.0 + lam_h * rho
    if x == 1 and y == 0:
        return 1.0 + lam_a * rho
    if x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def _score_matrix(lam_h: float, lam_a: float, rho: float = DC_RHO) -> np.ndarray:
    """Return (MAX_GOALS+1) x (MAX_GOALS+1) matrix of P(home=i, away=j)."""
    g = MAX_GOALS + 1
    mat = np.zeros((g, g))
    for i in range(g):
        for j in range(g):
            tau = _dc_tau(i, j, lam_h, lam_a, rho)
            mat[i, j] = poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a) * tau
    mat = np.clip(mat, 0, None)
    total = mat.sum()
    if total > 0:
        mat /= total
    return mat


def _outcomes(mat: np.ndarray) -> tuple[float, float, float]:
    """(home_win, draw, away_win) from score matrix."""
    n = mat.shape[0]
    home_win = float(sum(mat[i, j] for i in range(n) for j in range(n) if i > j))
    draw     = float(sum(mat[i, i] for i in range(n)))
    away_win = float(sum(mat[i, j] for i in range(n) for j in range(n) if j > i))
    return home_win, draw, away_win


def _elo_to_lambda(elo_h: float, elo_a: float, is_home: bool = True) -> tuple[float, float]:
    """
    Convert Elo ratings → expected goals.
    Calibrated on international football: avg ~1.25 goals/team/game at equal strength.
    """
    MEAN = 1.20
    K    = 0.45   # exponent: how sharply Elo differences affect goal rates
    adj  = HOME_ELO_BONUS if is_home else 0
    wp_h = 1.0 / (1.0 + 10 ** ((elo_a - elo_h - adj) / 400))
    wp_a = 1.0 - wp_h
    lam_h = MEAN * (2 * wp_h) ** K
    lam_a = MEAN * (2 * wp_a) ** K
    return lam_h, lam_a


# ---------------------------------------------------------------------------
# MLE fitting
# ---------------------------------------------------------------------------

REG_LAMBDA = 0.15   # L2 regularisation: shrinks params toward 0 when data sparse


def _fit_parameters(
    matches: list[MatchRecord],
    reference_date: str,
    rho: float = DC_RHO,
    phi: float = DECAY_PHI,
) -> dict:
    """
    Fit attack alpha_i, defence delta_i, global intercept mu, and home advantage gamma.

    Parametrisation:
        log(lam_home) = mu + alpha_home - delta_away + gamma
        log(lam_away) = mu + alpha_away - delta_home

    Both Sigma(alpha) = 0 and Sigma(delta) = 0 for identifiability.
    L2 regularisation guards against overfit when n_teams >> n_matches.
    """
    teams = sorted({m.home_team for m in matches} | {m.away_team for m in matches})
    idx   = {t: i for i, t in enumerate(teams)}
    n     = len(teams)
    w     = [_time_weight(m.match_date, reference_date, phi) for m in matches]

    all_goals = [m.home_goals + m.away_goals for m in matches]
    mu0 = math.log(max(sum(all_goals) / (2 * len(matches)), 0.5))

    # x = [mu, alpha_0..alpha_{n-1}, delta_0..delta_{n-1}, gamma]
    x0      = np.zeros(2 * n + 2)
    x0[0]   = mu0
    x0[-1]  = 0.15

    def neg_ll(x: np.ndarray) -> float:
        mu    = x[0]
        alpha = x[1: n + 1]
        delta = x[n + 1: 2 * n + 1]
        gamma = x[-1]
        ll = 0.0
        for m, wi in zip(matches, w):
            hi, ai = idx[m.home_team], idx[m.away_team]
            lam_h = math.exp(mu + alpha[hi] - delta[ai] + gamma)
            lam_a = math.exp(mu + alpha[ai] - delta[hi])
            tau   = _dc_tau(m.home_goals, m.away_goals, lam_h, lam_a, rho)
            if tau <= 0:
                tau = 1e-9
            ll += wi * (
                m.home_goals * math.log(lam_h) - lam_h
                + m.away_goals * math.log(lam_a) - lam_a
                + math.log(abs(tau))
            )
        ll -= REG_LAMBDA * (float(np.dot(alpha, alpha)) + float(np.dot(delta, delta)))
        return -ll

    cons = [
        {"type": "eq", "fun": lambda x: np.sum(x[1: n + 1])},
        {"type": "eq", "fun": lambda x: np.sum(x[n + 1: 2 * n + 1])},
    ]

    try:
        res = minimize(
            neg_ll, x0,
            method="SLSQP",
            constraints=cons,
            options={"maxiter": 1000, "ftol": 1e-9},
        )
    except Exception as exc:
        log.warning("MLE optimizer error: %s", exc)
        return {}

    if not res.success:
        log.debug("MLE convergence note: %s", res.message)

    mu_fit = float(res.x[0])
    return {
        "mu":       mu_fit,
        "attack":   {teams[i]: float(res.x[1 + i])     for i in range(n)},
        "defence":  {teams[i]: float(res.x[n + 1 + i]) for i in range(n)},
        "home_adv": float(res.x[-1]),
        "teams":    teams,
    }


# ---------------------------------------------------------------------------
# Main model class
# ---------------------------------------------------------------------------

class FootballPoissonModel:
    """
    Bivariate Dixon-Coles Poisson model with temporal decay.

    Usage:
        model = FootballPoissonModel()
        model.fit(matches, reference_date="2024-06-01")
        result = model.predict("DR Congo", "Colombia", venue="neutral")
    """

    def __init__(self, rho: float = DC_RHO, phi: float = DECAY_PHI):
        self.rho = rho
        self.phi = phi
        self._params: dict = {}
        self._all_matches: list[MatchRecord] = []
        self._ref_date: str = date.today().isoformat()

    # ------------------------------------------------------------------

    def fit(self, matches: list[MatchRecord], reference_date: str | None = None) -> "FootballPoissonModel":
        """Fit model parameters from historical matches."""
        if reference_date:
            self._ref_date = reference_date
        self._all_matches = matches
        if len(matches) >= 10:
            self._params = _fit_parameters(matches, self._ref_date, self.rho, self.phi)
        else:
            log.info("Too few matches (%d) for MLE; will use Elo fallback.", len(matches))
        return self

    # ------------------------------------------------------------------

    def predict(
        self,
        home_team: str,
        away_team: str,
        venue: str = "neutral",       # "home" | "away" | "neutral"
        elo_override: dict[str, float] | None = None,
    ) -> PredictionResult:
        """Generate a full probabilistic prediction."""

        home_team = resolve(home_team)
        away_team = resolve(away_team)
        is_home   = venue == "home"

        elo_h = (elo_override or {}).get(home_team) or get_elo(home_team)
        elo_a = (elo_override or {}).get(away_team) or get_elo(away_team)

        n_home = sum(1 for m in self._all_matches if home_team in (m.home_team, m.away_team))
        n_away = sum(1 for m in self._all_matches if away_team in (m.home_team, m.away_team))

        lam_h, lam_a, data_source, factors = self._resolve_lambdas(
            home_team, away_team, is_home, elo_h, elo_a, n_home, n_away
        )

        mat = _score_matrix(lam_h, lam_a, self.rho)
        hw, dw, aw = _outcomes(mat)

        # Scorelines sorted by probability
        scores = []
        for i in range(MAX_GOALS + 1):
            for j in range(MAX_GOALS + 1):
                scores.append({"score": f"{i}-{j}", "prob": float(mat[i, j])})
        scores.sort(key=lambda s: s["prob"], reverse=True)

        best = scores[0]["score"]
        confidence = self._confidence(n_home, n_away, data_source)

        return PredictionResult(
            home_team=home_team,
            away_team=away_team,
            home_win_prob=hw,
            draw_prob=dw,
            away_win_prob=aw,
            home_xg=round(lam_h, 3),
            away_xg=round(lam_a, 3),
            most_likely_score=best,
            scorelines=scores[:15],
            model_confidence=confidence,
            data_source=data_source,
            dominant_factors=factors,
            n_home_matches=n_home,
            n_away_matches=n_away,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_lambdas(
        self,
        home: str,
        away: str,
        is_home: bool,
        elo_h: float | None,
        elo_a: float | None,
        n_home: int,
        n_away: int,
    ) -> tuple[float, float, str, list[str]]:
        p = self._params
        has_fit = bool(p)
        has_home = has_fit and home in p.get("attack", {})
        has_away = has_fit and away in p.get("attack", {})

        if has_home and has_away:
            mu      = p.get("mu", 0.0)
            gamma   = p["home_adv"] if is_home else 0.0
            lam_h   = math.exp(mu + p["attack"][home] - p["defence"][away] + gamma)
            lam_a   = math.exp(mu + p["attack"][away] - p["defence"][home])
            source  = "historical_fit"
            factors = self._historical_factors(home, away, p, is_home)

        elif elo_h and elo_a:
            lam_h, lam_a = _elo_to_lambda(elo_h, elo_a, is_home)
            source  = "elo_fallback" if (not has_home and not has_away) else "hybrid"
            factors = self._elo_factors(home, away, elo_h, elo_a, lam_h, lam_a, is_home)

        else:
            raise ValueError(
                f"Insufficient data for {home!r} or {away!r}. "
                "Provide an Elo override or API key."
            )

        return round(lam_h, 4), round(lam_a, 4), source, factors

    def _historical_factors(self, home: str, away: str, p: dict, is_home: bool) -> list[str]:
        mu    = p.get("mu", 0.0)
        atk_h = p["attack"][home]
        atk_a = p["attack"][away]
        def_h = p["defence"][home]
        def_a = p["defence"][away]
        avg_goals = math.exp(mu)
        factors = [
            f"Baseline avg goals/team: {avg_goals:.2f} (mu={mu:+.3f})",
            f"Attack index {home}: {atk_h:+.3f} ({'above' if atk_h > 0 else 'below'} average)",
            f"Attack index {away}: {atk_a:+.3f} ({'above' if atk_a > 0 else 'below'} average)",
            f"Defence index {home}: {def_h:+.3f} ({'solid' if def_h < 0 else 'leaky'})",
            f"Defence index {away}: {def_a:+.3f} ({'solid' if def_a < 0 else 'leaky'})",
        ]
        if is_home:
            factors.append(f"Home advantage: +{p['home_adv']:.3f} log-scale ({math.exp(p['home_adv']):.2f}x multiplier on xG)")
        factors.append(f"Dixon-Coles rho={self.rho} (low-score correction applied)")
        return factors

    def _elo_factors(
        self, home: str, away: str, elo_h: float, elo_a: float,
        lam_h: float, lam_a: float, is_home: bool
    ) -> list[str]:
        diff = elo_h - elo_a + (HOME_ELO_BONUS if is_home else 0)
        wp   = 1 / (1 + 10 ** (-diff / 400))
        stronger = home if diff > 0 else away
        return [
            f"Elo {home}: {elo_h:.0f}  |  Elo {away}: {elo_a:.0f}",
            f"Elo gap (incl. venue): {abs(diff):.0f} pts → {stronger} favored",
            f"Win probability {home}: {wp * 100:.1f}%",
            f"xG {home}: {lam_h:.2f}  |  xG {away}: {lam_a:.2f}",
            "Model: Elo-calibrated Poisson (historical data unavailable or insufficient)",
        ]

    @staticmethod
    def _confidence(n_home: int, n_away: int, source: str) -> float:
        if source == "elo_fallback":
            return 0.45
        # Geometric mean of match-count confidence, saturates at 40 matches
        c = math.sqrt(min(n_home, 40) / 40 * min(n_away, 40) / 40)
        if source == "hybrid":
            c = max(c, 0.55)
        return round(min(c, 0.95), 3)
