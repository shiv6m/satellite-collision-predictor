"""
Fetches current orbital element sets (TLEs) from CelesTrak.

CelesTrak is a free, no-auth-required public catalog maintained from
US Space Force tracking data. It's updated a few times a day, which is
plenty for a "near real-time" predictor (satellites don't move orbital
regimes in minutes -- their *position* changes fast, but SGP4 lets us
compute that from a TLE that's a few hours old).

Docs: https://celestrak.org/NORAD/documentation/gp-data-formats.php
"""

from typing import Any

import httpx

CELESTRAK_URL = "https://celestrak.org/NORAD/elements/gp.php"

# CelesTrak groups you can pull instead of/alongside "active":
#   stations   -> ISS, Tiangong, etc. (small, good for testing)
#   active     -> all active satellites (~10,000 -- big!)
#   starlink   -> Starlink constellation (great demo: dense, real conjunctions)
#   debris     -> tracked debris objects (COSMOS-2251-DEB, IRIDIUM-33-DEB, etc.)


async def fetch_tle_group(group: str = "stations") -> list[dict[str, Any]]:
    """
    Fetch a named group of satellites as TLE text, parse into structured
    records. Returns a list of dicts: {name, line1, line2, norad_id}.
    """
    params = {"GROUP": group, "FORMAT": "tle"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(CELESTRAK_URL, params=params)
        resp.raise_for_status()
        text = resp.text

    return _parse_tle_text(text)


def _parse_tle_text(text: str) -> list[dict[str, Any]]:
    """TLE files are 3 lines per satellite: name, line1, line2."""
    lines = [line for line in text.splitlines() if line.strip()]
    satellites = []
    for i in range(0, len(lines) - 2, 3):
        name = lines[i].strip()
        line1 = lines[i + 1].strip()
        line2 = lines[i + 2].strip()
        if not (line1.startswith("1 ") and line2.startswith("2 ")):
            continue  # malformed block, skip
        norad_id = int(line1[2:7])
        satellites.append({"name": name, "line1": line1, "line2": line2, "norad_id": norad_id})
    return satellites
