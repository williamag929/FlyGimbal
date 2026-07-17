"""
Historical match data fetcher.

Priority:
  1. football-data.org (free tier, no key needed for some endpoints)
  2. api-football / api-sports.io  (free tier, 100 req/day with key)
  3. CSV file (user-supplied)

Set env vars:
  FOOTBALL_DATA_KEY   — api key for football-data.org
  API_FOOTBALL_KEY    — api key for api-football.com
"""

import os
import csv
import json
import time
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import requests

log = logging.getLogger(__name__)

FOOTBALL_DATA_BASE = "https://api.football-data.org/v4"
API_FOOTBALL_BASE  = "https://v3.football.api-sports.io"

# International competitions available on football-data.org free tier
INTL_COMPETITIONS = ["WC", "EC", "CN"]  # World Cup, EURO, AFCON

@dataclass(frozen=True)
class MatchRecord:
    home_team:  str
    away_team:  str
    home_goals: int
    away_goals: int
    match_date: str       # ISO-8601
    competition: str = ""
    venue: str = "neutral"  # "home" | "away" | "neutral"


class MatchFetcher:
    def __init__(self, cache_dir: str = ".football_cache"):
        self._fd_key = os.getenv("FOOTBALL_DATA_KEY", "")
        self._af_key = os.getenv("API_FOOTBALL_KEY", "")
        self._cache = Path(cache_dir)
        self._cache.mkdir(exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_matches(
        self,
        team: str,
        n_matches: int = 40,
        since_days: int = 1200,
    ) -> list[MatchRecord]:
        """Return up to n_matches completed results for a national team."""
        cache_file = self._cache / f"{team.replace(' ', '_')}.json"
        if cache_file.exists():
            age = time.time() - cache_file.stat().st_mtime
            if age < 3600 * 6:  # 6-hour cache
                return self._load_cache(cache_file)

        records: list[MatchRecord] = []

        if self._fd_key:
            records = self._fetch_football_data(team, since_days)
        if not records and self._af_key:
            records = self._fetch_api_football(team, since_days)

        records = sorted(records, key=lambda r: r.match_date, reverse=True)[:n_matches]

        if records:
            self._save_cache(cache_file, records)
        return records

    def load_csv(self, path: str) -> list[MatchRecord]:
        """Load matches from a CSV with columns: home,away,home_goals,away_goals,date."""
        records = []
        with open(path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    records.append(MatchRecord(
                        home_team=row["home"],
                        away_team=row["away"],
                        home_goals=int(row["home_goals"]),
                        away_goals=int(row["away_goals"]),
                        match_date=row["date"],
                        competition=row.get("competition", ""),
                    ))
                except (KeyError, ValueError) as exc:
                    log.warning("Skipping malformed CSV row: %s — %s", row, exc)
        return records

    # ------------------------------------------------------------------
    # football-data.org
    # ------------------------------------------------------------------

    def _fetch_football_data(self, team: str, since_days: int) -> list[MatchRecord]:
        headers = {"X-Auth-Token": self._fd_key}
        since = (date.today() - timedelta(days=since_days)).isoformat()
        records = []

        for comp in INTL_COMPETITIONS:
            url = f"{FOOTBALL_DATA_BASE}/competitions/{comp}/matches"
            params = {"dateFrom": since, "status": "FINISHED"}
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=10)
                if resp.status_code == 429:
                    log.warning("football-data.org rate limit hit")
                    time.sleep(60)
                    continue
                resp.raise_for_status()
                for m in resp.json().get("matches", []):
                    ht = m["homeTeam"]["name"]
                    at = m["awayTeam"]["name"]
                    if team.lower() not in (ht.lower(), at.lower()):
                        continue
                    score = m.get("score", {}).get("fullTime", {})
                    hg, ag = score.get("home"), score.get("away")
                    if hg is None or ag is None:
                        continue
                    records.append(MatchRecord(
                        home_team=ht,
                        away_team=at,
                        home_goals=int(hg),
                        away_goals=int(ag),
                        match_date=m["utcDate"][:10],
                        competition=comp,
                    ))
            except requests.RequestException as exc:
                log.warning("football-data.org error for %s/%s: %s", comp, team, exc)
        return records

    # ------------------------------------------------------------------
    # api-football.com
    # ------------------------------------------------------------------

    def _fetch_api_football(self, team: str, since_days: int) -> list[MatchRecord]:
        headers = {
            "x-apisports-key": self._af_key,
            "x-rapidapi-host": "v3.football.api-sports.io",
        }
        # First resolve team ID
        try:
            resp = requests.get(
                f"{API_FOOTBALL_BASE}/teams",
                headers=headers,
                params={"name": team, "type": "national"},
                timeout=10,
            )
            resp.raise_for_status()
            results = resp.json().get("response", [])
            if not results:
                return []
            team_id = results[0]["team"]["id"]
        except requests.RequestException as exc:
            log.warning("api-football team lookup failed: %s", exc)
            return []

        records = []
        since = (date.today() - timedelta(days=since_days)).year
        for season in range(since, date.today().year + 1):
            try:
                resp = requests.get(
                    f"{API_FOOTBALL_BASE}/fixtures",
                    headers=headers,
                    params={"team": team_id, "season": season, "status": "FT"},
                    timeout=10,
                )
                resp.raise_for_status()
                for fix in resp.json().get("response", []):
                    goals = fix.get("goals", {})
                    teams = fix.get("teams", {})
                    fixture = fix.get("fixture", {})
                    hg, ag = goals.get("home"), goals.get("away")
                    if hg is None or ag is None:
                        continue
                    records.append(MatchRecord(
                        home_team=teams["home"]["name"],
                        away_team=teams["away"]["name"],
                        home_goals=int(hg),
                        away_goals=int(ag),
                        match_date=fixture["date"][:10],
                        competition=fix.get("league", {}).get("name", ""),
                    ))
            except requests.RequestException as exc:
                log.warning("api-football fixtures error season %s: %s", season, exc)
        return records

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _save_cache(self, path: Path, records: list[MatchRecord]) -> None:
        with open(path, "w") as f:
            json.dump([r.__dict__ for r in records], f)

    def _load_cache(self, path: Path) -> list[MatchRecord]:
        with open(path) as f:
            return [MatchRecord(**d) for d in json.load(f)]
