"""Private, fail-closed PAPER settlement + no-vig CLV SQLite ledger.

Works with canonical sportsedge.markets.allmarkets_research Market, Outcome,
ScoreEvent and settle contracts. Original quote/final JSON bytes are required;
SHA256 and timestamp fields in an archive manifest must match. A claimed
source/clock does not independently authenticate a sportsbook or final.
No wagers, verified bets, signed immutable receipts, or profitable EV claims.
NHL is not yet in the all-markets settlement kernel and remains blocked.

CLI:
 python -m sportsedge.validation.paper_ledger private/bundle.json \
    --database private/research.sqlite3

Private input/SQLite files must NEVER be committed to public GitHub.
"""
from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
from urllib.parse import quote
from types import SimpleNamespace

from sportsedge.markets.allmarkets_research import Market, Outcome, ScoreEvent, settle


class Blocked(ValueError):
    pass


REPO_ROOT = Path(__file__).resolve().parents[2]
MAX_EVIDENCE_BYTES = 5_000_000


def private_file(path, label, *, required=True):
    """Guard both lexical and resolved paths, including all symlinked parents.

    The directory must be owner-private. A 0600 file is mandatory for existing
    evidence/SQLite. Never place private wagers, IDs or finals in public GitHub.
    """
    if not isinstance(path, (str, os.PathLike)):
        raise Blocked("Invalid private path: " + label)
    lexical = Path(os.path.abspath(os.fspath(path)))
    resolved = lexical.resolve()
    if (lexical == REPO_ROOT or REPO_ROOT in lexical.parents
            or resolved == REPO_ROOT or REPO_ROOT in resolved.parents):
        raise Blocked("Public repository path refused: " + label)
    if any(part.is_symlink() for part in (lexical, *lexical.parents)):
        raise Blocked("Symlinked private path refused: " + label)
    if not resolved.parent.is_dir() or stat.S_IMODE(resolved.parent.stat().st_mode) & 0o077:
        raise Blocked("Private parent directory 0700 required: " + label)
    if required:
        if not resolved.is_file() or stat.S_IMODE(resolved.stat().st_mode) & 0o077:
            raise Blocked("Owner-only 0600 file required: " + label)
    elif resolved.exists() and (not resolved.is_file()
                               or stat.S_IMODE(resolved.stat().st_mode) & 0o077):
        raise Blocked("Existing private file must be owner-only: " + label)
    return resolved


def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise Blocked("Duplicate original JSON field")
            result[key] = value
        return result

    def reject_nonfinite(value):
        raise Blocked("Nonfinite original JSON number")
    try:
        return json.loads(raw, object_pairs_hook=unique,
                          parse_constant=reject_nonfinite)
    except (ValueError, UnicodeError) as exc:
        raise Blocked("Corrupt or ambiguous original JSON evidence") from exc


def time_utc(raw):
    try:
        x=datetime.fromisoformat(raw.replace("Z","+00:00"))
        if x.tzinfo is None:
            raise ValueError("naive timestamp")
        return x.astimezone(timezone.utc)
    except (AttributeError, ValueError) as ex:
        raise Blocked("timezone-qualified UTC timestamp required") from ex


def source(root, cfg, cutoff, direction):
    if not isinstance(cfg,dict) or not all(k in cfg for k in
           ("path","sha256","captured_at_utc")):
        raise Blocked("Original evidence path/hash/capture missing")
    relative=cfg["path"]
    if (not isinstance(relative, str) or not relative or
            Path(relative).is_absolute() or
            any(part in ("", ".", "..") for part in relative.split("/")) or
            "\\" in relative):
        raise Blocked("Original source path must be private and relative")
    path=private_file(root/relative, "ORIGINAL_SOURCE")
    if not path.is_relative_to(root.resolve()):
        raise Blocked("Source path must be within private manifest folder")
    if not 0 < path.stat().st_size <= MAX_EVIDENCE_BYTES:
        raise Blocked("Original evidence size invalid")
    raw=path.read_bytes()
    if not 0 < len(raw) <= MAX_EVIDENCE_BYTES:
        raise Blocked("Original evidence unusually large")
    digest=hashlib.sha256(raw).hexdigest()
    if digest!=cfg["sha256"] or len(cfg["sha256"])!=64:
        raise Blocked("Original evidence bytes mismatch")
    clock=time_utc(cfg["captured_at_utc"])
    if direction=="pregame" and not clock<cutoff:
        raise Blocked("Pregame quote captured at/after kickoff")
    if direction=="postgame" and not clock>cutoff:
        raise Blocked("Postgame final captured before kickoff")
    return strict_json(raw.decode("utf-8")),clock,digest


def price_decimal(odds):
    if isinstance(odds,bool) or type(odds)!=int or not 100<=abs(odds)<=20000:
        raise Blocked("Invalid American price")
    o=Decimal(odds)
    return Decimal(1)+(o/100 if o>0 else 100/-o)


