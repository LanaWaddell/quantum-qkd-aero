# BENCH-mem0-gundogan — MEM-0 Reconstruction Benchmark

**Status: STOP retained — 2-QM cutoff behaviour reproduced under a source-backed assumption; block-count magnitudes low by ≈3.5× in both schemes; 1-QM comparison UNREPRODUCED. Not certified; not a passed benchmark.**
**Date:** 2026-08-26 (rev. 3, plan v1.3 + authorized Fig. 3 digitization) · **Implementer:** Sonnet subagent · **Review chain:** Echo v1 → v1.1 delta → post-implementation discrepancy adjudication

> This artifact independently reconstructs the published Gündoğan et al. finite-key calculation under explicitly stated assumptions. It evaluates agreement with reported benchmark behavior and does not validate the physical model, hardware feasibility, or Quantum-QKD-Aero performance.

## Baseline
Gündoğan, Sidhu, Krutzik, Oi, *Time-delayed single satellite quantum repeater node for global quantum communications*, **Optica Quantum 2(3), 140–147 (2024), DOI 10.1364/OPTICAQ.517495** (published article; arXiv:2303.04174v2 cross-check).

## Resolution hierarchy (Echo §8; Luong and Wittig are NOT interchangeable)
```
E1 / 2-QM error-correction parameter : Luong et al. 2016 [Ref. 28]  -> source-backed inherited assumption
1-QM block-count discrepancy         : Wittig et al. 2017 [Ref. 26] -> primary lineage source (supplies no repair factor)
                                       Fig. 3(a,b) digitization     -> DONE; see "Digitization" below
                                       author data/code             -> query drafted, PI approval pending
```

## Reconstruction assumptions
- **E1 (primary, v1.3): f_e = 1.16** — from Luong, Jiang, Kim, Lütkenhaus, Appl. Phys. B 122, 96 (2016) §6: "f (error correction inefficiency) = 1.16". Verified against the primary source (arXiv:1508.02811). Gündoğan cites Luong as Ref. 28 and imports its QBER expressions. **Corroboration:** Luong's Eq. (17) with e_mA = e_mB = 0.01 gives ε_m = 1.98%, matching Gündoğan's Table-1 ε_m = 2% — numerical parameter inheritance, not merely formalism inheritance. (λ_BSM differs, 0.97 vs 0.98, so the inheritance is close but not wholesale.) **Inherited assumption, not a recovered Gündoğan parameter**; adopted on source rationale, not on anchor fit.
- **E2: log₂** throughout.
- Count model, arm efficiencies, QBERs, R definition: plan v1.3 §3.4–§3.6.

## Results — 2-QM lane (f_e = 1.16)

| ID | Target | Tol | Result | Verdict |
|----|--------|-----|--------|---------|
| A1 | 42.0 dB | ±0.5 | **41.64 dB** | **PASS** |
| A2 | 37.5 dB | ±0.25 | **37.41 dB** | **PASS** |
| A5 (L @30 dB, e_m=5%) | >10⁴ | exact | **1.49×10⁴** | **PASS** |
| A6 γ_2QM (20–24 dB) | [0.8,1.2] | band | **1.084** | **PASS** |
| A8 (asymptotic gap) | <1% | — | **3.0×10⁻⁴** | **PASS** |
| A7a (p_d ordering @25.9 dB) | 2QM > 1QM | strict | 2.51e-5 > 5.41e-7 | PASS |

The full 2-QM binding family reproduces within predeclared tolerances under the source-backed assumption. Sensitivity sweep (A1/A2/A5 across f_e ∈ {1.0, 1.1, 1.16, 1.19, 1.22}): 42.41/38.73/2.38e4 · 41.92/37.91/1.82e4 · **41.64/37.41/1.49e4** · 41.50/37.15/1.32e4 · 41.36/36.89/1.16e4. Only f_e ∈ ≈[1.10, 1.19] satisfies A1 and A2 jointly.

## Results — 1-QM lane: OPEN (A3, A4, A6-1QM, A9, A10)

**1-QM factor ledger** (every multiplier from a counting convention; f_e = 1.16 throughout; targets A3 = 28.0 ±0.5, A4 = 25.9 ±0.2):

