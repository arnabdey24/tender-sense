"""Country name to ISO 3166-1 alpha-2, for the names portals actually print.

Shared rather than per-adapter, because a country code is not adapter trivia:
it feeds country-eligibility rules, so two portals disagreeing about what
"Lao People's Democratic Republic" is means a tenant's rule matches one source
and silently not the other.

Only names we recognise are mapped. An unrecognised name returns ``None`` and
the notice carries no country, which a rule can be written against honestly —
whereas a guess would put a notice in front of a bidder who cannot bid on it.
"""

from __future__ import annotations

#: Keyed lowercase, because portals disagree about capitalisation and little
#: else. Covers the World Bank names this project already handled plus the
#: Asian Development Bank's developing member countries, which is most of the
#: Asia-Pacific and the reason the map outgrew one adapter.
COUNTRY_CODES: dict[str, str] = {
    "afghanistan": "AF",
    "armenia": "AM",
    "azerbaijan": "AZ",
    "bangladesh": "BD",
    "bhutan": "BT",
    "cambodia": "KH",
    "china": "CN",
    "china, people's republic of": "CN",
    "people's republic of china": "CN",
    "cook islands": "CK",
    "egypt": "EG",
    "ethiopia": "ET",
    "fiji": "FJ",
    "georgia": "GE",
    "ghana": "GH",
    "india": "IN",
    "indonesia": "ID",
    "kazakhstan": "KZ",
    "kenya": "KE",
    "kiribati": "KI",
    "kyrgyz republic": "KG",
    "kyrgyzstan": "KG",
    "lao people's democratic republic": "LA",
    "laos": "LA",
    "maldives": "MV",
    "marshall islands": "MH",
    "micronesia": "FM",
    "federated states of micronesia": "FM",
    "mongolia": "MN",
    "morocco": "MA",
    "myanmar": "MM",
    "nauru": "NR",
    "nepal": "NP",
    "nigeria": "NG",
    "niue": "NU",
    "pakistan": "PK",
    "palau": "PW",
    "papua new guinea": "PG",
    "philippines": "PH",
    "samoa": "WS",
    "solomon islands": "SB",
    "sri lanka": "LK",
    "tajikistan": "TJ",
    "tanzania": "TZ",
    "thailand": "TH",
    "timor-leste": "TL",
    "tonga": "TO",
    "turkmenistan": "TM",
    "tuvalu": "TV",
    "uganda": "UG",
    "uzbekistan": "UZ",
    "vanuatu": "VU",
    "viet nam": "VN",
    "vietnam": "VN",
}


def country_code(name: object) -> str | None:
    """ISO code for a printed country name, or ``None`` when unrecognised."""
    if not name or not isinstance(name, str):
        return None
    return COUNTRY_CODES.get(name.strip().lower())
