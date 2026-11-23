exec(open('run.py').read().split('out.sort')[0].replace('out=[]','out=[];RAW=[]').replace("  marg=ph-pa; t=pa+ph","  marg=ph-pa; t=pa+ph; RAW.append((g,marg,t,pa,ph))"))
import statistics as st
# fit margin scale and total offset to market (calibration, not picks)
mm=[(-g[2],m) for g,m,t,_,_ in RAW]; k=sum(a*b for a,b in mm)/sum(b*b for a,b in mm)
toff=st.mean(g[5]-t for g,m,t,_,_ in RAW)
print(f"margin scale k={k:.2f}  total offset={toff:+.1f}")
out=[]
for g,m,t,pa,ph in RAW:
  a,h,sp,spa,sph,tot,to,tu,mla,mlh,tta,tth=g
  m2=m*k; t2=t+toff; pa2=(t2-m2)/2; ph2=(t2+m2)/2
  def add(mk,side,line,price,pm,opp):
    q=nv(price,opp)[0]; pb=0.5*pm+0.5*q; out.append((pb*dec(price)-1,f"{a}@{h}",mk,side,line,price,pm,q,round(pa2,1),round(ph2,1)))
  c=N((m2+sp)/SDM); add('SPREAD',h,sp,sph,c,spa); add('SPREAD',a,-sp,spa,1-c,sph)
  po=1-N((tot-t2)/SDT); add('TOTAL','O',tot,to,po,tu); add('TOTAL','U',tot,tu,1-po,to)
  if mla and abs(mla)<1000: w=N(m2/SDM); add('ML',h,'',mlh,w,mla); add('ML',a,'',mla,1-w,mlh)
  for nm,(l,o,u),pr in((a,tta,pa2),(h,tth,ph2)):
    p=1-N((l-pr)/SDTT); add('TT',nm+' O',l,o,p,u); add('TT',nm+' U',l,u,1-p,o)
out.sort(key=lambda x:-x[0])
top=[r for r in out if r[0]>0.03]
from collections import Counter
print(len(top),"plays >3% EV")
for r in top: print(f"{r[0]*100:+5.1f}% {r[1]:18s} {r[2]:6s} {r[3]:12s} {r[4]!s:6s} {r[5]:+5d} proj {r[8]}-{r[9]}")
