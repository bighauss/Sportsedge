"""G2/G3 frozen prediction audit; research only, never alters picks.

CSV columns: event_id,market,selection,model_p,market_p,outcome,
snapshot_utc,kickoff_utc,final_utc,model_sha256,source_sha256,odds.
outcome is 1 win / 0 loss; pushes and unsettled rows excluded.
Market probability must be independently sourced/de-vigged upstream.
"""
import argparse,csv,datetime as dt,json,math,hashlib,io,os
from pathlib import Path
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
FIELDS=("event_id","market","selection","model_p","market_p","outcome","snapshot_utc","kickoff_utc","final_utc","model_sha256","source_sha256","odds")
def utc(s):
    d=dt.datetime.fromisoformat(s.replace("Z","+00:00"))
    if d.tzinfo is None or d.utcoffset()!=dt.timedelta(0): raise ValueError("non-UTC timestamp")
    return d
# Legacy eleven-column G2 datasets are still reportable as unverified
# research. Fully identified market rows must be complete and cannot silently
# mix with legacy copies of the same game/market/selection.
IDENTITY_FIELDS=("book","period","settlement","line","player_id","team_id","stat")
MANDATORY_EXTENDED=("sport","book","period","settlement")
LINE_MARKETS=frozenset(("spread","spreads","total","totals","teamtotal","teamtotals","tt",
                         "alternatespread","alternatetotal","playerprop","prop"))
PLAYER_MARKETS=frozenset(("playerprop","prop","attd","atd","firsttd","td2plus",
                          "firstbasket","homerun","anytimegoal","firstgoal"))

def _market_token(value):
    m=str(value).strip().casefold().replace(" ","").replace("_","").replace("-","")
    return {"moneyline":"ml","spreads":"spread","totals":"total",
            "teamtotals":"teamtotal"}.get(m,m)

def _book_id(value):
    v=" ".join(str(value).strip().casefold().split())
    return {"dk":"draftkings","draft kings":"draftkings",
            "fd":"fanduel","fan duel":"fanduel"}.get(v,v)

def _period_id(value):
    v=str(value).strip().casefold().replace(" ","").replace("_","").replace("-","")
    return {"fullgame":"fg","full":"fg","game":"fg",
            "firsthalf":"1h","h1":"1h","secondhalf":"2h","h2":"2h",
            "firstquarter":"1q","q1":"1q","secondquarter":"2q","q2":"2q",
            "thirdquarter":"3q","q3":"3q","fourthquarter":"4q","q4":"4q"}.get(v,v)

def _line(value):
    raw=str(value if value is not None else "").strip()
    if not raw:
        return ""
    try:
        d=Decimal(raw)
        if not d.is_finite():
            raise ValueError("NONFINITE_MARKET_LINE")
        return format(d.normalize(),"f")
    except (InvalidOperation,ValueError) as e:
        raise ValueError("INVALID_MARKET_LINE") from e

def _identity(row):
    """Snapshot-independent decision key. Duplicate records cannot inflate ROI.

    Exact book/period/line/participant identity preserves legitimate alternate
    lines, distinct players and separate independently reported books.
    """
    if not isinstance(row,dict):
        raise ValueError("INVALID_CSV_ROW")
    for name in ("event_id","market","selection"):
        if not isinstance(row.get(name),str) or not row[name].strip():
            raise ValueError("INCOMPLETE_BASE_SELECTION_ID")
    # Omit sport from the *ambiguity family* to quarantine mixed legacy
    # and full-identity copies. Exact keys still include sport separately.
    base=(row["event_id"].strip(),_market_token(row["market"]),
          row["selection"].strip().casefold())
    extended=any(str(row.get(x) or "").strip() for x in IDENTITY_FIELDS)
    if not extended:
        return base, ("LEGACY_UNATTESTED",*base), "LEGACY_UNATTESTED"
    missing=[x for x in MANDATORY_EXTENDED
             if not isinstance(row.get(x),str) or not row[x].strip()]
    if missing:
        raise ValueError("INCOMPLETE_EXTENDED_MARKET_ID:"+",".join(missing))
    market=base[1]
    line=_line(row.get("line"))
    if (market in LINE_MARKETS or
            market.startswith("alt") or
            "prop" in market or "yard" in market or "point" in market or
            "reception" in market or "assist" in market or "rebound" in market or
            "shot" in market or "save" in market) and not line:
        raise ValueError("EXTENDED_NUMERIC_LINE_REQUIRED")
    player=str(row.get("player_id") or "").strip().casefold()
    team=str(row.get("team_id") or "").strip().casefold()
    stat=str(row.get("stat") or "").strip().casefold()
    if ("prop" in market or market in PLAYER_MARKETS) and (not player or not stat):
        raise ValueError("EXTENDED_PROP_PLAYER_AND_STAT_REQUIRED")
    if market in ("teamtotal","teamtotals","tt") and not team:
        raise ValueError("EXTENDED_TEAM_TOTAL_SUBJECT_REQUIRED")
    key=("EXACT_MARKET",row["sport"].strip().upper(),*base,
         _book_id(row["book"]),_period_id(row["period"]),
         row["settlement"].strip().casefold(),line,player,team,stat)
    return base,key,"EXACT_MARKET"

