# Quantum-QKD-Aero: Channel-Dynamics Generator (Spec)

*The non-stationarity generator the experimental ladder rests on. It produces a time-varying transmittance η(t) by composing three physically distinct layers on their own timescales, then aggregates per block into the fading distribution the secure-key module already consumes.*

---

## 0. Composition and timescales

The instantaneous channel transmittance factorizes into a constant term, a deterministic geometric backbone, and two stochastic layers:

$$\eta(t) = \eta_{\text{det}} \cdot \underbrace{\eta_{\text{geo}}(d(t)) \cdot \eta_{\text{atm}}(E(t))}_{\text{Generator A: deterministic}} \cdot \underbrace{\eta_{\text{turb}}(t)}_{\text{Gen B: fast}} \cdot \underbrace{\eta_{\text{cloud}}(C(t))}_{\text{Gen C: medium}}$$

| Layer | Physical origin | Timescale | Generator |
|---|---|---|---|
| $\eta_{\text{det}}$ | receiver optics + detector efficiency | constant | — |
| $\eta_{\text{geo}},\ \eta_{\text{atm}}$ | slant range + air mass over a pass | seconds–minutes (deterministic) | **A** |
| $\eta_{\text{turb}}$ | atmospheric turbulence (scintillation) | ~1–10 ms | **B** |
| $\eta_{\text{cloud}}$ | cloud/obscuration events | ~tens of seconds (discrete) | **C** |

**The timescale separation is the design's backbone.** Turbulence coherence time $\tau_c$ (ms) $\ll$ block duration (e.g. 0.1–1 s) $\ll$ pass duration (minutes). So within one block many turbulence coherence times elapse — the block *sees a fading distribution*, not a single value — while the distribution's parameters drift slowly with elevation, and cloud state switches abruptly between blocks. The agent adapts at block cadence to slowly-moving statistics plus discrete cloud transitions. This multi-rate structure is exactly what makes "value of adaptation" a function of how fast each layer moves.

---

## Generator A — Orbital-pass backbone (deterministic)

The geometric skeleton. A LEO downlink pass, parametrized by maximum elevation, sweeping range and air mass over minutes.

### A.1 Geometry

Constants: Earth radius $R_E = 6371$ km, $GM = 3.986\times10^{14}\ \text{m}^3/\text{s}^2$. Satellite altitude $h$ → orbital radius $r = R_E + h$, mean motion $\omega_{\text{orb}} = \sqrt{GM/r^3}$.

Parametrize the pass by along-track angle from closest approach $\theta(t) = \omega_{\text{orb}}(t - t_{\text{ca}})$ and a minimum geocentric offset $\gamma_0$ (how close the subsatellite track passes to the ground station). The geocentric angle between ground station and subsatellite point follows the spherical-triangle relation

$$\cos\gamma(t) = \cos\gamma_0 \cos\theta(t).$$

$\gamma_0 = 0$ gives an overhead pass ($E_{\max}=90°$); larger $\gamma_0$ gives a grazing pass. Slant range and elevation:

$$d(t) = \sqrt{R_E^2 + r^2 - 2 R_E r \cos\gamma(t)}, \qquad \cos E(t) = \frac{r \sin\gamma(t)}{d(t)}.$$

Pass runs over $t \in [-T_{\text{pass}}/2,\ +T_{\text{pass}}/2]$, with the horizon crossings ($E=0$) bounding $T_{\text{pass}}$. To **set** a target $E_{\max}$, solve at closest approach: $\cos E_{\max} = r\sin\gamma_0 / d_{\min}$ with $d_{\min} = \sqrt{R_E^2 + r^2 - 2R_E r\cos\gamma_0}$ — invert numerically for $\gamma_0$.

### A.2 Geometric (diffraction) loss

Gaussian beam, far field. Divergence $\theta_{\text{div}} = \lambda/(\pi w_0)$; beam radius at range $d$ is $w(d) = \sqrt{w_0^2 + (\theta_{\text{div}} d)^2} \approx \theta_{\text{div}} d$. Fraction captured by receiver aperture radius $a_{\text{rx}}$:

