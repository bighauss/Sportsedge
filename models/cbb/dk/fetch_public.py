"""Network helper (not used by tests): record public DK event pages and the ESPN scoreboard.

Usage:
  python -m models.cbb.dk.fetch_public events --ids 35083406 35083407 --out evidence.jsonl
  python -m models.cbb.dk.fetch_public espn --date 20261125 --out raw.json

Public, signed-out pages only. No credentials, cookies or tokens are read or stored.
Every record carries request URL, final URL, HTTP status, retrieval time (UTC) and the
SHA-256 of the exact bytes received.
"""
from __future__ import annotations
import argparse, json, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from models.cbb.dk import evidence as EV  # noqa: E402

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.geturl(), r.read()
    except urllib.error.HTTPError as e:
        return e.code, url, e.read() or b""


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("events"); e.add_argument("--ids", nargs="+", required=True); e.add_argument("--out", required=True)
    e.add_argument("--sleep", type=float, default=1.0)
    s = sub.add_parser("espn"); s.add_argument("--date", required=True); s.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "events":
        with open(a.out, "a", encoding="utf-8") as f:
            for eid in a.ids:
                url = f"https://sportsbook.draftkings.com/event/{eid}"
                t = now(); code, final, body = _get(url)
                f.write(json.dumps(EV.page_record(eid, url, final, code, t, body), sort_keys=True) + "\n")
                time.sleep(a.sleep)
    else:
        url = ("https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/"
               f"scoreboard?dates={a.date}&groups=50&limit=500")
        t = now(); code, _, body = _get(url)
        Path(a.out).write_bytes(body)
        Path(a.out + ".receipt.json").write_text(json.dumps({"url": url, "http": code, "retrieved_utc": t,
                                                              "sha256": __import__("hashlib").sha256(body).hexdigest()}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
