"""PAPER/0u first-half prospective residual calibration.
Input is prejoined original frozen H1 means and observed regulation H1 finals.
This checks contracts and chronology; hashes alone do not authenticate sources.
No historical odds, pricing, or model promotion.
"""
from collections import Counter
from datetime import datetime
from statistics import mean, stdev
import math
import unittest

def stamp(s):
    if not isinstance(s,str) or not s.endswith("Z"):raise ValueError("UTC_Z_REQUIRED")
    return datetime.fromisoformat(s[:-1]+"+00:00")

def sha(s):
    return isinstance(s,str) and len(s)==64 and all(c in "0123456789abcdef" for c in s)

def pair(r, side):
    h,a=(r[side][k] for k in ("home","away"))
    if any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=200 for v in (h,a)):
        raise ValueError("INVALID_HALF_SCORE")
    if side=="actual" and any(type(v) is not int for v in (h,a)):
        raise ValueError("NONINTEGER_HALF_FINAL")
    return dict(home_tt=h,away_tt=a,total=h+a,margin=h-a)

def evaluate(records, *, min_train=50):
    if type(min_train) is not int or min_train<3:raise ValueError("INVALID_MIN_TRAIN")
    records=list(records)
    ids=Counter(r.get("event_id") for r in records if isinstance(r,dict) and isinstance(r.get("event_id"),str))
    admitted=[];holds=[]
    for i,r in enumerate(records):
        try:
            e=r["event_id"]
            if not isinstance(e,str) or not e.strip() or ids[e]!=1:raise ValueError("DUPLICATE_OR_INVALID_EVENT")
            if r["period"]!="H1" or r["settlement_scope"]!="REGULATION_FIRST_HALF_ONLY":raise ValueError("H1_CONTRACT_REQUIRED")
            if any(not sha(r.get(k)) for k in ("forecast_sha256","final_sha256")):raise ValueError("MISSING_SOURCE_DIGEST")
            if r["forecast_team_ids"]!=r["final_team_ids"] or len(r["forecast_team_ids"])!=2 or len(set(r["forecast_team_ids"]))!=2 or any(not isinstance(t,str) or not t for t in r["forecast_team_ids"]):raise ValueError("TEAM_IDENTITY_MISMATCH")
            f,t,o=(stamp(r[k]) for k in ("freeze_utc","tipoff_utc","final_observed_utc"))
            if not f<t<o:raise ValueError("INVALID_CHRONOLOGY")
            admitted.append(dict(event_id=e,f=f,o=o,p=pair(r,"forecast"),a=pair(r,"actual")))
        except (KeyError,TypeError,ValueError,AttributeError) as exc:holds.append(dict(index=i,reason=str(exc)))
    scored=[]
    for r in sorted(admitted,key=lambda x:(x["f"],x["event_id"])):
        prior=[x for x in admitted if x["o"]<r["f"]]
        if len(prior)<min_train:
            holds.append(dict(event_id=r["event_id"],reason="INSUFFICIENT_PRIOR_H1_FINALS"));continue
        for k in ("home_tt","away_tt","total","margin"):
            errors=[x["a"][k]-x["p"][k] for x in prior]
            loc,sd=mean(errors),stdev(errors)
            if not math.isfinite(sd) or sd<=0:
                holds.append(dict(event_id=r["event_id"],market=k,reason="DEGENERATE_RESIDUAL_SD"));continue
            line=math.floor(r["p"][k])+.5
            p=.5*math.erfc(-(r["p"][k]+loc-line)/(sd*math.sqrt(2)))
            p=min(1-1e-6,max(1e-6,p))
            y=int(r["a"][k]>line)
            scored.append(dict(event_id=r["event_id"],market=k,train_n=len(prior),diagnostic_line=line,p=p,y=y,error=r["p"][k]-r["a"][k],adjusted_error=r["p"][k]+loc-r["a"][k]))
    summary={}
    for k in ("home_tt","away_tt","total","margin"):
        rows=[x for x in scored if x["market"]==k]
        summary[k]=dict(n=len(rows),mae=mean(abs(x["error"]) for x in rows) if rows else None,
            adjusted_mae=mean(abs(x["adjusted_error"]) for x in rows) if rows else None,
            brier=mean((x["p"]-x["y"])**2 for x in rows) if rows else None,
            log_loss=mean(-math.log(x["p"] if x["y"] else 1-x["p"]) for x in rows) if rows else None)
    return dict(status="H1_PREJOINED_RESEARCH_SOURCE_AUTH_UNVERIFIED",input_n=len(records),admitted_n=len(admitted),
        holds=holds,summary=summary,rows=scored,approved_stake_u=0,official_counted=0,
        limitations=["Model-derived half-lines only; no actual bookmaker quotes or push pricing.",
        "Regulation first half; no final-score substitution. Caller must authenticate original sources and freeze receipts."])

class Regression(unittest.TestCase):
    def row(self,i):
        return dict(event_id=str(i),period="H1",settlement_scope="REGULATION_FIRST_HALF_ONLY",
            forecast_sha256="a"*64,final_sha256="b"*64,forecast_team_ids=["1","2"],final_team_ids=["1","2"],
            freeze_utc=f"2026-11-{i:02d}T12:00:00Z",tipoff_utc=f"2026-11-{i:02d}T18:00:00Z",
            final_observed_utc=f"2026-11-{i:02d}T22:00:00Z",forecast={"home":35.0,"away":33.0},
            actual={"home":34+i%4,"away":31+i%3})
    def test_prior_only(self):
        rows=[self.row(i) for i in range(1,9)]
        a=evaluate(rows,min_train=3)
        self.assertGreater(a["summary"]["total"]["n"],0)
        rows[-1]["actual"]["home"]=99
        b=evaluate(rows,min_train=3)
        self.assertEqual([r["p"] for r in a["rows"]],[r["p"] for r in b["rows"]])
    def test_contract_and_duplicate(self):
        a=self.row(1);b=self.row(2);b["period"]="FG"
        self.assertEqual(evaluate([a,a,b],min_train=3)["admitted_n"],0)
    def test_invalid_sources_and_scores(self):
        for k,v in (("forecast_sha256","bad"),("final_team_ids",["2","1"]),("actual",{"home":float("inf"),"away":30}),("final_observed_utc","2026-11-01T10:00:00Z")):
            r=self.row(1);r[k]=v
            self.assertEqual(evaluate([r],min_train=3)["admitted_n"],0)
    def test_same_clock_no_leakage(self):
        rows=[self.row(i) for i in range(1,5)]
        for r in rows:r["final_observed_utc"]="2026-11-05T22:00:00Z"
        self.assertEqual(evaluate(rows,min_train=3)["summary"]["total"]["n"],0)

if __name__=="__main__":unittest.main()