$$\eta_{\text{geo}}(d) = 1 - \exp\!\left(-\frac{2 a_{\text{rx}}^2}{w(d)^2}\right) \xrightarrow{a_{\text{rx}} \ll w}\ \frac{2 a_{\text{rx}}^2}{(\theta_{\text{div}} d)^2} \propto \frac{1}{d^2}.$$

The $1/d^2$ scaling is the dominant range dependence. *(Optional pointing-jitter term: multiply by $\exp(-2\sigma_p^2/w(d)^2 \cdot \ldots)$ or fold its variance into Generator B for v1.)*

### A.3 Atmospheric absorption + turbulence schedule

Beer–Lambert with air mass. Use Kasten–Young to avoid the horizon divergence of plain $\sec z$:

$$\text{AM}(E) = \frac{1}{\sin E + 0.50572\,(E_{\deg} + 6.07995)^{-1.6364}}, \qquad \eta_{\text{atm}}(E) = \exp\!\big(-\tau_0\,\text{AM}(E)\big),$$

where $\tau_0 = -\ln \eta_{\text{atm,zenith}}$ is the zenith optical depth. The same air-mass / slant-path geometry sets the **turbulence strength** passed to Generator B via the elevation-scaled Rytov variance:

$$\sigma_R^2(E) = \sigma_{R,\text{zen}}^2 \cdot (\sin E)^{-11/6}.$$

So low passes are simultaneously lossier (air mass) **and** more volatile (Rytov) — physically correct, and it makes the value-of-adaptation curve steepen at low elevation for free.

**Output of A at each $t$:** $d(t),\ E(t),\ \eta_{\text{geo}}(t),\ \eta_{\text{atm}}(t),\ \sigma_R^2(t)$.

---

## Generator B — Turbulence fading (Ornstein–Uhlenbeck in log-η)

The fast stochastic layer. Weak-turbulence scintillation is approximately log-normal, so model the log-transmittance as a mean-reverting OU process — keeps $\eta_{\text{turb}}>0$ and connects directly to scintillation statistics.

$$\eta_{\text{turb}}(t) = e^{X(t)}, \qquad dX = \tfrac{1}{\tau_c}(m - X)\,dt + \sigma_X\sqrt{\tfrac{2}{\tau_c}}\;dW.$$

**Simulate with the exact OU transition** (no Euler timestep bias):

$$X_{t+\Delta t} = m + (X_t - m)\,e^{-\Delta t/\tau_c} + \sigma_X\sqrt{1 - e^{-2\Delta t/\tau_c}}\;Z, \quad Z \sim \mathcal{N}(0,1).$$

Stationary variance is $\sigma_X^2$ and autocovariance is $\sigma_X^2 e^{-|\Delta t|/\tau_c}$, independent of $\Delta t$.

**Pure-fading normalization.** Set $m = -\sigma_X^2/2$ so that $\mathbb{E}[\eta_{\text{turb}}] = 1$ — turbulence redistributes, it doesn't add net loss (that's already in A).

**Physics linkage.** Scintillation index $\sigma_I^2 = e^{\sigma_X^2} - 1$, so

$$\sigma_X^2 = \ln\!\big(1 + A_{\text{ap}}\,\sigma_R^2(E)\big),$$

where $\sigma_R^2(E)$ comes from Generator A and $A_{\text{ap}} \le 1$ is the **aperture-averaging factor** (a finite receiver averages over speckle and suppresses scintillation). $\tau_c \approx 0.31\, r_0 / v_\perp$ (Fried parameter, transverse wind); a few ms typical, optionally shortened at low elevation.

**Output of B:** $\eta_{\text{turb}}(t)$, with variance and correlation time driven by the elevation schedule from A.

---

## Generator C — Cloud / obscuration events (Markov jump process)

The discrete medium-timescale layer, distinct from smooth fading. A continuous-time Markov (telegraph) process over obscuration states.

