import re, json, subprocess, sys, glob
U="/mnt/user-data/uploads/"
def txt(pat):
    f=glob.glob(U+pat)[0]
    return subprocess.run(["pdftotext","-layout",f,"-"],capture_output=True,text=True).stdout.replace("−","-")
NUM=re.compile(r"(?<![\w.])([+-]\d+(?:\.\d+)?|[OU] \d+(?:\.\d+)?)(?![\w.])")
def blocks(t, start_kw):
    return t.split("More Bets")
def parse_board(t):
    out=[]
    for b in t.split("More Bets"):
        if " AT " not in b and "\n" not in b: continue
        tm=re.search(r"Today (\d+:\d+ [AP]M)",b)
        if not tm: continue
        lines=[l for l in b.split("\n") if l.strip()]
        # drop header lines
        lines=[l for l in lines if not re.search(r"Spread|Total|Moneyline|Today|Half|Log In|Sports|Odds|Games|Lines|SEC|Scorers|Search|Futures|Top 25",l)]
        side="away"; names={"away":[],"home":[]}; toks={"away":[],"home":[]}
        for l in lines:
            s=l.strip()
            if s.startswith("AT"):
                toks["away"]+=NUM.findall(s); side="home"; continue
            nums=NUM.findall(s)
            rest=NUM.sub("",s); rest=re.sub(r"^\d+\s*","",rest.strip()); rest=re.sub(r"\s\d+$","",rest).strip()
            rest=re.sub(r"^\d+$","",rest)
            if rest: names[side].append(rest)
            toks[side]+=nums
        if not names["away"] or not names["home"]: continue
        a,h=toks["away"],toks["home"]
        def sp(x): return [v for v in x if not v.startswith(("O","U"))]
        def tot(x): 
            v=[v for v in x if v[0] in "OU"]; return float(v[0][2:]) if v else None
        # away tokens order: spread, O tot, [ML], spreadOdds, overOdds
        an,hn=sp(a),sp(h)
        def unpack(n):
            if len(n)==4: return float(n[0]),int(n[1]),int(n[2]),int(n[3])
            if len(n)==3: return float(n[0]),None,int(n[1]),int(n[2])
            return None
        ua,uh=unpack(an),unpack(hn)
        if not ua or not uh: continue
        out.append({"kickoff_ct":tm.group(1),"awayTeam":" ".join(names["away"]),"homeTeam":" ".join(names["home"]),
          "spread":uh[0],"spreadHomeOdds":uh[2],"spreadAwayOdds":ua[2],"overUnder":tot(a),
          "overOdds":ua[3],"underOdds":uh[3],"homeMoneyline":uh[1],"awayMoneyline":ua[1]})
    return out
main=parse_board(txt("703e664e*"))
h1=parse_board(txt("d0b67a9b*"))
H1={(g["awayTeam"],g["homeTeam"]):g for g in h1}
for g in main:
    k=(g["awayTeam"],g["homeTeam"]); x=H1.get(k)
    if x: g.update(h1Spread=x["spread"],h1HomeOdds=x["spreadHomeOdds"],h1AwayOdds=x["spreadAwayOdds"],
                   h1Total=x["overUnder"],h1Over=x["overOdds"],h1Under=x["underOdds"])
# team totals
tt={}
t=txt("2a0fc0af*")
for m in re.finditer(r"\n\s*([A-Za-z&.' ]+): Team Total Points\s*\n\s*([+-]\d+)\s+([+-]\d+)(.*?)View More",t,re.S):
    ln=re.search(r"\n\s*(\d+\.5)\s+\1\s*\n",m.group(4)+"\n")
    if ln: tt[m.group(1).strip()]=(float(ln.group(1)),int(m.group(2)),int(m.group(3)))
for g in main:
    for side in ("home","away"):
        n=g[side+"Team"].replace(" ","")
        for k,v in tt.items():
            if k.replace(" ","")==n: g[side+"TT"],g[side+"TTOver"],g[side+"TTUnder"]=v
# props (milestone, one-sided over)
props=[]
for pat,mk in [("5d5a871c*","pass_yds"),("1a54d4a1*","rush_yds"),("917fd2cb*","rec_yds"),("b60abb72*","AUTO")]:
    t=txt(pat); game=None; L=[l for l in t.split("\n") if l.strip()]
    for i,l in enumerate(L):
        m=re.match(r"\s*(.+?)\s{2,}AT\s{2,}(.+?)\s*$",l)
        if m: game=(m.group(1).strip(),m.group(2).strip()); continue
        m=re.match(r"\s*([A-Z][\w'.\- ]+?(?:…|\s\([A-Z&]+\)))\s+(\d+)\+\s*$",l)
        if m and game and i+2<len(L):
            o=re.search(r"([+-]\d{3,4})",L[i+2])
            if not o: continue
            line=int(m.group(2)); market=mk
            if mk=="AUTO": market="receptions" if line<=15 else "rec_yds"
            nm=re.sub(r"\s\([A-Z&]+\)$","",m.group(1)).rstrip("…").strip()
            tm=re.search(r"\(([A-Z&]+)\)",m.group(1))
            props.append({"away":game[0],"home":game[1],"player":nm,"teamAbbr":tm.group(1) if tm else None,
                          "market":market,"line":line-0.5,"overOdds":int(o.group(1))})
json.dump({"captured":"2026-11-21T10:24-10:27 CT DraftKings (uploaded screenshots)","lines":main,"props":props},
          open(sys.argv[1],"w"),indent=1)
print(len(main),"games",len(props),"props")
for g in main:
    if "UCLA" in g["awayTeam"] or "LSU" in g["awayTeam"]: print(g)
print([p for p in props if p["home"] in("Michigan","Tennessee")][:6])
