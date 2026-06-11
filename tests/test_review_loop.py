"""Integration test for the Drafter<->Critic LoopAgent self-correction — GCP-free.

A stub drafter emits a BAD annexure on the first pass and a CORRECT one once it
sees the Critic's feedback in state. Proves the real CriticAgent + ADK LoopAgent:
feedback flows back, the loop iterates, and it escalates (stops) on APPROVE.
"""

import json
import uuid

from google.adk.agents import BaseAgent, LoopAgent
from google.adk.events import Event, EventActions
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from noticeflow.agents.reviewer import CriticAgent

STATE_PACKET = "response_packet_json"
STATE_LEGAL = "legal_context_json"

_GOOD = {"cited_source_ids": ["CGST Act 2017, Section 73"],
         "annexure": {"gstr3b_itc_claimed": 905000.0, "gstr2b_itc_available": 820000.0,
                      "itc_mismatch_amount": 85000.0}}
_BAD = {"cited_source_ids": ["CGST Act 2017, Section 73"],
        "annexure": {"gstr3b_itc_claimed": 905000.0, "gstr2b_itc_available": 820000.0,
                     "itc_mismatch_amount": 99999.0}}  # mismatch != claimed - available


class _StubDrafter(BaseAgent):
    """Emits a bad draft first; once Critic feedback is present, emits a good one."""
    async def _run_async_impl(self, ctx):
        had_feedback = bool(ctx.session.state.get("review_issues", "").strip())
        packet = _GOOD if had_feedback else _BAD
        yield Event(author=self.name,
                    actions=EventActions(state_delta={STATE_PACKET: json.dumps(packet)}))


async def test_loop_self_corrects_then_approves():
    loop = LoopAgent(name="draft_review",
                     sub_agents=[_StubDrafter(name="drafter"), CriticAgent(name="critic")],
                     max_iterations=2)
    svc = InMemorySessionService()
    sid = str(uuid.uuid4())
    await svc.create_session(app_name="t", user_id="u", session_id=sid,
                             state={STATE_LEGAL: json.dumps({"citations": [{"source_id": "CGST Act 2017, Section 73"}]}),
                                    "review_issues": "", "review_round": 0})
    runner = Runner(agent=loop, app_name="t", session_service=svc)
    async for _ in runner.run_async(
        user_id="u", session_id=sid,
        new_message=types.Content(role="user", parts=[types.Part(text="go")]),
    ):
        pass

    s = (await svc.get_session(app_name="t", user_id="u", session_id=sid)).state
    # Critic ran twice: REVISE (round 1) then APPROVE (round 2)
    assert s["review_round"] == 2
    review = json.loads(s["review_result_json"])
    assert review["verdict"] == "APPROVE" and review["round"] == 2
    # The drafter self-corrected: final packet has the reconciling figures
    final = json.loads(s[STATE_PACKET])
    assert final["annexure"]["itc_mismatch_amount"] == 85000.0


async def test_loop_escalates_first_round_when_already_good():
    loop = LoopAgent(name="draft_review",
                     sub_agents=[_AlwaysGoodDrafter(name="drafter"), CriticAgent(name="critic")],
                     max_iterations=2)
    svc = InMemorySessionService()
    sid = str(uuid.uuid4())
    await svc.create_session(app_name="t", user_id="u", session_id=sid,
                             state={STATE_LEGAL: json.dumps({"citations": [{"source_id": "CGST Act 2017, Section 73"}]}),
                                    "review_issues": "", "review_round": 0})
    runner = Runner(agent=loop, app_name="t", session_service=svc)
    async for _ in runner.run_async(
        user_id="u", session_id=sid,
        new_message=types.Content(role="user", parts=[types.Part(text="go")]),
    ):
        pass
    s = (await svc.get_session(app_name="t", user_id="u", session_id=sid)).state
    assert s["review_round"] == 1  # approved first pass, no second iteration
    assert json.loads(s["review_result_json"])["verdict"] == "APPROVE"


class _AlwaysGoodDrafter(BaseAgent):
    async def _run_async_impl(self, ctx):
        yield Event(author=self.name,
                    actions=EventActions(state_delta={STATE_PACKET: json.dumps(_GOOD)}))
