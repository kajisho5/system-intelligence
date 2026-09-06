from system_intelligence.core.verification import Verification


def test_verification_verified_at_is_timezone_aware() -> None:
    verification = Verification()
    assert verification.verified_at.tzinfo is not None
