"""Tier-4 adaptive-coupling package (ADR-0004 D1).

Owns every feedback path in which channel-state observables drive protocol or
policy adaptation. HYBRID-1 creates :mod:`qkd.adaptive.contracts` as the first
consumer to land; see that module's docstring for the ownership rule.
"""

from __future__ import annotations
