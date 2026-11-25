"""Point-in-time rest, travel and site context for the full-game CHALLENGER (PAPER / 0u).

All features for a game use only strictly earlier games in the same season (plus the
pre-game venue directory). No network I/O. Travel miles are a coarse proxy: 0 when the
city+state match, a fixed intra-state default when the state matches, otherwise the
haversine between state/region centroids. This is not a surveyed road distance.

Player availability and returning-minutes roster continuity are intentionally absent:
no legitimate point-in-time public source is shipped with this challenger. See REPORT.md.
"""
from __future__ import annotations

import math

REST_CAP = 14
INTRA_STATE_MILES = 120.0
EARLY_N = 5

# Approximate region centroids (US states, DC, Canadian provinces, common early-season
# event regions). Public geographic knowledge; not a geocoded venue survey.
CENTROIDS = {
    "AL": (32.78, -86.83), "AK": (64.07, -152.28), "AZ": (34.27, -111.66),
    "AR": (34.90, -92.44), "CA": (37.18, -119.47), "CO": (39.00, -105.55),
    "CT": (41.62, -72.73), "DE": (38.99, -75.51), "DC": (38.91, -77.04),
    "FL": (28.63, -82.45), "GA": (32.64, -83.44), "HI": (20.29, -156.37),
    "ID": (44.39, -114.66), "IL": (40.04, -89.20), "IN": (39.89, -86.28),
    "IA": (42.08, -93.50), "KS": (38.49, -98.32), "KY": (37.53, -85.29),
    "LA": (31.07, -92.00), "ME": (45.37, -69.24), "MD": (39.06, -76.80),
    "MA": (42.26, -71.81), "MI": (44.35, -85.55), "MN": (46.28, -94.31),
    "MS": (32.74, -89.68), "MO": (38.36, -92.46), "MT": (47.05, -109.63),
    "NE": (41.54, -99.81), "NV": (39.33, -116.63), "NH": (43.68, -71.58),
    "NJ": (40.19, -74.67), "NM": (34.41, -106.11), "NY": (42.95, -75.53),
    "NC": (35.56, -79.39), "ND": (47.45, -100.47), "OH": (40.29, -82.79),
    "OK": (35.59, -97.51), "OR": (43.93, -120.56), "PA": (40.88, -77.80),
    "RI": (41.68, -71.56), "SC": (33.92, -80.90), "SD": (44.44, -100.23),
    "TN": (35.86, -86.35), "TX": (31.48, -99.33), "UT": (39.31, -111.67),
    "VT": (44.07, -72.67), "VA": (37.52, -78.85), "WA": (47.38, -120.45),
    "WV": (38.64, -80.62), "WI": (44.62, -89.99), "WY": (43.00, -107.55),
    "ON": (43.70, -79.42), "BC": (49.25, -123.12), "PQ": (46.81, -71.21),
    "AB": (53.55, -113.49), "NB": (45.96, -66.64),
    "Bahamas": (25.06, -77.34), "Virgin Islands": (18.34, -64.93),
    "England": (51.51, -0.13), "Northern Ireland": (54.60, -5.93),
    "Mexico": (21.16, -86.85), "Cayman Islands": (19.29, -81.37),
    "Jamaica": (18.48, -77.92), "GB": (51.51, -0.13), "China": (31.23, 121.47),
    "Ireland": (53.35, -6.26), "Puerto Rico": (18.47, -66.12), "Italy": (41.90, 12.50),
}


def haversine_miles(a, b):
    lat1, lon1 = a; lat2, lon2 = b
    p = math.pi / 180.0
    dlat = (lat2 - lat1) * p; dlon = (lon2 - lon1) * p
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin(dlon / 2) ** 2
    return 3958.8 * 2 * math.asin(min(1.0, math.sqrt(h)))


def travel_miles(city_a, state_a, city_b, state_b):
    """Coarse miles between two (city, state/region) labels. None if a side is missing."""
    if not state_a or not state_b:
        return None
    sa, sb = str(state_a).strip(), str(state_b).strip()
    ca = (city_a or "").strip().lower(); cb = (city_b or "").strip().lower()
    if ca and cb and ca == cb and sa.lower() == sb.lower():
        return 0.0
    if sa.lower() == sb.lower():
        return INTRA_STATE_MILES
    c1, c2 = CENTROIDS.get(sa), CENTROIDS.get(sb)
    if c1 and c2:
        return haversine_miles(c1, c2)
    return None


def _loc(venue_id, lookup):
    if not venue_id or not lookup:
        return None, None
    info = lookup.get(str(venue_id))
    if not info:
        return None, None
    return info.get("city"), info.get("state")