def novig_pair(q):
    if q.get("book")!="DraftKings":
        raise Blocked("DK-only taken/close market price required")
    placeholders={"NOT_CAPTURED","UNKNOWN","UNVERIFIED","N/A","NONE","NULL","MISSING"}
    for k in ("quote_id","provider_event_id","provider_market_id"):
        value=q.get(k)
        if (not isinstance(value,str) or not value.strip()
            or value.strip().upper().replace(" ","_") in placeholders):
            raise Blocked("Missing provider original selection IDs")
    try:
        m=Market(**q["market"])
        other=Market(**q["opposite_market"])
    except (TypeError,KeyError,ValueError) as ex:
        raise Blocked("Malformed/unsupported market contract") from ex
    if not m.opposite(other):
        raise Blocked("Two-sided quote does not pair by same market definition")
    own_price=price_decimal(q["price_american"])
    other_price=price_decimal(q["opposite_price_american"])
    implied_own=1/own_price
    implied_other=1/other_price
    if implied_own+implied_other<=0:
        raise Blocked("Invalid opposing odds")
    return m,implied_own/(implied_own+implied_other)


def grade_bundle(bundle_path):
    bundle_path=private_file(bundle_path, "BUNDLE")
    if not 0 < bundle_path.stat().st_size <= MAX_EVIDENCE_BYTES:
        raise Blocked("Bundle evidence size invalid")
    root=bundle_path.parent
    b=strict_json(bundle_path.read_text(encoding="utf-8"))
    if not isinstance(b, dict):
        raise Blocked("Bundle JSON object required")
    if not isinstance(b.get("pick_id"),str) or not b["pick_id"] or len(b["pick_id"])>128:
        raise Blocked("Missing/oversized selection ID")
    kickoff=time_utc(b["kickoff_utc"])
    taken,tclock,thash=source(root,b["taken"],kickoff,"pregame")
    m,p_take=novig_pair(taken)
    if m.event_id!=b["event_id"]:
        raise Blocked("Source market event does not match selection")
    close_spec=b.get("close")
    p_close=None;chash=None;closeid=None
    if close_spec is not None:
        close,cclock,chash=source(root,close_spec,kickoff,"pregame")
        cm,p_close=novig_pair(close)
        if not 0<(kickoff-cclock).total_seconds()<=600:
            raise Blocked("Closing quote not inside 10-minute pregame window")
        if (cm.identity()!=m.identity() or
            close["provider_event_id"]!=taken["provider_event_id"] or
            close["provider_market_id"]!=taken["provider_market_id"] or
            close["book"]!=taken["book"]):
            raise Blocked("Closing offer not same DK event/market/side/line/period")
        if cclock<=tclock or close["quote_id"]==taken["quote_id"]:
            raise Blocked("Closing quote missing later independent observation")
        closeid=close["quote_id"]
    final,fclock,fhash=source(root,b["final"],kickoff,"postgame")
    if final.get("final_status")!="FINAL" or final.get("event_id")!=m.event_id or final.get("sport")!=m.sport:
        raise Blocked("Final source not marked settled for same sport/event")
    try:
        events=tuple(ScoreEvent(**e) for e in final.get("events",[]))
        outcome=Outcome(
            periods={k:tuple(v) for k,v in final["periods"].items()},
            player_stats=final.get("player_stats",{}),
            events=events,
            events_complete=final.get("events_complete",False),
            player_period_stats=final.get("player_period_stats",{}))
        batch=SimpleNamespace(sport=m.sport,event_id=m.event_id,
                              home_id=final["home_id"],away_id=final["away_id"],
                              roster_ids=frozenset(final.get("roster_ids",[])))
        grade=settle(batch,outcome,m)
    except (KeyError,TypeError,ValueError) as ex:
        raise Blocked("Postgame final unable to settle exact selection: "+str(ex)) from ex
    if grade not in ("W","L","P"):
        raise Blocked("Incomplete market result")
    result={
        "pick_id":b["pick_id"],"status":"PAPER_GRADED_UNAUTHENTICATED",
        "selection_identity":list(m.identity()),"grade":grade,
        "taken_book":"DraftKings","taken_quote_id":taken["quote_id"],
        "closing_quote_id":closeid,
        "taken_novig_p":round(float(p_take),8),
        "closing_novig_p":round(float(p_close),8) if p_close is not None else None,
        "clv_probability_pp":round(float((p_close-p_take)*100),6) if p_close is not None else None,
        "close_status":"RESEARCH_COMPARABLE_UNAUTHENTICATED" if p_close is not None else "NO_COMPARABLE_CLOSE",
        "taken_sha256":thash,"closing_sha256":chash,"final_sha256":fhash,
        "asof_taken_utc":b["taken"]["captured_at_utc"],
        "asof_final_utc":b["final"]["captured_at_utc"],
        "source_authentication_independent":False,
        "approved_stake_u":0,"official_counted":0,
        "roi":"UNAVAILABLE_NO_AUTHORITATIVE_BET_LEDGER",
        "note":"Authenticated source chain and independent final audit are unproven; hashed source is not upstream proof."
    }
    return result


