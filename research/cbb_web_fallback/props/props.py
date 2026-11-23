"""CBB prop grader, 2026-11-23. PAPER research.
Rates: ESPN 2026-27 team stats pages (per game, small GP).
Shrink: rate_adj = (GP*rate + K*mkt_mean)/(GP+K), K=5, where mkt_mean is the Poisson-ish
mean that makes DK's shown rung fair after a 4.5% one-sided hold.
Count model: negative binomial (var = mu*(1+mu/R)), R by stat.
Prob = 50/50 model vs market-implied (DK only shows one side -> hold-adjusted implied).
Pace: game possessions / team AdjT (Torvik), via fallback run.py tempos."""
from math import lgamma,exp,log
TEMPO={'StBona':68.0,'AppSt':65.0,'VCU':69.2,'Prov':71.1,'CSU':68.8,'Arizona':72.1,'Oregon':68.9,'StJ':72.2}
LT=69.3
def pace(a,b,me): return (TEMPO[a]*TEMPO[b]/LT)/TEMPO[me]
R={'PTS':12.0,'REB':8.0,'AST':6.0,'3PM':4.0}
def nb_pmf(k,mu,r):
    p=r/(r+mu); return exp(lgamma(k+r)-lgamma(r)-lgamma(k+1)+r*log(p)+k*log(1-p))
def p_ge(k,mu,r): return 1-sum(nb_pmf(i,mu,r) for i in range(k))
def dec(o): return 1+(o/100 if o>0 else 100/-o)
def fair_imp(o,hold=0.045): return (1/dec(o))/(1+hold)
def mkt_mean(k,o,r):
    t=fair_imp(o); lo,hi=0.01,60
    for _ in range(60):
        m=(lo+hi)/2
        if p_ge(k,m,r)<t: lo=m
        else: hi=m
    return m