def attach_context(games, *, venue_lookup=None):
    """Add rest/travel/site fields. ``games`` must be a single season (or already
    season-grouped). Each game is scored from strictly earlier games only.

    New fields (all pre-game):
      home_rest, away_rest  days since that team's last game, capped at REST_CAP;
                            REST_CAP and opener=1 if no prior game this season
      home_opener, away_opener
      home_b2b, away_b2b    rest == 1
      rest_diff             home_rest - away_rest
      is_neutral, is_unverified, is_home_verified
      home_miles, away_miles  coarse miles from the team's own home venue
      home_moved, away_moved  1 if this venue differs from that team's last venue
      miles_since_last_home, miles_since_last_away
    """
    venue_lookup = venue_lookup or {}
    ordered = sorted(games, key=lambda g: (g["date"], g.get("tip_utc") or "", g["game_id"]))
    last = {}  # team -> (date, venue_id)
    for g in ordered:
        hid, aid = str(g["home"]), str(g["away"])
        day = g["date"][:10]
        vid = str(g.get("venue_id") or "") or None
        hvid = str(g.get("home_venue_id") or "") or None
        site = g.get("site")
        for side, tid in (("home", hid), ("away", aid)):
            prev = last.get(tid)
            if prev is None:
                rest, opener, moved, miles_since = REST_CAP, 1, 0, 0.0
            else:
                prev_day, prev_vid = prev
                delta = (date_ordinal(day) - date_ordinal(prev_day))
                rest, opener = min(REST_CAP, max(0, delta)), 0
                moved = int(bool(vid and prev_vid and vid != prev_vid))
                c1, s1 = _loc(prev_vid, venue_lookup)
                c2, s2 = _loc(vid, venue_lookup)
                miles_since = travel_miles(c1, s1, c2, s2)
                if miles_since is None:
                    miles_since = 0.0 if not moved else INTRA_STATE_MILES
            g[f"{side}_rest"] = rest
            g[f"{side}_opener"] = opener
            g[f"{side}_b2b"] = int(rest == 1 and opener == 0)
            g[f"{side}_moved"] = moved
            g[f"{side}_miles_since_last"] = float(miles_since)
            # miles from the team's home venue to today's venue
            team_home_vid = hvid if side == "home" else None
            # away team's home venue is not always on the row; use last known home
            # venue if the caller attached ``away_venue_id``, else leave 0 for home
            # verified and a lookup via ``away_home_venue_id`` when present.
            if side == "home":
                src = hvid
            else:
                src = str(g.get("away_venue_id") or g.get("away_home_venue_id") or "") or None
            if site == "HOME_VERIFIED" and side == "home":
                g["home_miles"] = 0.0
            elif src and vid:
                c1, s1 = _loc(src, venue_lookup)
                c2, s2 = _loc(vid, venue_lookup)
                m = travel_miles(c1, s1, c2, s2)
                g[f"{side}_miles"] = 0.0 if m is None and src == vid else (0.0 if m is None else float(m))
            else:
                g[f"{side}_miles"] = 0.0 if (site == "HOME_VERIFIED" and side == "home") else (
                    0.0 if not vid else float(INTRA_STATE_MILES) if site == "NEUTRAL" else 0.0)
        # If the away team has no explicit home venue, treat miles as 0 when we
        # cannot observe it (feature becomes a missing-at-zero, documented).
        g["rest_diff"] = g["home_rest"] - g["away_rest"]
        g["is_neutral"] = int(site == "NEUTRAL")
        g["is_unverified"] = int(site == "UNVERIFIED")
        g["is_home_verified"] = int(site == "HOME_VERIFIED")
        last[hid] = (day, vid)
        last[aid] = (day, vid)
    return ordered


def date_ordinal(s):
    y, m, d = int(s[0:4]), int(s[5:7]), int(s[8:10])
    # Rata die / civil ordinal without datetime (pure arith.)
    if m <= 2:
        y -= 1; m += 12
    return 365 * y + y // 4 - y // 100 + y // 400 + (153 * m - 457) // 5 + d - 306


def build_venue_lookup(schedule_rows):
    """schedule_rows: iterable of dicts with venue_id, city, state (and optional home_venue_id)."""
    out = {}
    for r in schedule_rows:
        for key in ("venue_id", "home_venue_id", "away_venue_id"):
            vid = r.get(key)
            if vid in (None, ""):
                continue
            city = r.get("venue_address_city") or r.get("city")
            state = r.get("venue_address_state") or r.get("state")
            if key != "venue_id":
                # do not invent city for a team's home venue from the game venue
                if key == "home_venue_id" and str(vid) == str(r.get("venue_id") or ""):
                    pass
                else:
                    continue
            if city or state:
                out[str(int(vid) if not isinstance(vid, str) else vid.split(".")[0] if vid else vid)] = {
                    "city": city, "state": state,
                    "name": r.get("venue_full_name") or r.get("name"),
                }
    return out


def early_flag(n_home, n_away, threshold=EARLY_N):
    return int(min(n_home, n_away) < threshold)