| Variant | Counting rationale | ×(n_Z+n_X) | A3 | A4 | γ_1QM (20–24) | Source contradiction |
|---|---|---|---|---|---|---|
| **V0 baseline** | plan §3.6; matches Wittig structure | 1.000 | 25.55 | 23.30 | 3.15 | **none** |
| V5 | η_det applied once, not per arm | 1.250 | 26.03 | 23.81 | 2.89 | no explicit support |
| V1 | η_det excluded from counts, kept in QBER | 1.562 | 26.51 | 24.32 | 2.71 | strains App. A η definition |
| V2 | η_mem excluded from counts, kept in QBER | 1.667 | 26.65 | 24.47 | 2.67 | contradicts retrieval gating the count |
| V4 | raw coincidences, no basis sift | 2.000 | 27.04 | 24.88 | 2.57 | **contradicts Eq. (1)** ("matching and coincident") |
| V6 | V5 + no basis sift | 2.500 | 27.51 | 25.40 | 2.48 | inherits V4 contradiction |
| V3 | V1 + V2 (both device factors QBER-only) | 2.604 | **27.60 ✓** | 25.50 ✗ | 2.46 | strains App. A twice |
| V2+V4 | η_mem QBER-only + raw pairs | 3.333 | **28.13 ✓** | **26.07 ✓** | 2.39 | **both components contradict source text** |

**Reading of the ledger — the decisive point.** The only variant that satisfies both A3 and A4 (V2+V4) is also the one whose two components each contradict explicit source text: Eq. (1) defines n_Z, n_X as matching coincident events (so the basis sift is textual), and memory retrieval physically gates the 1-QM count (so η_mem belongs in it). **No source-defensible variant closes A3 and A4 together.** Per the test-not-select rule, **no variant is adopted**; V0 remains the implemented model. This outcome is positive evidence for Echo's class-D hypothesis: an undocumented convention in the published 1-QM calculation itself.

**γ_1QM is not an independent failure.** In the deeper 14–18 dB window, away from the cutoff cliff, every variant sits inside the structural band: V0 = 2.145, V4 = 2.099, V3 = 2.086, V2+V4 = 2.076. The η_ch² scaling is reproduced correctly; the 20–24 dB miss is cliff proximity, derivative of the displaced cutoff.

## Discrepancy ledger

| # | Item | Status |
|---|------|--------|
| L1 | f_e | **Resolved to source-backed inherited assumption f_e = 1.16** (Luong §6, verified; ε_m corroboration). Not a recovered Gündoğan parameter. Sweep retained. |
| L2 | 1-QM count mapping | **OPEN — principal item.** Factor ledger above; no source-defensible variant reconciles A3 and A4. Wittig supplies no repair factor. |
| L3 | 1-QM arm placement | Asymmetric reading, Echo-confirmed from protocol; ≤~1.1 dB; not the cause |
| L4 | Eq. (A5) as printed | Reproduced verbatim; pinned by test |
| L5 | R normalization | **Demoted (Echo §6) and analytically closed:** a scheme-independent renormalization cancels in the crossover; only a scheme-dependent "received pair" definition could move A4, and no source evidence supports one |
| L6 | Log bases | log₂ predeclared; sweep showed no resolution of the 1-QM gap |
| L7 | A6-1QM | **Reclassified (Echo answer 2): structurally passed / dependent on unresolved 1-QM normalization.** γ ≈ 2.08–2.15 across all variants at 14–18 dB confirms η_ch² scaling; the 20–24 dB miss is cliff proximity. No longer a standalone open discrepancy. |
| L8 | ×3 diagnostic | **Rejected as a correction** (Echo §4.2); now also refuted empirically by D3 — the 1-QM mismatch is a shape mismatch, which no constant multiplier can repair |
| L9 | Eq. (A5) reading | **New (D1).** Two available readings of the printed expression; the literal one is implemented. Which was intended is an open question to the authors, not an asserted defect. Count-independent, and independent of L2. |
| L10 | Block-count magnitude | **New (D2).** ×3.45 gap between reconstruction and source in both schemes; the two source routes agree with each other. Attributable to the unprinted source-to-(n_Z,n_X) path, i.e. a limit of this reconstruction. Qualifies the 2-QM endpoint. |

## Digitization of published Fig. 3(a,b) — authorized, performed 2026-08-26
Panels extracted from the published PDF (not redrawn). Precision ±~15% on L, ±0.02 on R, ±0.3 dB on endpoints.

