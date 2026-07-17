"""
AI narrative layer — uses Claude to turn model numbers into expert analysis.

Requires ANTHROPIC_API_KEY env var.
Gracefully degrades to a structured text summary when the key is absent.
"""

from __future__ import annotations

import os
import logging
import textwrap

from football.model.poisson import PredictionResult

log = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-6"


def generate_narrative(result: PredictionResult, context: str = "") -> str:
    """
    Return a natural-language match analysis for the given PredictionResult.
    Falls back to a formatted summary if the Anthropic SDK is unavailable.
    """
    try:
        return _claude_narrative(result, context)
    except Exception as exc:
        log.warning("Claude narrative failed (%s); using fallback summary.", exc)
        return _fallback_summary(result)


# ---------------------------------------------------------------------------
# Claude-powered narrative
# ---------------------------------------------------------------------------

def _claude_narrative(result: PredictionResult, context: str) -> str:
    import anthropic  # type: ignore

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    top_scores = "\n".join(
        f"  {s['score']:>5}  {s['prob'] * 100:.1f}%"
        for s in result.scorelines[:8]
    )

    system_prompt = textwrap.dedent("""\
        You are a senior football analyst with expertise in quantitative models and
        international football. You write concise, data-driven match previews that
        explain WHY the model produced these numbers — not just WHAT the numbers are.

        Style rules:
        - Lead with the key tension / most interesting finding.
        - Call out any contradiction (e.g. high Elo but bad recent form).
        - Mention the scoreline that best represents the game's dynamics.
        - Honest about uncertainty: flag if data is thin.
        - Max 280 words. No bullet lists in the output — flowing paragraphs.
    """)

    user_msg = textwrap.dedent(f"""\
        Match: {result.home_team} vs {result.away_team}
        Context: {context or "International friendly / unspecified"}
        Data source: {result.data_source}
        Model confidence: {result.model_confidence * 100:.0f}%

        Win probabilities
          {result.home_team}: {result.home_win_prob * 100:.1f}%
          Draw:              {result.draw_prob * 100:.1f}%
          {result.away_team}: {result.away_win_prob * 100:.1f}%

        Expected goals
          {result.home_team}: {result.home_xg:.2f}
          {result.away_team}: {result.away_xg:.2f}

        Most likely score: {result.most_likely_score}

        Top scorelines:
        {top_scores}

        Key factors the model detected:
        {chr(10).join('- ' + f for f in result.dominant_factors)}

        Historical matches used:
          {result.home_team}: {result.n_home_matches}
          {result.away_team}: {result.n_away_matches}

        Write the analyst narrative now.
    """)

    msg = client.messages.create(
        model=_MODEL,
        max_tokens=400,
        messages=[{"role": "user", "content": user_msg}],
        system=system_prompt,
    )
    return msg.content[0].text.strip()


# ---------------------------------------------------------------------------
# Plain-text fallback (no API key required)
# ---------------------------------------------------------------------------

def _fallback_summary(result: PredictionResult) -> str:
    r = result
    lines = [
        f"=== {r.home_team} vs {r.away_team} ===",
        "",
        "OUTCOME PROBABILITIES",
        f"  {r.home_team:<25} {r.home_win_prob * 100:>5.1f}%",
        f"  Draw                      {r.draw_prob * 100:>5.1f}%",
        f"  {r.away_team:<25} {r.away_win_prob * 100:>5.1f}%",
        "",
        "EXPECTED GOALS",
        f"  {r.home_team}: {r.home_xg:.2f}  |  {r.away_team}: {r.away_xg:.2f}",
        "",
        f"MOST LIKELY SCORE: {r.most_likely_score}",
        "",
        "TOP SCORELINES",
    ]
    for s in r.scorelines[:8]:
        lines.append(f"  {s['score']:>5}   {s['prob'] * 100:.1f}%")

    lines += [
        "",
        "MODEL FACTORS",
        *[f"  • {f}" for f in r.dominant_factors],
        "",
        f"Data source    : {r.data_source}",
        f"Confidence     : {r.model_confidence * 100:.0f}%",
        f"Historical data: {r.n_home_matches} matches ({r.home_team}) / {r.n_away_matches} ({r.away_team})",
    ]
    return "\n".join(lines)
