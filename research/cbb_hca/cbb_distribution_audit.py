"""Common-location residual CDF comparison; experimental ML research, PAPER / 0u.

Use only full-game-including-OT non-tied finals. Not spread/total settlement.
All families share centered deviations and the same optional prior-mean shift.
"""
import math
from statistics import mean,stdev


def _cf(a,b,x):
    tiny=1e-30;c=1.;d=1-(a+b)*x/(a+1)
    if abs(d)<tiny:d=tiny
    d=1/d;h=d
    for m in range(1,201):
        for aa in (m*(b-m)*x/((a-1+2*m)*(a+2*m)), -(a+m)*(a+b+m)*x/((a+2*m)*(a+1+2*m))):
            d=1+aa*d;c=1+aa/c
            if abs(d)<tiny:d=tiny
            if abs(c)<tiny:c=tiny
            d=1/d;delta=d*c;h*=delta
        if abs(delta-1)<3e-12:return h
    raise ValueError("BETA_NOT_CONVERGED")


def t_cdf(z,df):
    if not math.isfinite(z) or not math.isfinite(df) or df<=2:raise ValueError("INVALID_T_PARAMETERS")
    if z==0:return .5
    x=df/(df+z*z);a=df/2;b=.5
    if x>=1:return .5
    if x<=0:return float(z>0)
    front=math.exp(math.lgamma(a+b)-math.lgamma(a)-math.lgamma(b)+a*math.log(x)+b*math.log1p(-x))
    ib=front*_cf(a,b,x)/a if x<(a+1)/(a+b+2) else 1-front*_cf(b,a,1-x)/b
    return 1-.5*ib if z>0 else .5*ib


def probabilities(residuals,projected_margin,*,use_mean_location=False):
    residuals=list(residuals)
    if type(use_mean_location) is not bool or len(residuals)<5:
        raise ValueError("INVALID_LOCATION_POLICY_OR_TRAINING_N")
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in (*residuals,projected_margin)):
        raise ValueError("FINITE_VALUES_REQUIRED")
    mu=mean(residuals);sd=stdev(residuals)
    if sd<=1e-12:raise ValueError("DEGENERATE_RESIDUAL_VARIANCE")
    deviations=[r-mu for r in residuals];shift=mu if use_mean_location else 0.
    var=mean(v*v for v in deviations);excess=mean(v**4 for v in deviations)/(var*var)-3
    df=100. if excess<=.0625 else min(100.,4+6/excess)
    scale=sd*math.sqrt((df-2)/df);threshold=-projected_margin-shift
    empirical=(sum(v>threshold for v in deviations)+.5*sum(v==threshold for v in deviations))/len(deviations)
    return dict(normal=.5*(1+math.erf((projected_margin+shift)/sd/math.sqrt(2))),
                student_t=t_cdf((projected_margin+shift)/scale,df),empirical=empirical,
                training_n=len(residuals),location=shift,residual_sd=sd,student_df=df,
                empirical_equality_policy="MID_DISTRIBUTION_NOT_OT_SIMULATION")


def reliability(ps,ys,*,bins=10):
    if len(ps)!=len(ys) or type(bins) is not int or bins<1:raise ValueError("INVALID_CALIBRATION_INPUT")
    groups=[[] for _ in range(bins)]
    for p,y in zip(ps,ys):
        if type(p) not in (int,float) or not math.isfinite(p) or not 0<=p<=1 or type(y) is not int or y not in (0,1):
            raise ValueError("INVALID_PROBABILITY_OR_OUTCOME")
        groups[min(bins-1,int(p*bins))].append((p,y))
    return [dict(lower=i/bins,upper=(i+1)/bins,n=len(g),predicted=mean(p for p,y in g) if g else None,
                 observed=mean(y for p,y in g) if g else None) for i,g in enumerate(groups)]