**D1 — Eq. (A5): a reading question, not a finding about the paper (count-independent).** Asymptotic curves isolate the QBER model from block counts. 2-QM asymptotic cutoff: published figure ~40.2 dB, reconstruction 39.83 dB ✓. Asymptotic R levels agree (1-QM 0.418 vs ~0.43; 2-QM 0.166 vs ~0.20). The 1-QM asymptotic cutoff is the exception: reading Eq. (A5) literally, without a ½[1−α_Aα_B] term, this reconstruction obtains **49.13 dB** against a digitized ~43 dB; reading it as structurally parallel to Eqs. (A3) and (A6) obtains **43.89 dB**.

**This artifact does not conclude that Eq. (A5) is in error.** Two readings of a compact printed expression are available; the second happens to align with the published figure in this reconstruction. Which reading the authors intended is a question only they can answer, and it has been put to them (author query, item 4). Until then, **the literal printed form is what this reconstruction implements** (ledger L4), and the discrepancy is recorded as an open reading question against *this reconstruction*, not as a defect in the source. Note also that the alternative reading does **not** fix A3/A4 (25.46 / 23.07), so it is independent of the count-convention question.

**D2 — block-count gap between this reconstruction and the source, both schemes.** Fig. 3(b) L ÷ Fig. 3(a) R at 30 dB (2-QM) implies n_Z+n_X ≈ 5.5×10⁵; independently, §4's N_QM1 ≈ 2×10⁶ with N = 4(n_Z+n_X) gives 5.0×10⁵. The two source routes are mutually consistent. This reconstruction obtains 1.45×10⁵ → **a ×3.45 gap between the reconstruction and the published values**. The paper is internally consistent here; it is the reconstruction that does not reach it, because the source-to-(n_Z,n_X) path is not printed and had to be inferred. L2 is upgraded from "tension" to a quantified deficit confirmed by two independent source routes. Digitized 2-QM L is low by 2.3× at 20 dB rising to 13× at 35 dB — the passing cutoff anchors are insensitive to a constant block factor; the magnitudes are not.

**D3 — the 1-QM mismatch is shape, not scale.** Reconstruction 1-QM L is *above* the paper at 20 dB (6.7e3 vs ~3e3), equal at 24 dB (3.4e2 vs ~4e2), and dead by 25.6 dB while the paper survives to 27.9 dB; R at 25 dB is 0.024 vs ~0.19. The curve is too steep, so no constant multiplier can fix it — independent empirical confirmation of Echo's rejection of ×3.

**V7 (new ledger variant, rejected):** "ground-detected photons never traverse a memory" (each station detects the direct photon; η_mem gates retrieval) recovers ×1.67 of the missing ×3.45 but pushes A2 to 37.96, outside ±0.25. Not adopted; no source authorizes the residual ×2.

## Current stated result (Echo §9 endpoint, qualified by digitization)
> 2-QM cutoff and threshold behaviour is reproduced within predeclared tolerances under a source-backed inherited f_e = 1.16; absolute key-length magnitudes and block counts remain low by ≈3.5× in both schemes; the 1-QM comparison remains unreproduced because the published count convention is under-specified.

This is an unresolved **literature-reconstruction boundary, not a failed implementation**. MEM-0 does not have to manufacture agreement to succeed.

## Leading explanation (Echo answer 1)
> The factor-ledger search found no source-defensible counting convention that reproduces both A3 and A4. The only variant that does so contradicts explicit source text. This supports an undocumented implementation/counting convention in the published 1-QM calculation as the **leading explanation supported by current evidence** — not an established fact.

"Undocumented" here means *not printed in the article*, which is ordinary for a compact letter-format paper: authors routinely omit the full source-to-block-count path. It is a statement about what a reader can reconstruct from the text, not about the correctness of the authors' own calculation, which this artifact is not in a position to assess and does not assess.

## Standing of this artifact toward the source
This is a **reconstruction report**. Where reconstruction and publication disagree, the artifact records the disagreement and the reconstruction's own assumptions; it does not assign fault. The published article is a peer-reviewed primary source, and every quantity this reconstruction *could* check against it without inferring an unprinted convention — asymptotic rate levels, the 2-QM asymptotic cutoff, the 2-QM finite cutoffs under an inherited f_e, the η_ch and η_ch² scaling exponents — agrees. The open items concentrate precisely where the article does not print the calculation path, which is a normal feature of the format and not a criticism.

## Pending
- **Author query** — sent 2026-08-27, 08:50 MST, by the PI: five items (f_e; 1-QM n_Z,n_X construction; R denominator; Eq. (A5) reading; data/code). Any reply will be incorporated as a dated Correction Log entry and an artifact revision.
