# Quantum-QKD-Aero: Contact-Window Extension (Spec)

*How the satellite-pass intermittency in the channel-dynamics spec generalizes — through a single abstraction, the **contact window** — to pull deep space, delay-tolerant networking, and quantum repeaters into one framework. This is the proposal-grade architecture: deliberately broader than the built simulation, and explicitly a roadmap on top of the existing spec rather than a replacement for it.*

---

## 0. The one hook: a contact window

A LEO pass is a **finite, predictable window of usable link, bounded by horizon crossings, with time-varying quality inside it.** That is the whole abstraction. Everything in the channel-dynamics spec — Generators A/B/C producing $\eta(t)$ — describes the *inside* of one such window for one ground–satellite link.

The claim from the previous turn was that this one feature reaches deep space, delay-tolerance, and repeaters simultaneously. Here is why, in one sentence each:

- **Deep space** is the same contact window with the range dialed up until *propagation delay* dominates and the atmosphere disappears.
- **Delay-tolerant networking (DTN)** is what you are *forced* into the moment windows are intermittent: store during a gap, forward during a contact.
- **Quantum repeaters** are the spatial generalization — and the entanglement they hold in memory between swaps is the *same store-and-wait problem* as a DTN buffer, with a decoherence clock instead of a bundle lifetime.

So the lift is: generalize "$\eta(t)$ over one pass" to **a time-varying contact topology** in which nodes hold buffers, links open and close as windows, each link carries a propagation delay, and decisions are made under the constraint that you may have to *store and wait* rather than transmit now. The existing channel spec is the intra-window building block, reused unchanged.

---

## 1. The lifting: from `ChannelDynamics` to `ContactTopology`

```
ContactTopology
├── nodes N                       # ground stations, satellites, repeater nodes, probes
├── for each ordered link (i,j):
│     ContactSchedule             # Generator D — list of (t_open, t_close) windows
│       └── per window:
│             ChannelDynamics     # the existing A/B/C spec → η(t) inside the window
│             delay  L(t)=d/c     # Generator E — one-way light time
└── for each node:
      Buffer/Memory               # Generator F — classical key buffer OR quantum memory
```

The existing spec is *not* replaced — it becomes the per-window link model. A window simply reuses Generators A/B/C, or a subset, depending on regime (deep-space and space-to-space hops drop the atmospheric layers B and C entirely).

---

## 2. One abstraction, three regimes

Dialing the contact-window parameters reproduces all three frontiers from the same machinery:

| Quantity | LEO downlink (current spec) | Deep-space link | Repeater segment |
|---|---|---|---|
| Range $d$ | 500–2000 km | 0.1–50+ AU | tens–hundreds km / hop |
| One-way delay $L=d/c$ | 2–7 ms (**negligible**) | minutes–hours (**dominant**) | µs–ms |
| Turbulence (Gen B) | full | none | only ground-traversing hops |
| Cloud (Gen C) | full | none | only ground-traversing hops |
| Loss mechanism (Gen A) | diffraction + air mass | diffraction only ($d^2$ enormous) | per-segment; PLOB sets why segmenting helps |
| Window gating (Gen D) | horizon + weather | antenna schedule + solar conjunction/occultation | memory coherence + swap timing |
| What's stored in a gap (Gen F) | classical key (bundles) | classical key | **quantum state** (decoherence clock) |
| Real-time closed loop? | **yes** ($L \ll$ block) | **no** ($L \gg$ control interval) | partial (within memory budget) |

The through-line in the bottom three rows: a contact window is a bounded opportunity, the gap forces storage, and the only thing that changes across frontiers is *what* you store and *how it decays*.

---

## 3. New generator layers

### Generator D — Contact schedule

Generalizes the horizon-bounded LEO pass to a schedule of windows per link.

- **LEO:** derive directly from Generator A — a window is $\{t : E(t) > E_{\min}\}$. Already in hand.
- **Deep space:** periodic antenna availability (DSN-style scheduling) intersected with **occultation/conjunction blackouts** (line-of-sight blocked by the Sun or a planet). Windows are long but sparse, and gaps can be days.
- **Repeater chain:** per-segment availability — always-on for fixed fibre, windowed for any satellite hop.

Output per link: an ordered list of $(t_{\text{open}}, t_{\text{close}})$ windows, each carrying a `ChannelDynamics`.

### Generator E — Propagation delay

$$L(t) = d(t)/c.$$

Tracked-but-negligible for LEO. For deep space it is the **dominant state variable** and it drifts as bodies move (range-rate → Doppler, the deep-space analogue of the LEO elevation schedule). 1 AU $\approx$ 8.3 light-minutes; a Mars link is 4–24 minutes one-way.

**The consequence worth its own experiment:** any feedback-based adaptation — the entire premise of the RL agent in Experiments 1–5 — observes state that is $L$ old and acts $L$ into the future. When $L \gg$ the control interval, *reactive* adaptation is impossible; the agent must **predict and pre-commit a parameter schedule for the whole window** (open-loop within a contact). Light-time converts the control problem from feedback to forecasting.

### Generator F — Buffer / memory dynamics

