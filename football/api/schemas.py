from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional


class PredictRequest(BaseModel):
    home_team:    str = Field(..., examples=["DR Congo"])
    away_team:    str = Field(..., examples=["Colombia"])
    venue:        str = Field("neutral", description="home | away | neutral")
    context:      str = Field("", description="Tournament name, match context")
    n_matches:    int = Field(40, ge=5, le=100, description="Historical matches to use")
    since_days:   int = Field(1200, ge=90, le=3650)
    elo_override: Optional[dict[str, float]] = Field(
        None, description="Force specific Elo ratings: {team: rating}"
    )


class ScoreLine(BaseModel):
    score: str
    prob:  float


class PredictResponse(BaseModel):
    home_team:   str
    away_team:   str
    venue:       str

    home_win_prob: float
    draw_prob:     float
    away_win_prob: float

    home_xg: float
    away_xg: float

    most_likely_score: str
    scorelines:        list[ScoreLine]

    model_confidence:  float
    data_source:       str
    dominant_factors:  list[str]

    n_home_matches: int
    n_away_matches: int

    narrative: Optional[str] = None