def parse(rows):
    rows=list(rows)
    # First pass: count every reconstructible decision independent of
    # screenshot clock. A malformed duplicate must not poison the valid copy.
    keys=[];bases=defaultdict(set);counts=Counter();invalid_bases=set()
    for r in rows:
        try:
            base,k,mode=_identity(r)
            keys.append((base,k,mode))
            counts[k]+=1
            bases[base].add(mode)
        except (ValueError,TypeError,AttributeError):
            keys.append(None)
            if isinstance(r,dict) and all(isinstance(r.get(f),str) and
                                         r[f].strip() for f in
                                         ("event_id","market","selection")):
                invalid_bases.add((r["event_id"].strip(),
                                   _market_token(r["market"]),
                                   r["selection"].strip().casefold()))
    good=[];blocked=[]
    for i,r in enumerate(rows,2):
        try:
            k=keys[i-2]
            if k is None:
                _identity(r)  # preserve the exact identity error
                raise ValueError("INVALID_DECISION_IDENTITY")
            base,identity,mode=k
            if (base in invalid_bases or len(bases[base])>1):
                raise ValueError("MIXED_OR_MALFORMED_DECISION_IDENTITY_ALL_COPIES_BLOCKED")
            if counts[identity]>1:
                raise ValueError("DUPLICATE" if mode=="LEGACY_UNATTESTED" else
                                 "DUPLICATE_DECISION_ALL_SNAPSHOTS_BLOCKED")
            if any(not r.get(f) for f in FIELDS):raise ValueError("MISSING_FIELD")
            for h in ("model_sha256","source_sha256"):
                s=r[h]
                if len(s)!=64 or any(c not in "0123456789abcdef" for c in s):raise ValueError("INVALID_HASH")
            if not utc(r["snapshot_utc"])<utc(r["kickoff_utc"])<utc(r["final_utc"]):raise ValueError("LOOKAHEAD")
            p=float(r["model_p"]);q=float(r["market_p"])
            if not all(math.isfinite(x) and 0<x<1 for x in (p,q)):raise ValueError("INVALID_PROBABILITY")
            if r["outcome"] not in ("0","1"):raise ValueError("UNSETTLED_OR_PUSH")
            odds=int(r["odds"]); profit=(odds/100 if odds>=100 else 100/abs(odds)) if abs(odds)>=100 else None
            if profit is None or odds==0:raise ValueError("INVALID_ODDS")
            stratum=(r["market"] if mode=="LEGACY_UNATTESTED" else
                     "|".join((r["sport"].strip().upper(),_market_token(r["market"]),
                               _book_id(r["book"]),_period_id(r["period"]),
                               r["settlement"].strip().casefold())))
            good.append((stratum,p,q,int(r["outcome"]),profit,r["event_id"]))
        except (ValueError,TypeError,KeyError) as e:blocked.append({"row":i,"reason":str(e)})
    return good,blocked
def bucket(x):
    """No four-place rounding: that had advanced 4.996pp into the 5-10pp band.

    Tolerate only floating-point subtraction noise at the *exact* thresholds.
    A genuine 9.996pp gap remains below 10pp, while .6-.5 is exactly 10pp.
    """
    a=abs(float(x))
    if not math.isfinite(a):raise ValueError("INVALID_DISAGREEMENT")
    for boundary,label in ((.05,"0-5pp"),(.10,"5-10pp"),(.20,"10-20pp")):
        if a<boundary and not math.isclose(a,boundary,rel_tol=0,abs_tol=1e-12):
            return label
    return "20pp+"
