"""
NX Sports — Football Probability API

Run:
    uvicorn football.api.main:app --reload --port 8000

Endpoints:
    POST /predict        — full match prediction
    GET  /health         — liveness check
    GET  /teams          — list teams with known Elo ratings
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from football.api.schemas import PredictRequest, PredictResponse, ScoreLine
from football.data.fetcher import MatchFetcher, MatchRecord as FetcherRecord
from football.model.poisson import FootballPoissonModel, MatchRecord
from football.narrator import generate_narrative
from football.data.elo_table import ELO_RATINGS

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "WARNING").upper(),
    format="%(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

_cors_origins = [o.strip() for o in os.getenv("API_CORS_ORIGINS", "*").split(",")]

_fetcher = MatchFetcher()
_model   = FootballPoissonModel()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Football Probability API started.")
    yield
    log.info("Football Probability API shut down.")


app = FastAPI(
    title="NX Sports — Football Probability Model",
    version="1.0.0",
    description=(
        "Bivariate Dixon-Coles Poisson model with temporal decay. "
        "Returns win/draw/loss probabilities, expected goals, and scoreline distribution."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/teams")
def list_teams():
    return {
        "count": len(ELO_RATINGS),
        "teams": sorted(ELO_RATINGS.keys()),
    }


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest):
    t0 = time.perf_counter()

    # --- Fetch historical data for both teams ---
    home_records = _fetcher.get_matches(req.home_team, req.n_matches, req.since_days)
    away_records = _fetcher.get_matches(req.away_team, req.n_matches, req.since_days)

    # Merge + convert to model records
    all_records = _to_model_records(home_records) + _to_model_records(away_records)

    if all_records:
        _model.fit(all_records)

    # --- Run prediction ---
    try:
        result = _model.predict(
            home_team=req.home_team,
            away_team=req.away_team,
            venue=req.venue,
            elo_override=req.elo_override,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # --- Generate narrative ---
    narrative = generate_narrative(result, context=req.context)

    elapsed = time.perf_counter() - t0
    log.info(
        "Predicted %s vs %s in %.2fs (source=%s, confidence=%.0f%%)",
        req.home_team, req.away_team, elapsed,
        result.data_source, result.model_confidence * 100,
    )

    return PredictResponse(
        home_team=result.home_team,
        away_team=result.away_team,
        venue=req.venue,
        home_win_prob=result.home_win_prob,
        draw_prob=result.draw_prob,
        away_win_prob=result.away_win_prob,
        home_xg=result.home_xg,
        away_xg=result.away_xg,
        most_likely_score=result.most_likely_score,
        scorelines=[ScoreLine(score=s["score"], prob=s["prob"]) for s in result.scorelines],
        model_confidence=result.model_confidence,
        data_source=result.data_source,
        dominant_factors=result.dominant_factors,
        n_home_matches=result.n_home_matches,
        n_away_matches=result.n_away_matches,
        narrative=narrative,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_model_records(records) -> list[MatchRecord]:
    out = []
    for r in records:
        out.append(MatchRecord(
            home_team=r.home_team,
            away_team=r.away_team,
            home_goals=r.home_goals,
            away_goals=r.away_goals,
            match_date=r.match_date,
            competition=r.competition,
        ))
    return out
