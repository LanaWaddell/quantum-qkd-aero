"""Synthetic, non-physical stress fixtures for the LINK effect stack.

Everything in this subpackage is a **fixture**, not a physics model. Modules
here emit ``qkd.link`` observables through the ordinary
:class:`~qkd.link.ChannelEffect` contract so they compose with the real
stack, but none of them claims a propagation mechanism. They exist to
stress estimator and monitor assumptions with structured inputs that the
physical effect library does not produce.

Binding conventions for this subpackage:

* Every ``effect_id`` here carries the ``fixture_`` prefix.
* No fixture ``effect_id`` may be added to
  ``qkd.detection.PDT_ADMISSIBLE_EFFECTS``. (PDT in this repository is the
  per-block probability-distribution-of-transmittance mode, ADR-0003 section 4;
  its ``deterministic`` admission class asserts the effect is resolved by --
  effectively constant within -- each evaluation block. That is a bandwidth
  claim relative to the evaluation grid, and a fixture chosen for its
  spectral structure is exactly the case the claim fails for.)
* Fixtures are never members of the production stack.
"""
