"""Passive tier-4 attribution monitor over committed scalar references.

The verdict is an ADAPT operational OR-mapping over TWIN-1's separately
calibrated whiteness and NIS component outcomes.  It is not a TWIN aggregate
statistical verdict and never establishes authenticity or attack presence.
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np

from qkd.twin import LinearGaussianTwin, innovation_diagnostic

from .contracts import AttributionVerdict, DegradationAttributionEvidence
from .references import CommittedReference, parse_canonical_utc, require_nonempty_string
from .traces import ChannelStateTrace

ADAPT_COMPONENT_ALPHA = 0.05
ADAPT_FAMILY_ALPHA_BOUND = min(1.0, 2.0 * ADAPT_COMPONENT_ALPHA)
ADAPT_MONITOR_ID = "qkd.adaptive.monitor"
ADAPT_MONITOR_VERSION = "adaptive-1.0"

SOURCE_INTEGRITY = "not_cryptographically_verified"
SOURCE_INDEPENDENCE = "channel_derived_not_independent"

WHITENESS_PASS = "whiteness_pass"
WHITENESS_REJECT = "whiteness_reject"
NIS_PASS = "nis_pass"
NIS_REJECT_HIGH = "nis_reject_high"
NIS_REJECT_LOW = "nis_reject_low"
WINDOW_BELOW_EFFECTIVE_N = "window_below_effective_n"


class MonitorContractError(ValueError):
    """Raised for monitor-input contract violations that produce no evidence."""


class TraceLengthContractError(MonitorContractError):
    """Raised when a trace exceeds the committed calibration window."""


class AttributionMonitor:
    """Deterministic passive monitor; identity and clock are caller supplied."""

    def evaluate(
        self,
        trace: ChannelStateTrace,
        reference: CommittedReference,
        *,
        evidence_id: str,
        produced_at_utc: str,
    ) -> DegradationAttributionEvidence:
        if not isinstance(trace, ChannelStateTrace):
            raise TypeError("trace must be a ChannelStateTrace.")
        if not isinstance(reference, CommittedReference):
            raise TypeError("reference must be a CommittedReference.")
        try:
            require_nonempty_string(evidence_id, "evidence_id")
            committed_at = parse_canonical_utc(reference.committed_at_utc, "committed_at_utc")
            window_start = parse_canonical_utc(trace.window_start_utc, "window_start_utc")
            window_end = parse_canonical_utc(trace.window_end_utc, "window_end_utc")
            produced_at = parse_canonical_utc(produced_at_utc, "produced_at_utc")
        except ValueError as exc:
            raise MonitorContractError(str(exc)) from exc

        if trace.observable_name != reference.observable_name:
            raise MonitorContractError(
                "trace observable_name must match the committed reference observable_name."
            )
        if committed_at >= window_start:
            raise MonitorContractError(
                "committed_at_utc must strictly precede window_start_utc (commit-then-observe)."
            )
        if produced_at < window_end:
            raise MonitorContractError("produced_at_utc must not precede window_end_utc.")

        effective_n = reference.calibration.effective_n
        if len(trace.values) > effective_n:
            raise TraceLengthContractError(
                f"trace has {len(trace.values)} samples; calibration permits exactly "
                f"effective_n={effective_n} and the monitor never truncates."
            )

        freshness = (
            "fresh"
            if produced_at - window_end
            <= timedelta(seconds=reference.decision_rules.max_freshness_age_s)
            else "stale"
        )
        common = {
            "evidence_id": evidence_id,
            "link_id": trace.link_id,
            "window_start_utc": trace.window_start_utc,
            "window_end_utc": trace.window_end_utc,
            "produced_at_utc": produced_at_utc,
            "monitor_id": ADAPT_MONITOR_ID,
            "monitor_version": ADAPT_MONITOR_VERSION,
            "reference_id": reference.reference_id,
            "reference_digest": reference.digest,
            "source_integrity": SOURCE_INTEGRITY,
            "source_independence": SOURCE_INDEPENDENCE,
            "freshness": freshness,
            "evidence_refs": (trace.trace_id, reference.reference_id),
        }

        if len(trace.values) < effective_n:
            return DegradationAttributionEvidence(
                verdict=AttributionVerdict.INSUFFICIENT_EVIDENCE,
                confidence=0.0,
                reason_codes=(WINDOW_BELOW_EFFECTIVE_N,),
                **common,
            )

        model = reference.model
        twin = LinearGaussianTwin(
            F=np.array([[model.f]], dtype=float),
            H=np.array([[model.h]], dtype=float),
            Q=np.array([[model.q]], dtype=float),
            R=np.array([[model.r]], dtype=float),
        )
        twin_trace = twin.run(
            np.asarray(trace.values, dtype=float).reshape((-1, 1)),
            np.array([model.x0], dtype=float),
            np.array([[model.p0]], dtype=float),
        )
        diagnostic = innovation_diagnostic(twin_trace, reference.calibration.build())

        whiteness_code = WHITENESS_PASS if diagnostic.whiteness_pass else WHITENESS_REJECT
        if diagnostic.nis_pass:
            nis_code = NIS_PASS
        elif diagnostic.nis_statistic > diagnostic.nis_upper_threshold:
            nis_code = NIS_REJECT_HIGH
        else:
            nis_code = NIS_REJECT_LOW
        verdict = (
            AttributionVerdict.ENVIRONMENT_CONSISTENT
            if diagnostic.whiteness_pass and diagnostic.nis_pass
            else AttributionVerdict.UNEXPLAINED
        )
        return DegradationAttributionEvidence(
            verdict=verdict,
            confidence=1.0 - ADAPT_FAMILY_ALPHA_BOUND,
            reason_codes=(whiteness_code, nis_code),
            **common,
        )


__all__ = [
    "ADAPT_COMPONENT_ALPHA",
    "ADAPT_FAMILY_ALPHA_BOUND",
    "ADAPT_MONITOR_ID",
    "ADAPT_MONITOR_VERSION",
    "AttributionMonitor",
    "MonitorContractError",
    "TraceLengthContractError",
]
