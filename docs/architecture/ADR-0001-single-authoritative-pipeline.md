# ADR-0001: Single Authoritative Pipeline

## Context

The repository had two producers for the same production artifact,
`outputs/results.json`. The active computed pipeline, `src/qkd/run.py`, wrote the
artifact from the Phase 2B satellite-pass/channel/teleportation path. The root
`qkd_model.py` script was the original decorative prototype: it drove
`TeleportationMission`, `build_teleportation_results`, and `fidelity_noise`,
then wrote the same `outputs/results.json` path.

That meant the dashboard showed whichever producer ran last. The decorative
quantities were gone from `run.py`, but still live in the second execution path.
This was an execution-graph defect, not a physics-level defect, so it could be
missed while reviewing only the computed physics.

## Decision

Establish the §4.0 single-authoritative-pipeline invariant: exactly one
authoritative production pipeline may write each generated artifact. Historical
or experimental pipelines must write to separate, clearly labelled outputs and
must never overwrite a production artifact.

For `outputs/results.json`, `src/qkd/run.py` is the sole production writer. The
legacy `qkd_model.py` path is retired. The code is deleted, not archived: its
only value is historical, it has no unique non-decorative capability, it is not
a regression reference, and a faithful archive would leave self-contained
decorative code on disk. Git history plus this ADR preserve the reasoning and
provenance without weakening the invariant.

## Provenance

The retired symbols were introduced in the initial commit, `2924673`
(`2026-04-06`, "Initial commit: structured QKD simulation with teleportation and
BB84 modules"). They predate the Phase 2B refactor and are retired in PR0 /
Phase 2B-6a.

## Consequences

`src/qkd/run.py` becomes the only production writer of `outputs/results.json`.
The stale root `results.json` artifact is removed; the active production
artifact under `outputs/results.json` is not removed.

The misleading `remaining_entangled_resource_kb` key loses its legacy emitter,
so it can be dropped cleanly in PR1 when the honest pass composition replaces
the remaining display placeholder. Future structural decisions should follow
this ADR convention: document the decision and provenance, and avoid preserving
obsolete executable paths that can compete with authoritative artifacts.
