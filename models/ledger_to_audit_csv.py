"""Convert a human markdown grade ledger to audit intake WITHOUT fabricating evidence.

Only explicit WIN/LOSS outcomes are carried. Missing point-in-time model
probabilities, market no-vig probabilities and source hashes remain blank;
G2/G3 intentionally rejects these rows until authenticated captures join them.
"""
import argparse,csv,re
FIELDS=("event_id","market","selection","model_p","market_p","outcome","snapshot_utc","kickoff_utc","final_utc","model_sha256","source_sha256","odds","source_status")
def convert(text):
    section="";out=[]
    for line in text.splitlines():
        if line.startswith("## "):section=line[3:].strip()
        if not line.startswith("|") or line.startswith("|---"):continue
        cells=[c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells)!=3 or cells[0]=="Play":continue
        play,odds,result=cells
        m=re.fullmatch(r"[+-]\d+",odds)
        status=re.match(r"^(WIN|LOSS)\b",result)
        if not m:continue
        outcome={"WIN":"1","LOSS":"0"}.get(status.group(1)) if status else ""
        # Inferred prop grades are not authenticated actual player outcomes.
        if "inferred" in result.lower() or "likely" in result.lower():outcome=""
        out.append(dict.fromkeys(FIELDS,"") | {"event_id":section,"selection":play,"odds":odds,"outcome":outcome,"source_status":"NOT_CAPTURED"} )
    return out
def main():
    p=argparse.ArgumentParser();p.add_argument("ledger");p.add_argument("output");a=p.parse_args()
    with open(a.ledger) as f:rows=convert(f.read())
    with open(a.output,"w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    print("Rows:",len(rows),"unverified:",len(rows))
if __name__=="__main__":main()
