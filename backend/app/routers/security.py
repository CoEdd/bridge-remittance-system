import json
from collections.abc import Iterator

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import iterate_in_threadpool

from app import redteam
from app.config import get_settings
from app.policy.describe import describe_limits, describe_safeguards, describe_tiers
from app.claims.evaluation import load_results
from app.redteam.cases import CASES
from app.rules.core_rules import CORE_RULES
from app.routers.deps import UserDep
from app.schemas import ClaimCheckOverviewOut, RedTeamCaseOut, RuleOut, SecurityPolicyOut

router = APIRouter(prefix="/security", tags=["security"])


@router.get("/policy")
def security_policy(user: UserDep) -> SecurityPolicyOut:
    """The permission tiers, the student's limits and the safeguards, as the policy engine has them."""
    return SecurityPolicyOut(
        tiers=describe_tiers(),
        currency=user.home_currency,
        limits=describe_limits(user, get_settings().cooling_off_seconds),
        safeguards=describe_safeguards(),
    )


@router.get("/claim-check")
def claim_check_overview() -> ClaimCheckOverviewOut:
    """The claim check in brief: its eight rules and, when it has been run, its measured results."""
    return ClaimCheckOverviewOut(
        rules=[
            RuleOut(id=rule.id, severity=rule.severity, raises=rule.raises, title=rule.title, text=rule.text)
            for rule in CORE_RULES
        ],
        evaluation=load_results(),
    )


@router.get("/redteam")
def list_red_team_cases() -> list[RedTeamCaseOut]:
    """The red-team cases, before they are run."""
    return [RedTeamCaseOut(id=case.id, title=case.title, attack=case.attack, expected=case.expected) for case in CASES]


@router.post("/redteam/run")
def run_red_team() -> EventSourceResponse:
    """
    Run every case and stream the results as Server-Sent Events: "case" when one starts
    (status running), "case" again with its result (passed or failed), then "done".
    Each case runs on its own isolated copy of the database; the demo data is not touched.
    """

    def events() -> Iterator[dict[str, str]]:
        for name, payload in redteam.run_all():
            yield {"event": name, "data": json.dumps(payload, ensure_ascii=False, default=str)}

    return EventSourceResponse(iterate_in_threadpool(events()))
