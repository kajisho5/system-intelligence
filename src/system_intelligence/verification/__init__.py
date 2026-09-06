"""Verification engine: run tests locally and record the outcome.

Phase 8 scope (R10, docs/design/docs/02-requirements.md): `run_verification`
executes a configured command and produces a `Verification` record from its
actual exit code — never inferred, never assumed passing. Not yet
implemented: re-scanning and diffing before/after snapshots, which needs a
stored before-snapshot to compare against.
"""

from system_intelligence.verification.engine import VerificationError, run_verification

__all__ = ["VerificationError", "run_verification"]
