"""Minimal learned controller for decoy-state BB84 over a drifting satellite channel.

Physics (gains, QBER, decoy bounds, key rate) is imported from Quantum-QKD-Aero
(src/qkd/bb84.py) and is not modified. Everything else here -- the channel
generator, the finite-count sampling of the reward, the agent, and the
baselines -- is experiment scaffolding written for the ML4QT 2026 poster and
lives outside the repository. Provenance: SIMULATED on top of the repo's
ANALYTIC block statistics; channel parameters ILLUSTRATIVE.
"""
import math, json
import numpy as np
from qkd.bb84 import _honest_gain, _honest_qber, estimate_decoy_bounds, secure_key_rate

# ----------------------------------------------------------------- channel
DT = 0.5; T = 600.0; TGRID = np.arange(0, T, DT); N = len(TGRID)
R_E, H = 6371.0, 500.0; TAU0 = 0.25
import os
DET_EFF = 0.5; Y0 = 1e-6; ED = 0.01; PULSE_RATE = float(os.environ.get('PULSE_RATE','1e8')); Q = 0.5
DECOY, VAC = 0.1, 0.0

def make_pass(rng, max_elev_deg=60.0, ou_sigma=0.55, ou_theta=1/8.0, p_on=0.004, p_off=0.02):
    elev = np.deg2rad(max_elev_deg) * np.sin(np.pi * TGRID / T)
    elev = np.clip(elev, np.deg2rad(5), None)
    airmass = 1 / np.sin(elev)
    eta_geo = np.exp(-TAU0 * airmass)
    slant = np.sqrt((R_E*np.sin(elev))**2 + 2*R_E*H + H**2) - R_E*np.sin(elev)
    capture = np.minimum(1.0, (1.0/(1.0 + 10e-6*slant*1e3))**2)
    back = eta_geo * capture
    x = np.zeros(N)
    for i in range(1, N):
        x[i] = x[i-1] - ou_theta*x[i-1]*DT + ou_sigma*math.sqrt(DT)*rng.normal()
    eta = back * np.exp(x - ou_sigma**2/(4*ou_theta))
    cloud = np.zeros(N, bool); s = False
    for i in range(N):
        s = (not s) if rng.random() < (p_on if not s else p_off) else s
        cloud[i] = s
    eta = eta * np.where(cloud, 0.03, 1.0)
    return dict(eta=np.clip(eta, 1e-9, 1.0), elev=np.rad2deg(elev), cloud=cloud)

# ------------------------------------------------------------------ reward
Z = 3.0   # confidence multiplier for the finite-count penalty (simplified Gaussian bounds, not a finite-key proof)

def block_key(eta_seg, mu, rng=None):
    """Certified secure key bits from one block.

    Counts are aggregated over the block (so drift inside the block feeds the
    decoy inversion), then the decoy bounds are evaluated at the conservative
    edge of a Z-sigma confidence interval on each count. rng=None evaluates the
    bounds at expected counts (deterministic, used by the oracle); rng given
    draws Poisson counts (what the system actually delivers and what the agent
    is paid). The finite-count penalty is experiment scaffolding, added outside
    the repository, so that block length has a physical cost."""
    intens = {"signal": mu, "decoy": DECOY, "vacuum": VAC}
    pulses_per_step = PULSE_RATE * DT / 3.0
    counts, errs = {}, {}
    for name, m in intens.items():
        g = np.array([_honest_gain(m, e*DET_EFF, Y0) for e in eta_seg])
        q = np.array([_honest_qber(m, e*DET_EFF, Y0, ED) for e in eta_seg])
        c = g * pulses_per_step; er = q * c
        if rng is None:
            counts[name], errs[name] = c.sum(), er.sum()
        else:
            cs = rng.poisson(c.sum()); es = rng.binomial(int(cs), float(er.sum()/c.sum()) if c.sum() > 0 else 0.0)
            counts[name], errs[name] = float(cs), float(es)
    n_each = pulses_per_step * len(eta_seg)
    lo = {k: max(counts[k] - Z*math.sqrt(counts[k]), 0.0)/n_each for k in intens}
    hi = {k: (counts[k] + Z*math.sqrt(counts[k]))/n_each for k in intens}
    nom = {k: counts[k]/n_each for k in intens}
    qnom = {k: (errs[k]/counts[k] if counts[k] > 0 else 0.0) for k in intens}
    qhi = {k: min((errs[k] + Z*math.sqrt(max(errs[k],1.0)))/max(counts[k] - Z*math.sqrt(counts[k]),1.0), 0.5) for k in intens}
    worst_gains = {"signal": hi["signal"], "decoy": lo["decoy"], "vacuum": hi["vacuum"]}
    worst_qber = {"signal": qhi["signal"], "decoy": qhi["decoy"], "vacuum": 0.5}
    try:
        y1, e1 = estimate_decoy_bounds(worst_gains, worst_qber, intens)
    except ValueError:
        return 0.0
    q1 = y1 * mu * math.exp(-mu)
    rate = secure_key_rate(nom["signal"], min(qhi["signal"], 0.5), q1, e1, q=Q)
    return rate * n_each * 3

# ------------------------------------------------------------------- arms
MUS = [0.2, 0.35, 0.5, 0.7, 0.9]
LENS = [5.0, 10.0, 20.0, 40.0]
ARMS = [(m, L) for m in MUS for L in LENS]