**Two-state v1:** $C \in \{\text{clear}, \text{cloud}\}$ with transition rates $\lambda_{\text{c}\to\text{cl}}$ and $\lambda_{\text{cl}\to\text{c}}$ (per second). Mean sojourn in clear $= 1/\lambda_{\text{c}\to\text{cl}}$; stationary cloud fraction $= \lambda_{\text{c}\to\text{cl}} / (\lambda_{\text{c}\to\text{cl}} + \lambda_{\text{cl}\to\text{c}})$. Simulate by drawing exponential dwell times per state.

$$\eta_{\text{cloud}}(C) = \begin{cases} 1 & C = \text{clear} \\ 10^{-A_{\text{cloud}}/10} & C = \text{cloud} \end{cases}$$

with $A_{\text{cloud}}$ the cloud attenuation in dB (thin cirrus ~3–6 dB; optically thick → $\eta_{\text{cloud}} \to 0$, effective outage). Optionally draw $A_{\text{cloud}}$ per event from a distribution, or extend to a three-state {clear, thin, thick} rate matrix $Q$.

**Output of C:** $\eta_{\text{cloud}}(t)$ — abrupt on/off (or multi-level) obscuration. The **cloud-event rate** is a clean volatility knob orthogonal to turbulence.

---

## Putting it together — interface and per-block aggregation

### Interface

A `ChannelDynamics` object composing A/B/C:

```
ch = ChannelDynamics(orbit=..., turbulence=..., clouds=..., optics=...)
eta_t = ch.sample(t)            # instantaneous η at time t (fine resolution)
pdt   = ch.block_pdt(t0, N, dt) # probability distribution of transmittance over a block
```

Two simulation modes, picked by the experiment's budget:

1. **Fine-grained**: step the OU process and cloud chain at $\Delta t \sim \tau_c/10$, evaluate $\eta(t)$ each step, aggregate the block. Faithful but expensive.
2. **PDT summary** (recommended default): hold A and C fixed over the block, represent B by its stationary log-normal $\mathcal{N}(m,\sigma_X^2)$, and feed the resulting **probability distribution of transmittance (PDT)** to the secure-key module. Orders of magnitude cheaper and valid because $\tau_c \ll$ block duration.

### Bridge to the secure-key module (likely already in the platform)

The generator supplies $\eta$; the existing decoy-BB84 estimator turns it into gains and QBER. For completeness, the standard coupling per intensity $x$:

$$Q_x = Y_0 + 1 - e^{-\eta x}, \qquad E_x = \frac{e_0 Y_0 + e_d\,(1 - e^{-\eta x})}{Q_x},$$

with $Y_0$ the background/dark-count yield, $e_0 = 1/2$, $e_d$ the optical misalignment error. Note the behavior the experiments rely on: as $\eta \to$ small, $E_x \to 1/2$ (dark-count-dominated QBER blow-up) — so **QBER rises automatically as the channel fades**, which is what makes QBER an informative (but, in Exp 3, forgeable) observation. Under PDT mode, integrate $Q_x, E_x$ over the transmittance distribution before decoy estimation.

---

## Default parameters (LEO downlink, runnable starting point)

| Parameter | Symbol | Default | Note |
|---|---|---|---|
| Altitude | $h$ | 500 km | LEO |
| Wavelength | $\lambda$ | 785 nm | (1550 nm telecom option) |
| Transmit divergence | $\theta_{\text{div}}$ | 10 µrad | sets beam spread |
| Receiver aperture radius | $a_{\text{rx}}$ | 0.5 m | 1 m telescope |
| Zenith atm. transmittance | $\eta_{\text{atm,zen}}$ | 0.80 | $\tau_0 \approx 0.22$, good site |
| Zenith Rytov variance | $\sigma_{R,\text{zen}}^2$ | 0.10 | weak turbulence |
| Aperture-averaging factor | $A_{\text{ap}}$ | 0.3 | suppresses scintillation |
| Turbulence coherence time | $\tau_c$ | 3 ms | $0.31 r_0/v_\perp$ |
| Detector/optics efficiency | $\eta_{\text{det}}$ | 0.5 | constant |
| Background/dark yield | $Y_0$ | $10^{-6}$ | per pulse |
| Misalignment error | $e_d$ | 0.01–0.03 | optical |
| Clear fraction (stationary) | — | 0.7 | cloud duty cycle |
| Mean clear sojourn | $1/\lambda_{\text{c}\to\text{cl}}$ | 100 s | |
| Mean cloud sojourn | $1/\lambda_{\text{cl}\to\text{c}}$ | 40 s | |
| Cloud attenuation | $A_{\text{cloud}}$ | 6 dB | thin cloud |
| Max elevation (swept) | $E_{\max}$ | 20°–90° | **primary geometry knob** |
| Pass duration | $T_{\text{pass}}$ | ~5–8 min | LEO, from geometry |