Two flavors, and keeping them distinct is essential (see §5):

- **Classical buffer (DTN):** a key store per node, filled during contacts, drained by demand or forwarding, with finite capacity and an optional bundle lifetime (TTL). Pure store-carry-forward.
- **Quantum memory (repeater):** stored entanglement carries a **decoherence clock**. A simple v1 model for fidelity to the target Bell state:
$$F(t) = \tfrac{1}{2} + \big(F_0 - \tfrac{1}{2}\big)\,e^{-t/T_{\text{mem}}},$$
decaying toward the floor where the pair stops being distillable (Werner threshold $F > \tfrac{1}{2}$). $T_{\text{mem}}$ is the memory coherence time; swap success probability and purification cost (pairs consumed per fidelity gain) sit alongside it.

---

## 4. Why repeaters are not optional at these distances (the baseline)

The repeaterless secret-key capacity of a lossy channel is bounded (PLOB):

$$K \le -\log_2(1-\eta).$$

Since $\eta$ falls **exponentially** with distance in fibre ($\eta = 10^{-\alpha d/10}$) and as $1/d^2$ in free space, the achievable repeaterless rate collapses over long links. Segmenting the path with repeaters — entanglement generation per segment, **swapping** at nodes, **purification** to fight accumulated noise, and **memory** to hold a segment's entanglement while a neighbor catches up — is the only way to beat it. This bound is the baseline every repeater experiment reports against: it tells you *how much* the repeater architecture bought.

---

## 5. The conceptual payoff: store-and-hold is one problem in two media

The clean idea this whole extension is built to expose:

> **A DTN bundle lifetime and a quantum memory coherence time are the same constraint in different media.**

Both ask: *I have something useful now but can't deliver it until the next contact — will it survive the wait?* For DTN it's buffer capacity and TTL; for repeaters it's $T_{\text{mem}}$ and fidelity decay; for deep space the "wait" is light-time itself. So a **single scheduling/routing policy** — when to hold, when to forward, when to swap, when to purify, when to discard and regenerate — governs all three, parameterized only by what is stored and how it decays.

This is exactly where the learned-policy story extends. The agent's action space grows from "tune link parameters" (Exp 1–5) to "given the contact schedule, predicted window qualities, and buffer/memory state, decide store / forward / swap / purify / commit." Experiments 6 (routing) and 7 (repeaters) unify under it, and a deep-space/DTN variant falls out for free.

---

## 6. New experiments this unlocks (extending the ladder)

**Experiment 6′ — Contact-aware scheduling under intermittency (DTN layer).** One node, intermittent contacts (LEO-like or deep-space-like), classical key buffer with finite capacity and TTL. Policy: when to transmit / accumulate / hold given predicted next-window quality and buffer state. Metric: delivered secure key vs. buffer overflow and expiry, as a function of contact duty cycle and delay. *This is Experiment 5 (commit timing) lifted to span gaps rather than to act within a block.*

**Experiment 7′ — Repeater segment with memory decoherence (quantum store-and-hold).** Two segments, a midpoint repeater with finite-$T_{\text{mem}}$ memory. Policy: when to attempt a swap vs. wait for a fresher pair; when to purify (spending pairs) vs. accept lower fidelity — given that stored entanglement decays on its clock. Metric: end-to-end secure key / fidelity vs. $T_{\text{mem}}$ and segment contact timing; PLOB as the must-beat baseline.

**Experiment 8 — Deep-space open-loop adaptation (the light-time experiment).** Same single-link physics as Experiment 1, but with $L \gg$ control interval, forcing predict-and-pre-commit instead of react. Metric: how the value-of-adaptation from Exp 1 degrades as delay grows, and how much a *predictive* policy recovers versus a reactive one that is always $L$-stale. A clean, novel measurement of what light-time costs adaptive QKD.

---

## 7. Honest boundaries (so the scope doesn't overreach)

- **"Quantum DTN" is a trap phrase — be precise.** You cannot park a flying photon in a classical buffer. The DTN layer over *classical key derived from quantum links* is solid and near-term. "DTN for qubits" only means *entanglement held in repeater memory*, which is the Generator-F quantum branch, not a classical bundle store. Conflating the two would be a real error; the spec keeps them on separate tracks for this reason.
- **Deep-space *quantum* links at AU scale are far beyond current capability** — the loss is astronomical and no memory holds that long. The realistic framings are (a) classical-key DTN over deep-space *optical* links, and (b) entanglement distribution only via repeater-segmented architectures. The "deep-space quantum network" is a long-horizon research framing, and the modeling here is exploratory architecture, not near-term engineering.
- **This is roadmap, not built simulation.** Consistent with the vision-versus-concrete split that's run through this work: §6's experiments are the declared expansion path. The currently specced and runnable system is still the LEO optical link of the channel-dynamics spec plus Experiments 1–5. Build the contact-window layer only when an experiment past Exp 5 actually needs it.

For a proposal, the strength of this section is precisely that the contact window is *one* hook that visibly reaches all three frontiers at once — which is the through-line a reviewer can follow. For the simulation, treat it as the order in which scope is allowed to grow.