# (player, team, opp, stat, rung k, DK price, GP, rate/g)
P=[
('Benjamin Bill','StBona','AppSt','PTS',15,-105,4,15.5),('Zach Philipkoski','StBona','AppSt','PTS',12,-130,4,16.3),
('Ari Fulton','StBona','AppSt','PTS',12,105,4,13.3),('Taj Au-Duke','StBona','AppSt','PTS',11,-105,4,9.0),
('Ilia Ermakov','StBona','AppSt','PTS',10,100,4,6.5),
('Blake Harper','VCU','Prov','PTS',16,-120,3,14.7),('Lazar Djokovic','VCU','Prov','PTS',15,-110,3,12.7),
('Miles Byrd','Prov','VCU','PTS',13,-125,4,11.0),('Arrinten Page','Prov','VCU','PTS',13,-115,2,7.5),
('Malik Mack','Prov','VCU','PTS',13,-110,4,12.0),('Nyk Lewis','VCU','Prov','PTS',12,-120,3,13.7),
('Ryan Mela','Prov','VCU','PTS',12,-140,3,9.7),('Brandon Jennings','VCU','Prov','PTS',8,100,3,5.7),
('Michael Belle','VCU','Prov','PTS',5,-105,3,4.3),
('Caleb Holt','Arizona','CSU','PTS',20,-110,3,15.0),('Motiejus Krivas','Arizona','CSU','PTS',18,110,3,18.0),
('Derek Dixon','Arizona','CSU','PTS',15,-115,3,13.0),
('Keyshawn Hall','StJ','Oregon','PTS',20,110,1,26.0),('Ian Jackson','StJ','Oregon','PTS',16,-120,1,15.0),
('Fred Payne','Oregon','StJ','PTS',15,-125,2,14.0),('Malique Ewin','Oregon','StJ','PTS',15,105,2,12.0),
('Jasper Johnson','Oregon','StJ','PTS',12,105,2,3.5),('Quinn Ellis','StJ','Oregon','PTS',12,125,1,8.0),
('Andrew Meadow','Oregon','StJ','PTS',10,-125,2,11.0),('Taylor Bol Bowen','Oregon','StJ','PTS',8,120,2,6.0),
('Ruben Prey','StJ','Oregon','PTS',7,-110,1,2.0),
# threes
('Zach Philipkoski','StBona','AppSt','3PM',2,-105,4,2.3),('Ilia Ermakov','StBona','AppSt','3PM',2,110,4,1.3),
('Ari Fulton','StBona','AppSt','3PM',2,160,4,1.3),('Miles Byrd','Prov','VCU','3PM',2,-170,4,1.8),
('Nyk Lewis','VCU','Prov','3PM',2,-170,3,2.3),('Malik Mack','Prov','VCU','3PM',2,-155,4,1.8),
('Arrinten Page','Prov','VCU','3PM',2,-140,2,1.5),('Blake Harper','VCU','Prov','3PM',2,-115,3,2.3),
('Lazar Djokovic','VCU','Prov','3PM',1,-165,3,0.3),('Brandon Jennings','VCU','Prov','3PM',1,-150,3,0.3),
('Ryan Mela','Prov','VCU','3PM',1,-130,3,0.7),('Michael Belle','VCU','Prov','3PM',1,165,3,0.7),
('Derek Dixon','Arizona','CSU','3PM',3,110,3,2.3),('Caleb Holt','Arizona','CSU','3PM',2,-115,3,0.3),
('Ian Jackson','StJ','Oregon','3PM',3,115,1,3.0),('Fred Payne','Oregon','StJ','3PM',2,-130,2,2.0),
('Keyshawn Hall','StJ','Oregon','3PM',2,-120,1,1.0),('Jasper Johnson','Oregon','StJ','3PM',2,-105,2,0.0),
('Andrew Meadow','Oregon','StJ','3PM',2,210,2,1.5),('Quinn Ellis','StJ','Oregon','3PM',2,215,1,0.0),
('Taylor Bol Bowen','Oregon','StJ','3PM',1,-145,2,0.5),('Ruben Prey','StJ','Oregon','3PM',1,100,1,0.0),
# rebounds
('Ari Fulton','StBona','AppSt','REB',8,100,4,8.3),('Benjamin Bill','StBona','AppSt','REB',8,130,4,7.3),
('Zach Philipkoski','StBona','AppSt','REB',5,-130,4,5.3),('Ilia Ermakov','StBona','AppSt','REB',5,145,4,4.5),
('Taj Au-Duke','StBona','AppSt','REB',3,-135,4,2.3),('Lazar Djokovic','VCU','Prov','REB',6,130,3,4.7),
('Arrinten Page','Prov','VCU','REB',5,-140,2,3.0),('Ryan Mela','Prov','VCU','REB',5,-140,3,5.3),
('Miles Byrd','Prov','VCU','REB',5,-125,4,5.3),('Blake Harper','VCU','Prov','REB',5,110,3,3.0),
('Michael Belle','VCU','Prov','REB',4,-140,3,5.0),('Nyk Lewis','VCU','Prov','REB',4,-135,3,3.7),
('Malik Mack','Prov','VCU','REB',3,-155,4,3.3),('Brandon Jennings','VCU','Prov','REB',4,155,3,2.7),
('Motiejus Krivas','Arizona','CSU','REB',11,110,3,8.0),('Caleb Holt','Arizona','CSU','REB',8,110,3,6.7),
('Derek Dixon','Arizona','CSU','REB',4,110,3,2.7),
('Malique Ewin','Oregon','StJ','REB',11,125,2,10.0),('Keyshawn Hall','StJ','Oregon','REB',7,100,1,9.0),
('Ruben Prey','StJ','Oregon','REB',6,110,1,4.0),('Quinn Ellis','StJ','Oregon','REB',5,115,1,5.0),
('Taylor Bol Bowen','Oregon','StJ','REB',5,130,2,5.0),('Fred Payne','Oregon','StJ','REB',3,-155,2,1.0),
('Andrew Meadow','Oregon','StJ','REB',3,115,2,0.5),('Ian Jackson','StJ','Oregon','REB',3,120,1,2.0),
('Jasper Johnson','Oregon','StJ','REB',3,135,2,1.0),
# assists
('Zach Philipkoski','StBona','AppSt','AST',4,115,4,4.0),('Taj Au-Duke','StBona','AppSt','AST',4,140,4,3.3),
('Ilia Ermakov','StBona','AppSt','AST',3,-115,4,3.5),('Benjamin Bill','StBona','AppSt','AST',2,100,4,1.5),
('Ari Fulton','StBona','AppSt','AST',1,-150,4,1.0),('Nyk Lewis','VCU','Prov','AST',4,140,3,4.3),
('Malik Mack','Prov','VCU','AST',4,155,4,3.3),('Blake Harper','VCU','Prov','AST',3,-150,3,3.3),
('Miles Byrd','Prov','VCU','AST',3,105,4,2.5),('Brandon Jennings','VCU','Prov','AST',3,130,3,1.7),
('Ryan Mela','Prov','VCU','AST',2,-105,3,2.0),('Lazar Djokovic','VCU','Prov','AST',2,120,3,2.0),
('Arrinten Page','Prov','VCU','AST',2,125,2,1.0),('Michael Belle','VCU','Prov','AST',1,-150,3,0.0),
('Derek Dixon','Arizona','CSU','AST',3,-150,3,2.7),('Caleb Holt','Arizona','CSU','AST',2,110,3,1.7),
('Motiejus Krivas','Arizona','CSU','AST',2,130,3,1.0),
('Quinn Ellis','StJ','Oregon','AST',9,135,1,7.0),('Fred Payne','Oregon','StJ','AST',4,-105,2,3.5),
('Keyshawn Hall','StJ','Oregon','AST',3,-155,1,2.0),('Jasper Johnson','Oregon','StJ','AST',3,-130,2,1.5),
('Malique Ewin','Oregon','StJ','AST',3,-125,2,4.5),('Ruben Prey','StJ','Oregon','AST',2,-140,1,1.0),
('Ian Jackson','StJ','Oregon','AST',2,105,1,0.0),('Taylor Bol Bowen','Oregon','StJ','AST',2,155,2,3.5),
('Andrew Meadow','Oregon','StJ','AST',1,-115,2,0.5),
]
K=5
rows=[]
for name,tm,op,st,k,o,gp,rate in P:
    r=R[st]; mm=mkt_mean(k,o,r); f=pace(tm,op,tm)
    mu=(gp*rate*f+K*mm)/(gp+K)
    pm=p_ge(k,mu,r); q=fair_imp(o); pb=0.5*pm+0.5*q; ev=pb*dec(o)-1
    rows.append((ev,name,tm,st,k,o,gp,rate,round(mu,1),pm,q))
rows.sort(key=lambda x:-x[0])
def stars(ev): return '★★★★' if ev>=.12 else '★★★' if ev>=.07 else '★★' if ev>=.04 else '★'
for ev,name,tm,st,k,o,gp,rate,mu,pm,q in rows:
    if ev<0.0: continue
    print(f"{ev*100:+5.1f}% {stars(ev):4s} {name:18s} {tm:7s} {st:3s} {k}+ {o:+d}  gp{gp} rate{rate} mu{mu} pm{pm:.2f} mkt{q:.2f}")
print('neg/flat EV:',sum(1 for x in rows if x[0]<0.03),'of',len(rows))
