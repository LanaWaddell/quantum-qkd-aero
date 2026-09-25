import numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import rcParams
rcParams["font.family"] = "TeX Gyre Heros Cn"
rcParams["svg.fonttype"] = "none"
INK="#1B1F2A"; PHYS="#1F6F8B"; LEARN="#C98A2B"; DRIFT="#A8453E"; MUTE="#8A8F98"; PAPER="#F3F4F0"
rng=np.random.default_rng(7)

# ---- Hero: one satellite pass, transmittance in log-eta ----
T=600.0; dt=0.5; t=np.arange(0,T,dt); n=len(t)
# orbital-pass backbone: elevation arch (circular orbit, symmetric pass), max elev 60 deg
elev=np.deg2rad(60)*np.sin(np.pi*t/T)
elev=np.clip(elev,np.deg2rad(5),None)
airmass=1/np.sin(elev)
tau0=0.25
eta_geo=np.exp(-tau0*airmass)             # Beer-Lambert extinction
# diffraction capture ~ (D/(w0+theta*L))^2, slant range grows near horizon
R_e=6371.0; h=500.0
slant=np.sqrt((R_e*np.sin(elev))**2+2*R_e*h+h**2)-R_e*np.sin(elev)
capture=np.minimum(1.0,(1.0/(1.0+10e-6*slant*1e3))**2)
eta_back=eta_geo*capture
# OU turbulence fading in log-eta
theta=1/8.0; sigma=0.55
x=np.zeros(n)
for i in range(1,n):
    x[i]=x[i-1]-theta*x[i-1]*dt+sigma*np.sqrt(dt)*rng.normal()
eta_turb=eta_back*np.exp(x-0.5*sigma**2/(2*theta))
# Markov cloud process: two-state, opaque-ish blocks
cloud=np.zeros(n,bool); state=False
p_on=0.004; p_off=0.02
for i in range(n):
    state = (not state) if rng.random()<(p_on if not state else p_off) else state
    cloud[i]=state
eta=eta_turb*np.where(cloud,0.03,1.0)

fig,ax=plt.subplots(2,1,figsize=(13,7.2),sharex=True,gridspec_kw=dict(height_ratios=[2.3,1.2],hspace=0.12))
fig.patch.set_alpha(0)
for a in ax:
    a.set_facecolor("none")
    for s in ("top","right"): a.spines[s].set_visible(False)
    a.spines["left"].set_color(MUTE); a.spines["bottom"].set_color(MUTE)
    a.tick_params(colors=INK,labelsize=15)
a0=ax[0]
a0.plot(t,eta_back,color=PHYS,lw=2.2,ls=(0,(6,4)),label="orbital-pass backbone (deterministic)")
a0.plot(t,eta,color=INK,lw=1.1,alpha=0.9,label="composed transmittance η(t)")
for seg in np.ma.clump_masked(np.ma.masked_where(cloud,t)):
    a0.axvspan(t[seg.start],t[min(seg.stop,n-1)],color=DRIFT,alpha=0.12,lw=0)
a0.set_yscale("log"); a0.set_ylim(3e-6,1.5)
a0.set_ylabel("channel transmittance  η",fontsize=17,color=INK)
a0.legend(frameon=False,fontsize=15,loc="lower right",ncol=1)
a0.text(t[cloud].mean() if cloud.any() else 300,0.45,"cloud event (Markov)",color=DRIFT,fontsize=15,ha="center")
a0.text(470,0.15,"OU turbulence fading in log η\n(correlation time ≈ 8 s)",color=INK,fontsize=14,ha="center")

# reward signal: per-block estimated secure-key rate with estimator variance growing as counts shrink
B=20.0; edges=np.arange(0,T+B,B); centers=edges[:-1]+B/2
mu=0.5; eta_det=0.5; rate_true=[]; rate_est=[]; err=[]
for k in range(len(centers)):
    m=(t>=edges[k])&(t<edges[k+1]); e=eta[m].mean()
    gain=mu*e*eta_det
    Q=gain+2e-5; Ebit=(0.01*gain+1e-5)/Q
    def h2(p): p=np.clip(p,1e-9,1-1e-9); return -p*np.log2(p)-(1-p)*np.log2(1-p)
    r=max(0.0, Q*(1-2*h2(Ebit)))*0.5
    counts=max(Q*2e5*B,1.0)
    se=(r/np.sqrt(counts)*7+0.05*r) if r>0 else 0
    rate_true.append(r); rate_est.append(max(0,r+rng.normal(0,se))); err.append(se)
rate_true=np.array(rate_true); rate_est=np.array(rate_est); err=np.array(err)
a1=ax[1]
a1.step(centers,rate_true,where="mid",color=MUTE,lw=1.4,label="key rate the physics actually delivered (oracle)")
a1.errorbar(centers,rate_est,yerr=err,fmt="o",ms=4.5,color=LEARN,ecolor=LEARN,elinewidth=1.4,capsize=3,label="what the learner receives: estimate, after the block closes")
a1.set_ylim(0,rate_true.max()*1.35); a1.ticklabel_format(axis="y",style="sci",scilimits=(0,0)); a1.yaxis.get_offset_text().set_fontsize(13)
a1.set_ylabel("secure key per pulse, per block",fontsize=16,color=INK)
a1.set_xlabel("time in pass (s)   —   each block = 20 s of decisions before any reward arrives",fontsize=16,color=INK)
a1.legend(frameon=False,fontsize=14,loc="upper left")
fig.savefig("figures/hero.svg",bbox_inches="tight",transparent=True)

# ---- Small figure: the block-length dilemma ----
fig,ax=plt.subplots(figsize=(5.8,3.8)); fig.patch.set_alpha(0); ax.set_facecolor("none")
for sp in ("top","right"): ax.spines[sp].set_visible(False)
ax.spines["left"].set_color(MUTE); ax.spines["bottom"].set_color(MUTE); ax.tick_params(colors=INK,labelsize=14)
L=np.linspace(0.5,60,300)
counts=2.5e-4*2e5*L      # illustrative sifted-count scale
est=1/np.sqrt(counts)
drift=0.3*np.sqrt(L/300.0)
ax.plot(L,est,color=LEARN,lw=2.2,label="estimator noise on the reward, falling as 1/√counts")
ax.plot(L,drift,color=DRIFT,lw=2.2,label="channel drift inside the block (slow component, τ ≈ 5 min)")
tot=np.sqrt(est**2+drift**2)
ax.plot(L,tot,color=INK,lw=2.6,label="combined error the agent must live with")
k=np.argmin(tot); ax.plot(L[k],tot[k],"o",color=INK,ms=7)
ax.text(L[k]+3,tot[k]*0.62,"the optimum moves with η and τ,\nso the agent has to learn it",fontsize=13,color=INK)
ax.set_xlabel("block length chosen by the agent (s)",fontsize=15,color=INK)
ax.set_ylabel("relative error in what it learns",fontsize=15,color=INK)
ax.set_yscale("log"); ax.legend(frameon=False,fontsize=12.5,loc="upper center",bbox_to_anchor=(0.5,-0.22),ncol=1)
fig.savefig("figures/variance.svg",bbox_inches="tight",transparent=True)
print("ok")
