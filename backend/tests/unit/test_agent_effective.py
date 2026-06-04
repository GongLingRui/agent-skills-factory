"""Release strategy helpers."""

from agent_factory.core.user_context import UserContext
from agent_factory.services.agent_effective import _user_in_canary_cohort


def _ctx(*, dept=None, uid="u1"):
    return UserContext(
        session_id="s",
        user_id_hash=uid,
        department=dept,
        permissions=(),
    )


def test_canary_department_match():
    rc = {
        "strategy": "canary",
        "canary": {"target_departments": ["legal"], "percent": 0},
    }
    assert _user_in_canary_cohort(_ctx(dept="legal"), rc) is True


def test_canary_user_whitelist():
    rc = {
        "strategy": "canary",
        "canary": {"target_users": ["hash-a"], "percent": 0},
    }
    assert _user_in_canary_cohort(_ctx(uid="hash-a"), rc) is True


def test_canary_percent_bucket_stable():
    rc = {"strategy": "canary", "canary": {"percent": 50}}
    u = _ctx(uid="stable-user-id")
    a = _user_in_canary_cohort(u, rc)
    b = _user_in_canary_cohort(u, rc)
    assert a == b
