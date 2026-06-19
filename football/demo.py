"""
Demo: DR Congo vs Colombia — Elo-only prediction (no API key needed).
Run:
    python football/demo.py
"""

from __future__ import annotations

from datetime import date

from football.model.poisson import FootballPoissonModel, MatchRecord
from football.narrator import generate_narrative

# ── Synthetic historical data (illustrative) ──────────────────────────────
# Real data would come from MatchFetcher; these fixtures let the demo run
# without any API key.

DR_CONGO_MATCHES: list[MatchRecord] = [
    MatchRecord("DR Congo", "Tanzania",    3, 0, "2024-03-22", "AFCON Q"),
    MatchRecord("Sudan",    "DR Congo",    0, 2, "2024-03-26", "AFCON Q"),
    MatchRecord("DR Congo", "Morocco",     0, 1, "2024-01-16", "AFCON"),
    MatchRecord("Zambia",   "DR Congo",    2, 3, "2024-01-20", "AFCON"),
    MatchRecord("DR Congo", "Tanzania",    3, 1, "2024-01-24", "AFCON"),
    MatchRecord("DR Congo", "Egypt",       1, 1, "2024-01-28", "AFCON"),
    MatchRecord("DR Congo", "Guinea",      3, 1, "2024-02-02", "AFCON"),
    MatchRecord("Cape Verde","DR Congo",   0, 1, "2024-02-06", "AFCON"),
    MatchRecord("DR Congo", "Ivory Coast", 0, 1, "2024-02-10", "AFCON SF"),
    MatchRecord("Nigeria",  "DR Congo",    0, 0, "2023-10-13", "AFCON Q"),
    MatchRecord("DR Congo", "Mauritania",  1, 0, "2023-06-17", "AFCON Q"),
    MatchRecord("DR Congo", "Cameroon",    1, 0, "2023-03-24", "AFCON Q"),
    MatchRecord("Ethiopia", "DR Congo",    0, 3, "2022-09-27", "AFCON Q"),
    MatchRecord("DR Congo", "Gabon",       1, 1, "2022-06-11", "AFCON Q"),
]

COLOMBIA_MATCHES: list[MatchRecord] = [
    MatchRecord("Colombia", "Argentina",  1, 1, "2024-07-14", "Copa America F"),
    MatchRecord("Colombia", "Canada",     1, 0, "2024-07-09", "Copa America SF"),
    MatchRecord("Colombia", "Panama",     5, 0, "2024-07-05", "Copa America QF"),
    MatchRecord("Colombia", "Costa Rica", 3, 0, "2024-06-28", "Copa America"),
    MatchRecord("Colombia", "Paraguay",   2, 1, "2024-06-24", "Copa America"),
    MatchRecord("Colombia", "Ecuador",    1, 0, "2024-06-20", "Copa America"),
    MatchRecord("Colombia", "USA",        5, 1, "2024-06-09", "Friendly"),
    MatchRecord("Bolivia",  "Colombia",   0, 3, "2024-03-26", "WC Q"),
    MatchRecord("Colombia", "Chile",      3, 0, "2024-03-22", "WC Q"),
    MatchRecord("Colombia", "Brazil",     1, 1, "2024-11-19", "WC Q"),
    MatchRecord("Colombia", "Paraguay",   1, 0, "2024-11-15", "WC Q"),
    MatchRecord("Venezuela","Colombia",   1, 0, "2023-10-17", "WC Q"),
    MatchRecord("Colombia", "Uruguay",    2, 2, "2023-10-12", "WC Q"),
    MatchRecord("Colombia", "Ecuador",    0, 1, "2023-09-08", "WC Q"),
    MatchRecord("Peru",     "Colombia",   1, 0, "2023-09-08", "WC Q"),
]

ALL_MATCHES = DR_CONGO_MATCHES + COLOMBIA_MATCHES


def run_demo():
    print("=" * 60)
    print("  NX Sports — Football Probability Model Demo")
    print("  DR Congo vs Colombia  |  Neutral venue")
    print("=" * 60)
    print()

    model = FootballPoissonModel()
    model.fit(ALL_MATCHES, reference_date=date.today().isoformat())

    result = model.predict("DR Congo", "Colombia", venue="neutral")

    narrative = generate_narrative(
        result,
        context="International friendly — neutral venue, June 2024",
    )

    print(narrative)


if __name__ == "__main__":
    run_demo()
