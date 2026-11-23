# Read-only reconstruction from Drive artifacts: sportsedge_nfl_wk11_run_v3.py (inputs inline)
# + sportsedge_nfl_wk11_v3_graded.csv (saved notes = engine-consumed M, T; per-side W/L).
S={'BUF':(9,287,199),'NE':(10,221,242),'NYJ':(10,194,254),'MIA':(9,148,224),'CIN':(9,278,193),'PIT':(9,198,182),'CLE':(10,188,220),'BAL':(10,209,259),'JAX':(9,269,144),'HOU':(10,259,222),'IND':(11,211,297),'TEN':(9,167,239),'KC':(9,237,156),'DEN':(9,198,186),'LV':(10,251,289),'LAC':(9,144,239),'NYG':(9,203,196),'DAL':(10,286,282),'WAS':(9,196,223),'PHI':(9,148,221),'DET':(9,257,199),'MIN':(9,176,126),'CHI':(9,241,184),'GB':(10,226,221),'CAR':(9,219,236),'TB':(9,202,178),'NO':(9,202,236),'ATL':(10,201,258),'SF':(9,281,196),'SEA':(10,223,175),'LAR':(10,248,187),'ARI':(10,184,289)}
LG,K=22.5,8
def reg(t): g,pf,pa=S[t]; return (pf+LG*K)/(g+K),(pa+LG*K)/(g+K)
def raw(t): g,pf,pa=S[t]; return pf/g,pa/g
# away, home, home spread, total ; saved engine M (home) and T from graded notes; home cover result
G=[('NO','CHI',-11.5,48.5,6.7,46.6,'L'),('TB','DET',-3.5,47.5,3.2,45.8,'W'),('MIA','BUF',-16.5,44.5,10.7,46.4,'W'),
   ('ARI','KC',-15.5,40.5,10.8,45.3,'W'),('TEN','DAL',-7.5,54.5,5.2,48.3,'W'),('PIT','PHI',3.5,37.5,-3.8,43.2,'W'),
   ('BAL','CAR',-3,44.5,4.4,47.0,'L'),('NYJ','LAC',-3,41.5,1.1,44.3,'L'),('JAX','NYG',6,45.5,-5.6,45.1,'W'),
   ('LV','DEN',-10.5,40.5,6.3,46.9,'W'),('MIN','SF',-3.5,46.5,2.4,44.1,'W'),('CIN','WAS',6,54.5,-4.7,47.4,'pending')]
print("game     mkt_M  ratings_M(=engine)  stats_M(reg k8)  stats_M(raw)  | mkt_T  engine_T(=stats reg)  stats_T_check | home_cover")
rows=[]
for a,h,sp,tot,M,T,res in G:
    ho,hd=reg(h); ao,ad=reg(a); rho,rhd=raw(h); rao,rad=raw(a)
    sm=(ho+ad)/2-(ao+hd)/2; smr=(rho+rad)/2-(rao+rhd)/2
    st=(ho+ad)/2+(ao+hd)/2
    mm=-sp
    rows.append((mm,M,sm,smr,tot,T,st,res))
    print(f"{a}@{h:4} {mm:+6.1f} {M:+10.1f} {sm:+16.1f} {smr:+13.1f}  | {tot:5.1f} {T:10.1f} {st:16.1f} | {res}")
import statistics as s
def slope(x,y):
    mx,my=s.mean(x),s.mean(y); return sum((a-mx)*(b-my) for a,b in zip(x,y))/sum((a-mx)**2 for a in x)
mm=[r[0] for r in rows]; M=[r[1] for r in rows]; sm=[r[2] for r in rows]; smr=[r[3] for r in rows]
print(f"\nn={len(rows)} games")
print(f"slope engine_M on market_M      = {slope(mm,M):.2f}  (1.00 = same spread width as market)")
print(f"slope stats_M(reg) on market_M  = {slope(mm,sm):.2f}")
print(f"slope stats_M(raw) on market_M  = {slope(mm,smr):.2f}")
print(f"mean |engine_M| = {s.mean(abs(x) for x in M):.1f}  vs mean |market_M| = {s.mean(abs(x) for x in mm):.1f}")
print(f"engine_T - market_T: mean {s.mean(r[5]-r[4] for r in rows):+.1f}, slope {slope([r[4] for r in rows],[r[5] for r in rows]):.2f}")
print(f"max |engine_T - stats_T recomputed| = {max(abs(r[5]-r[6]) for r in rows):.2f}")
big=[r for r in rows if abs(r[0])>=7]
print(f"big-spread bucket (|mkt|>=7, set before results): n={len(big)}, engine keeps {s.mean(abs(r[1]) for r in big)/s.mean(abs(r[0]) for r in big):.0%} of market margin; favorite covered {sum(1 for r in big if r[7]=='W')}/{len([r for r in big if r[7]!='pending'])}")
