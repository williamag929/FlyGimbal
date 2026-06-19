"""
CLI entry point for the football probability model.

Usage:
    python -m football predict "DR Congo" Colombia --venue neutral
    python -m football predict Brazil Argentina --venue home --context "Copa America SF"
    python -m football predict Spain England --csv my_matches.csv
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

from football.data.fetcher import MatchFetcher
from football.model.poisson import FootballPoissonModel, MatchRecord
from football.narrator import generate_narrative


def _to_model_record(r) -> MatchRecord:
    return MatchRecord(
        home_team=r.home_team,
        away_team=r.away_team,
        home_goals=r.home_goals,
        away_goals=r.away_goals,
        match_date=r.match_date,
        competition=r.competition,
    )


def cmd_predict(args: argparse.Namespace) -> None:
    fetcher = MatchFetcher()
    model   = FootballPoissonModel()

    all_records: list[MatchRecord] = []

    if args.csv:
        raw = fetcher.load_csv(args.csv)
        all_records = [_to_model_record(r) for r in raw]
        print(f"Loaded {len(all_records)} matches from {args.csv}")
    else:
        print(f"Fetching data for {args.home_team}…", end=" ", flush=True)
        rh = fetcher.get_matches(args.home_team, n_matches=args.n_matches, since_days=args.since_days)
        print(f"{len(rh)} records")

        print(f"Fetching data for {args.away_team}…", end=" ", flush=True)
        ra = fetcher.get_matches(args.away_team, n_matches=args.n_matches, since_days=args.since_days)
        print(f"{len(ra)} records")

        all_records = [_to_model_record(r) for r in rh + ra]

    if all_records:
        print(f"Fitting model on {len(all_records)} matches…")
        model.fit(all_records, reference_date=date.today().isoformat())

    result = model.predict(
        home_team=args.home_team,
        away_team=args.away_team,
        venue=args.venue,
    )

    narrative = generate_narrative(result, context=args.context)
    print()
    print(narrative)


def main() -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(
        prog="football",
        description="NX Sports — Football Probability Model",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    pred = sub.add_parser("predict", help="Predict a match outcome")
    pred.add_argument("home_team", help="Home (or first) team name")
    pred.add_argument("away_team", help="Away (or second) team name")
    pred.add_argument("--venue",      default="neutral", choices=["home", "away", "neutral"])
    pred.add_argument("--context",    default="", help="Tournament / match context")
    pred.add_argument("--n-matches",  type=int, default=40, dest="n_matches")
    pred.add_argument("--since-days", type=int, default=1200, dest="since_days")
    pred.add_argument("--csv",        default=None, help="Path to CSV file with historical matches")

    args = parser.parse_args()

    if args.command == "predict":
        cmd_predict(args)


if __name__ == "__main__":
    main()
