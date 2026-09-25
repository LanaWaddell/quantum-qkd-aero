"""Regenerates figures/results.svg (the poster's results panel) from results/*.json."""
import json, numpy as np, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib import rcParams
rcParams["font.family"]="TeX Gyre Heros Cn"; rcParams["svg.fonttype"]="none"
INK="#1B1F2A"; PHYS="#1F6F8B"; LEARN="#C98A2B"; DRIFT="#A8453E"; MUTE="#8A8F98"
rates=["1e+08","1e+07","1e+06","1e+05"]; cols=[INK,PHYS,LEARN,DRIFT]; names=["bright source","10× dimmer","100× dimmer","1000× dimmer"]
fig,ax=plt.subplots(1,2,figsize=(13,4.8),gridspec_kw=dict(width_ratios=[1.6,1],wspace=0.28)); fig.patch.set_alpha(0)
for a in ax:
    a.set_facecolor("none")
    for sp in ("top","right"): a.spines[sp].set_visible(False)
    a.spines["left"].set_color(MUTE); a.spines["bottom"].set_color(MUTE); a.tick_params(colors=INK,labelsize=14)
summary={}
for r,c,nm in zip(rates,cols,names):
    cv=json.load(open(f"results/agent_results_{r}.json"))["curve"]
    ratio=np.array([e["agent"]/e["static"] if e["static"]>0 else np.nan for e in cv]); ep=np.arange(len(ratio))
    ma=np.array([np.nanmean(ratio[max(0,i-15):i+1]) for i in ep])
    ax[0].plot(ep,ma,color=c,lw=2.2,label=nm)
    summary[r]={k:np.nanmean([e[k]/e["static"] for e in cv[-30:] if e["static"]>0]) for k in ("agent","reopt","oracle")}
ax[0].axhline(1.0,color=MUTE,lw=1.2,ls=(0,(4,3))); ax[0].text(2,1.012,"the fixed setting, never changed during a pass",fontsize=13,color=MUTE)
ax[0].set_ylim(0.6,1.05); ax[0].set_xlabel("satellite passes the learner has experienced",fontsize=15,color=INK)
ax[0].set_ylabel("key delivered, relative to the fixed setting",fontsize=14,color=INK); ax[0].legend(frameon=False,fontsize=12.5,loc="lower right",title="how bright the transmitter is",title_fontsize=12.5)
x=np.arange(len(rates)); w=0.26
for i,(k,c,lab) in enumerate([("oracle",MUTE,"a controller that can see the next block's conditions"),("reopt",PHYS,"a controller that reacts to the last block, with no memory"),("agent",LEARN,"the learner")]):
    ax[1].bar(x+(i-1)*w,[summary[r][k] for r in rates],w,color=c,label=lab)
ax[1].axhline(1.0,color=INK,lw=1.2,ls=(0,(4,3)))
ax[1].set_xticks(x); ax[1].set_xticklabels(["bright","10× dimmer","100× dimmer","1000× dimmer"],fontsize=12.5)
ax[1].set_ylim(0,1.55); ax[1].set_ylabel("share of what the fixed setting delivers",fontsize=13,color=INK); ax[1].legend(frameon=False,fontsize=11.5,loc="upper left")
fig.savefig("figures/results.svg",bbox_inches="tight",transparent=True)
print({r:{k:round(float(v),3) for k,v in s.items()} for r,s in summary.items()})
