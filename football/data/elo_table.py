"""
National team Elo ratings — baseline for teams with limited data.
Source: World Football Elo Ratings (worldfootballelo.com), approximate mid-2024.
"""

# fmt: off
ELO_RATINGS: dict[str, float] = {
    # S. America
    "Argentina":        2175,
    "Brazil":           2150,
    "France":           2135,
    "Spain":            2100,
    "England":          2075,
    "Belgium":          2060,
    "Portugal":         2055,
    "Netherlands":      2045,
    "Germany":          2040,
    "Italy":            2025,
    "Colombia":         2000,
    "Uruguay":          1990,
    "USA":              1975,
    "Mexico":           1965,
    "Chile":            1930,
    "Ecuador":          1900,
    "Peru":             1880,
    "Paraguay":         1860,
    "Bolivia":          1790,
    "Venezuela":        1780,
    # Europe
    "Croatia":          1980,
    "Denmark":          1965,
    "Switzerland":      1960,
    "Austria":          1945,
    "Sweden":           1935,
    "Poland":           1930,
    "Serbia":           1920,
    "Hungary":          1905,
    "Czech Republic":   1895,
    "Slovakia":         1885,
    "Ukraine":          1880,
    "Turkey":           1870,
    "Russia":           1865,
    "Greece":           1855,
    "Romania":          1845,
    "Scotland":         1840,
    "Norway":           1835,
    "Finland":          1820,
    "Wales":            1815,
    "Ireland":          1800,
    # Africa
    "Senegal":          1965,
    "Morocco":          1950,
    "Nigeria":          1885,
    "Ivory Coast":      1875,
    "Ghana":            1865,
    "Cameroon":         1855,
    "Tunisia":          1850,
    "Algeria":          1840,
    "Egypt":            1830,
    "Mali":             1820,
    "DR Congo":         1815,
    "Zambia":           1800,
    "South Africa":     1795,
    "Uganda":           1785,
    "Zimbabwe":         1770,
    "Tanzania":         1765,
    "Angola":           1760,
    "Mozambique":       1740,
    "Ethiopia":         1730,
    "Rwanda":           1720,
    # Asia
    "Japan":            1960,
    "South Korea":      1945,
    "Iran":             1920,
    "Australia":        1895,
    "Saudi Arabia":     1875,
    "Qatar":            1845,
    "China":            1810,
    "Thailand":         1780,
    "Vietnam":          1775,
    "India":            1765,
    "Uzbekistan":       1790,
    # CONCACAF
    "Canada":           1910,
    "Costa Rica":       1865,
    "Jamaica":          1835,
    "Honduras":         1825,
    "El Salvador":      1810,
    "Panama":           1820,
    "Curacao":          1800,
    "Haiti":            1780,
    # EURO newcomers / mid-tier
    "North Macedonia":  1810,
    "Albania":          1805,
    "Slovenia":         1800,
    "Bosnia":           1795,
    "Montenegro":       1785,
    "Georgia":          1815,
    "Iceland":          1830,
    "Israel":           1820,
}

# Canonical name aliases — map API names → dict keys above
TEAM_ALIASES: dict[str, str] = {
    "democratic republic of congo": "DR Congo",
    "congo dr":                     "DR Congo",
    "drc":                          "DR Congo",
    "republic of congo":            "DR Congo",
    "united states":                "USA",
    "united states of america":     "USA",
    "côte d'ivoire":                "Ivory Coast",
    "cote d'ivoire":                "Ivory Coast",
    "korea republic":               "South Korea",
    "republic of ireland":          "Ireland",
    "northern ireland":             "Ireland",
    "bosnia and herzegovina":       "Bosnia",
    "north korea":                  "South Korea",   # no data, use proxy
    "chinese taipei":               "China",
}


def resolve(name: str) -> str:
    """Normalize a team name to the canonical key in ELO_RATINGS."""
    key = name.strip()
    if key in ELO_RATINGS:
        return key
    lower = key.lower()
    if lower in TEAM_ALIASES:
        return TEAM_ALIASES[lower]
    # Case-insensitive direct lookup
    for k in ELO_RATINGS:
        if k.lower() == lower:
            return k
    return key  # return as-is; caller handles KeyError


def get_elo(name: str) -> float | None:
    """Return Elo rating for a team, or None if unknown."""
    canonical = resolve(name)
    return ELO_RATINGS.get(canonical)