def append_ledger(db_path, result):
    """SQLite BEGIN IMMEDIATE + unique pick_id: no double-counting across agents.

    A local SHA256 hash chain detects accidental rewrites, not tamper-proof
    WORM storage or externally signed attestations.
    """
    db_path=private_file(db_path, "LEDGER", required=False)
    if not db_path.exists():
        # sqlite3.connect() creates files using the process umask (often
        # world-readable 0644). Create exclusively as 0600 before opening.
        flags=os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd=os.open(db_path, flags, 0o600)
        except FileExistsError:
            # Another agent may have created it. Validate permissions before
            # SQLite opens it; never overwrite or chmod an unknown file.
            private_file(db_path, "LEDGER")
        else:
            os.close(fd)
    private_file(db_path, "LEDGER")
    if not isinstance(result.get("selection_identity"), list) or not result["selection_identity"]:
        raise Blocked("Exact canonical market identity required")
    stable=json.dumps(result,sort_keys=True,separators=(",",":"),ensure_ascii=False)
    target_identity=json.dumps(result["selection_identity"],sort_keys=True,separators=(",",":"))
    with sqlite3.connect(db_path,timeout=15) as db:
        db.execute("CREATE TABLE IF NOT EXISTS ledger("
                   "seq INTEGER PRIMARY KEY AUTOINCREMENT,"
                   "pick_id TEXT NOT NULL UNIQUE,"
                   "payload TEXT NOT NULL,prev_sha TEXT NOT NULL,record_sha TEXT NOT NULL)")
        db.execute("BEGIN IMMEDIATE")
        # Before each append or idempotent read, validate the *entire* existing
        # chain inside the same write lock. A corrupt prefix must not be extended.
        prior="0"*64
        for old_id,old_payload,old_prev,old_sha in db.execute(
                "SELECT pick_id,payload,prev_sha,record_sha FROM ledger ORDER BY seq"):
            try:
                old_doc=json.loads(old_payload)
            except (ValueError,TypeError) as ex:
                raise Blocked("Existing ledger contains unreadable payload") from ex
            expected=hashlib.sha256((prior+"\n"+old_payload).encode("utf-8")).hexdigest()
            if old_id!=old_doc.get("pick_id") or old_prev!=prior or old_sha!=expected:
                raise Blocked("Existing ledger chain damaged; refusing append")
            if (old_id!=result["pick_id"] and
                json.dumps(old_doc.get("selection_identity"),sort_keys=True,separators=(",",":"))==target_identity):
                raise Blocked("Canonical selection already recorded under different pick ID")
            prior=old_sha
        existing=db.execute("SELECT payload,record_sha FROM ledger WHERE pick_id=?",
                            (result["pick_id"],)).fetchone()
        if existing is not None:
            if existing[0]!=stable:
                raise Blocked("Same pick ID but conflicting outcome/evidence; never overwrite")
            return {"status":"ALREADY_RECORDED","sha256":existing[1]}
        previous=db.execute("SELECT record_sha FROM ledger ORDER BY seq DESC LIMIT 1").fetchone()
        prev=previous[0] if previous else "0"*64
        record_sha=hashlib.sha256((prev+"\n"+stable).encode("utf-8")).hexdigest()
        db.execute("INSERT INTO ledger (pick_id,payload,prev_sha,record_sha) VALUES(?,?,?,?)",
                   (result["pick_id"],stable,prev,record_sha))
    return {"status":"APPENDED_PAPER","sha256":record_sha}


def verify_chain(db_path):
    # Read-only URI also prevents silently creating a nonexistent ledger.
    db_path=private_file(db_path, "LEDGER")
    uri="file:" + quote(str(db_path), safe="/") + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        rows=db.execute("SELECT pick_id,payload,prev_sha,record_sha FROM ledger ORDER BY seq").fetchall()
    previous="0"*64
    for pid,payload,prev,rec in rows:
        try:
            doc=json.loads(payload)
        except ValueError as ex:
            raise Blocked("Unreadable ledger row") from ex
        if pid!=doc.get("pick_id") or prev!=previous:
            raise Blocked("Ledger link corrupted")
        expected=hashlib.sha256((previous+"\n"+payload).encode("utf-8")).hexdigest()
        if rec!=expected:
            raise Blocked("Ledger payload altered")
        previous=rec
    return len(rows)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("bundle",type=Path)
    p.add_argument("--database",type=Path,required=True)
    a=p.parse_args()
    result=grade_bundle(a.bundle)
    appended=append_ledger(a.database,result)
    print(json.dumps({"pick_id":result["pick_id"],"grade":result["grade"],
                      "clv_pp":result["clv_probability_pp"],
                      "ledger":appended,"rows_verified":verify_chain(a.database),
                      "status":result["status"]},indent=2))


if __name__=="__main__":
    main()