def run_pass(chan, policy, rng, seen_rng):
    """policy(context, t) -> arm index. Returns key (true), per-block log."""
    t = 0.0; total = 0.0; log = []
    prev_gain_est = None
    while t < T:
        i0 = int(t/DT)
        elev = chan["elev"][i0]
        ctx = context(elev, prev_gain_est)
        a = policy(ctx, t)
        mu, L = ARMS[a]
        i1 = min(N, int((t+L)/DT))
        seg = chan["eta"][i0:i1]
        if len(seg) == 0: break
        true_key = block_key(seg, mu)
        seen_key = block_key(seg, mu, seen_rng)
        prev_gain_est = seen_key/(L*PULSE_RATE)
        log.append(dict(t=t, arm=a, ctx=ctx, true=true_key, seen=seen_key))
        total += true_key
        yield_ = policy.update if hasattr(policy, "update") else None
        if yield_: yield_(ctx, a, seen_key/(L*PULSE_RATE*1e-3))   # reward scaled to key-per-pulse units x1e3
        t += L
    return total, log

def context(elev, prev_gain_est):
    eb = 0 if elev < 20 else (1 if elev < 40 else 2)
    if prev_gain_est is None: gb = 1
    else: gb = 0 if prev_gain_est < 2e-5 else (1 if prev_gain_est < 2e-4 else 2)
    return eb*3 + gb

# ------------------------------------------------------------------ agents
class DiscountedTS:
    """Gaussian Thompson sampling per (context, arm) with exponential forgetting,
    so old evidence decays as the channel regime moves."""
    def __init__(self, rng, gamma=0.995, prior_var=1.0, noise_var=0.05):
        self.rng = rng; self.g = gamma; self.pv = prior_var; self.nv = noise_var
        self.n = np.zeros((9, len(ARMS))); self.s = np.zeros((9, len(ARMS)))
    def __call__(self, ctx, t):
        n, s = self.n[ctx], self.s[ctx]
        post_var = 1/(1/self.pv + n/self.nv); post_mean = post_var * (s/self.nv)
        return int(np.argmax(self.rng.normal(post_mean, np.sqrt(post_var))))
    def update(self, ctx, a, r):
        self.n *= self.g; self.s *= self.g
        self.n[ctx, a] += 1; self.s[ctx, a] += r

class Static:
    def __init__(self, a): self.a = a
    def __call__(self, ctx, t): return self.a

class ReOptimizer:
    """No memory: picks the mu that is best for the eta implied by the last block, at fixed L=20."""
    def __init__(self): self.prev = None
    def __call__(self, ctx, t):
        gb = ctx % 3; eta_guess = [3e-4, 3e-3, 1e-2][gb]
        best = max(MUS, key=lambda m: block_key(np.array([eta_guess]*4), m))
        return ARMS.index((best, 20.0))

class Oracle:
    """Sees the true eta ahead; chooses the arm with the highest true key for the coming block."""
    def __init__(self, chan): self.chan = chan
    def __call__(self, ctx, t):
        i0 = int(t/DT); best, ba = -1, 0
        for a, (mu, L) in enumerate(ARMS):
            seg = self.chan["eta"][i0:min(N, int((t+L)/DT))]
            k = block_key(seg, mu)/L if len(seg) else 0   # per-second rate, fair across L
            if k > best: best, ba = k, a
        return ba

# --------------------------------------------------------------- experiment
def main(n_train=100, n_eval=30, seed=1):
    rng = np.random.default_rng(seed)
    # static baseline: best single arm on cloud-free nominal passes
    nominal = [make_pass(np.random.default_rng(100+i), p_on=0.0) for i in range(5)]
    static_scores = [np.mean([run_pass(c, Static(a), rng, np.random.default_rng(7))[0] for c in nominal]) for a in range(len(ARMS))]
    static_arm = int(np.argmax(static_scores))
    agent = DiscountedTS(np.random.default_rng(seed+1))
    curve = []
    for ep in range(n_train + n_eval):
        chan = make_pass(np.random.default_rng(1000+ep))
        seen_rng = np.random.default_rng(5000+ep)
        k_agent, log = run_pass(chan, agent, rng, seen_rng)
        k_static, _ = run_pass(chan, Static(static_arm), rng, np.random.default_rng(5000+ep))
        k_reopt, _ = run_pass(chan, ReOptimizer(), rng, np.random.default_rng(5000+ep))
        k_orac, olog = run_pass(chan, Oracle(chan), rng, np.random.default_rng(5000+ep))
        curve.append(dict(ep=ep, agent=k_agent, static=k_static, reopt=k_reopt, oracle=k_orac,
                          cloud_frac=float(chan["cloud"].mean())))
        if ep % 25 == 0: print(ep, {k: round(v/1e6, 3) for k, v in curve[-1].items() if k in ("agent","static","reopt","oracle")}, flush=True)
    # one evaluation pass, block-by-block, for the adaptation figure
    chan = make_pass(np.random.default_rng(7))
    _, alog = run_pass(chan, agent, rng, np.random.default_rng(77))
    _, slog = run_pass(chan, Static(static_arm), rng, np.random.default_rng(77))
    _, olog = run_pass(chan, Oracle(chan), rng, np.random.default_rng(77))
    json.dump(dict(curve=curve, static_arm=ARMS[static_arm], arms=ARMS,
                   eval_pass=dict(t=TGRID.tolist(), eta=chan["eta"].tolist(), cloud=chan["cloud"].tolist(),
                                  agent=alog, static=slog, oracle=olog)),
              open(f"results/agent_results_{PULSE_RATE:.0e}.json", "w"))
    print("static arm", ARMS[static_arm])

if __name__ == "__main__":
    main()