---

## Validation before use (verify the instrument, not the simulated data)

Run these checks on the generator in isolation before any experiment depends on it:

1. **Range scaling**: $\eta_{\text{geo}} \propto 1/d^2$ recovered across the pass.
2. **Elevation profile**: $E(t)$ symmetric about closest approach; $E_{\max}$ matches the requested value; horizon crossings bound $T_{\text{pass}}$.
3. **Fading is unbiased**: $\mathbb{E}[\eta_{\text{turb}}] = 1$ to sampling error (confirms the $m = -\sigma_X^2/2$ correction).
4. **OU statistics**: empirical stationary variance $= \sigma_X^2$; autocorrelation decays as $e^{-|\Delta t|/\tau_c}$.
5. **PDT shape**: per-block transmittance is log-normal in the weak-turbulence regime; mean tracks the deterministic backbone.
6. **Cloud duty cycle**: empirical cloud fraction matches $\lambda_{\text{c}\to\text{cl}}/(\lambda_{\text{c}\to\text{cl}}+\lambda_{\text{cl}\to\text{c}})$; dwell times exponential.
7. **QBER response**: $E_x \to 1/2$ as $\eta \to 0$ and $E_x \to e_d$ at high $\eta$.

---

## Volatility knobs → which experiment turns which

| Knob | Effect | Used by |
|---|---|---|
| $E_{\max}$ (pass geometry) | how far the channel sweeps in range/air-mass/Rytov | Exp 1 (value-of-adaptation), Exp 4 (deploy on a new pass) |
| $\sigma_{R,\text{zen}}^2$ | turbulence strength → fading width | Exp 1, Exp 2 |
| $\tau_c$ | how fast fading decorrelates | Exp 1, Exp 2 |
| cloud rates $\lambda$ | discrete-event volatility | Exp 1, Exp 3 (cloud as the "weather" matched to attacks) |
| atmospheric-profile / $\eta_{\text{det}}$ shift | distribution shift between train and deploy | Exp 4 (capture / drift) |

The non-stationarity parameter on the x-axis of the Experiment 1 value-of-adaptation curve is any one of the first three, holding the others fixed.

---

## v1 boundaries and honest caveats

- **Weak-to-moderate turbulence only.** Log-normal (hence OU-in-log) holds for $\sigma_R^2 \lesssim 1$. At very low elevation / strong turbulence, irradiance statistics become **gamma–gamma**; flag this regime and treat gamma–gamma as the v2 extension rather than trusting log-normal there.
- **Plane-parallel atmosphere** with Kasten–Young air mass — accurate to near the horizon but not at $E \to 0$.
- **Circular orbit, single pass** — no $J_2$, drag, or Earth rotation within the pass. Fine for per-pass dynamics; not for multi-day scheduling.
- **Single coherence time** (frozen-flow / Taylor hypothesis). Real turbulence has a spectrum of timescales; one $\tau_c$ is the v1 simplification.
- **Pointing jitter** folded into $\sigma_X^2$ for v1; separate it into a Rayleigh/Beckmann beam-wander term if pointing budgets become a study variable.

These are deliberate v1 choices, not oversights — each is the simplest model that preserves the *behavior* the experiments need (volatility that scales with elevation, abrupt obscuration, QBER that blows up as the channel fades). Replace them only when an experiment's conclusion would actually turn on the difference.
