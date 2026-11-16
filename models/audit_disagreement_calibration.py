"""G2/G3 frozen prediction audit; research only, never alters picks.

CSV columns: event_id,market,selection,model_p,market_p,outcome,
snapshot_utc,kickoff_utc,final_utc,model_sha256,source_sha256,odds.
outcome is 1 win / 0 loss; pushes and unsettled rows excluded.
Market probability must be independently sourced/de-vigged upstream.
"""
import argparse,csv,datetime as dt,json,math,hashlib,io,os
from pathlib import Path
from collections import Counter, defaultdict
FIELDS=("event_id","market","selection","model_p","market_p","outcome","snapshot_utc","kickoff_utc","final_utc","model_sha256","source_sha256","odds")
def utc(s):
    d=dt.datetime.fromisoformat(s.replace("Z","+00:00"))
    if d.tzinfo is None or d.utcoffset()!=dt.timedelta(0): raise ValueError("non-UTC timestamp")
    return d
def parse(rows):
    rows=list(rows)
    # Never select the first among conflicting frozen records. All duplicate
    # copies are held until source reconciliation, independent of file order.
    counts=Counter((r.get('event_id'),r.get('market'),r.get('selection'),
                    r.get('snapshot_utc')) for r in rows)
    good=[];blocked=[]
    for i,r in enumerate(rows,2):
        try:
            if any(not r.get(k) for k in FIELDS):raise ValueError("MISSING_FIELD")
            k=(r["event_id"],r["market"],r["selection"],r["snapshot_utc"])
            if counts[k]>1:raise ValueError("DUPLICATE")
            for h in ("model_sha256","source_sha256"):
                s=r[h]
                if len(s)!=64 or any(c not in "0123456789abcdef" for c in s):raise ValueError("INVALID_HASH")
            if not utc(r["snapshot_utc"])<utc(r["kickoff_utc"])<utc(r["final_utc"]):raise ValueError("LOOKAHEAD")
            p=float(r["model_p"]);q=float(r["market_p"])
            if not all(math.isfinite(x) and 0<x<1 for x in (p,q)):raise ValueError("INVALID_PROBABILITY")
            if r["outcome"] not in ("0","1"):raise ValueError("UNSETTLED_OR_PUSH")
            odds=int(r["odds"]); profit=(odds/100 if odds>=100 else 100/abs(odds)) if abs(odds)>=100 else None
            if profit is None or odds==0:raise ValueError("INVALID_ODDS")
            good.append((r["market"],p,q,int(r["outcome"]),profit,r["event_id"]))
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