def stats(rows):
    n=len(rows)
    if not n:return {"n":0,"unique_events":0,"insufficient_unique_events_30":True,"event_dependent_selections":False,"roi_descriptive_only":True,"roi":None,"observed_wilson_95":None,"insufficient_n30":True,"brier":None,"market_brier":None,"log_loss":None,"market_log_loss":None,"bias":None,"observed":None,"predicted":None}
    wins=sum(y for _,_,_,y,_,_ in rows)
    z=1.95996398454; ph=wins/n; den=1+z*z/n
    mid=(ph+z*z/(2*n))/den; rad=z*math.sqrt(ph*(1-ph)/n+z*z/(4*n*n))/den
    events=len({event for *_,event in rows})
    # Wilson assumes independent Bernoulli observations. Multiple alt lines
    # from one game violate that assumption: show no misleading CI.
    wilson=([round(max(0,mid-rad),6),round(min(1,mid+rad),6)]
            if events==n else None)
    return {"n":n,"unique_events":events,
        "event_dependent_selections":events<n,
        "insufficient_unique_events_30":events<30,
        "insufficient_n30":n<30,"observed_wilson_95":wilson,"roi_descriptive_only":True,"roi":round(sum(profit if y else -1 for _,_,_,y,profit,_ in rows)/n,6),"brier":round(sum((p-y)**2 for _,p,q,y,_,_ in rows)/n,6),
        "market_brier":round(sum((q-y)**2 for _,p,q,y,_,_ in rows)/n,6),
        "log_loss":round(-sum(y*math.log(p)+(1-y)*math.log1p(-p) for _,p,q,y,_,_ in rows)/n,6),
        "market_log_loss":round(-sum(y*math.log(q)+(1-y)*math.log1p(-q) for _,p,q,y,_,_ in rows)/n,6),
        "bias":round(sum(p-y for _,p,q,y,_,_ in rows)/n,6),
        "observed":round(sum(y for _,p,q,y,_,_ in rows)/n,6),
        "predicted":round(sum(p for _,p,q,y,_,_ in rows)/n,6)}
def audit(rows):
    valid,blocked=parse(rows);groups=defaultdict(list);cal=defaultdict(list)
    for row in valid:
        m,p,q,y,_,event_id=row
        groups[(m,bucket(p-q),"model_above" if p>q else "model_below_or_equal")].append(row)
        cal[(m,min(9,int(p*10)))].append(row)
    return {"status":"RESEARCH_ONLY_NOT_VALIDATED_EV","accepted":len(valid),"blocked":blocked,
        "market_identity_note":"Extended source rows require sport, book, period, settlement and exact line/subject when applicable. Legacy rows are not price-authenticated; repeated decisions across snapshots and mixed identity copies are quarantined.",
        "overall":stats(valid),
        "disagreement":[{"market":m,"bucket":b,"direction":d,**stats(v)} for (m,b,d),v in sorted(groups.items())],
        "calibration":[{"market":m,"decile":d,**stats(v)} for (m,d),v in sorted(cal.items())],
        "caution":"ROI is hypothetical flat 1u per retained selection at original odds, NOT verified execution; correlated alt lines share events. A large number of selections with fewer than 30 distinct events is not sufficient independent evidence. Missing pushes excluded; no CLV, sportsbook-provider authentication, or original point-in-time feature certification."}

REPO_ROOT=Path(__file__).resolve().parents[1]

def _private_path(value):
    """Refuse source data or detailed result reports anywhere under public Git."""
    lexical=Path(os.path.abspath(os.fspath(value)))
    resolved=lexical.resolve()
    if any(p==REPO_ROOT or REPO_ROOT in p.parents for p in (lexical,resolved)):
        raise ValueError("PRIVATE_G2_DATA_OR_OUTPUT_INSIDE_PUBLIC_CHECKOUT")
    if lexical.is_symlink() or any(parent.is_symlink() for parent in lexical.parents):
        raise ValueError("UNTRUSTED_SYMLINK_PATH")
    return lexical

def _read_original_csv(path):
    """No silent duplicate-header aliasing or truncated/overlong evidence rows."""
    raw=path.read_bytes()
    try:
        decoded=raw.decode("utf-8-sig")
        reader=csv.DictReader(io.StringIO(decoded,newline=""))
        fields=reader.fieldnames
        if (not fields or len(fields)!=len(set(fields)) or
                not set(FIELDS).issubset(fields)):
            raise ValueError("MISSING_OR_DUPLICATE_CSV_HEADER")
        rows=list(reader)
        if any(None in row or any(value is None for value in row.values())
               for row in rows):
            raise ValueError("TRUNCATED_OR_OVERLONG_CSV_ROW")
    except (UnicodeError,csv.Error) as e:
        raise ValueError("CORRUPT_SOURCE_CSV") from e
    return rows,hashlib.sha256(raw).hexdigest()

def _create_private_report(path,output):
    """Create only with mode 0600; never overwrite an evidence file/report."""
    flags=os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os,"O_NOFOLLOW",0)
    fd=os.open(path,flags,0o600)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream:
            fd=-1
            stream.write(output)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        if fd>=0:
            os.close(fd)
        path.unlink(missing_ok=True)
        raise

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("csv")
    p.add_argument("--output")
    a=p.parse_args(argv)
    private_input=_private_path(a.csv)
    private_output=_private_path(a.output) if a.output else None
    rows,digest=_read_original_csv(private_input)
    result=audit(rows)
    result["input_sha256"]=digest
    result["input_original_provider_authenticated"]=False
    s=json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+"\n"
    if private_output:
        _create_private_report(private_output,s)
    else:
        print(s,end="")
    return 0

if __name__=="__main__":
    main()
