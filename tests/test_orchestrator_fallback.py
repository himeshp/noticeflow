"""Regression test: run_pipeline must not crash on a KNOWN notice when the
researcher's legal context fails to parse (the fallback LegalContext path).

Guards against the UnboundLocalError introduced by a function-local
`from noticeflow.schemas import LegalContext` shadowing the module-level import.
Pure — all GCP touchpoints are monkeypatched.
"""

from noticeflow.agents import orchestrator as O
from noticeflow.schemas import ClassifiedNotice, NoticeType, ResponsePacket


class _FakeRunner:
    async def run_async(self, **kwargs):  # async generator that yields nothing
        return
        yield  # noqa: unreachable — makes this an async generator


class _FakeSession:
    def __init__(self, state):
        self.state = state


class _FakeSessionService:
    def __init__(self, state):
        self._state = state

    async def create_session(self, **kwargs):
        return _FakeSession(self._state)

    async def get_session(self, **kwargs):
        return _FakeSession(self._state)


async def test_known_notice_with_unparseable_legal_context_does_not_crash(monkeypatch):
    state = {
        O.STATE_CLASSIFIED: {"notice_type": "ITC_MISMATCH"},
        O.STATE_LEGAL: "not-valid-json",
        O.STATE_PACKET: "",  # forces the fallback packet path
    }
    known = ClassifiedNotice(
        notice_type=NoticeType.ITC_MISMATCH,
        governing_sections=["Section 16"],
        issue_summary="ITC excess",
        raw_extracted_text="",
        confidence=1.0,
    )
    monkeypatch.setattr(O, "_get_pipeline", lambda: (None, _FakeRunner()))
    monkeypatch.setattr(O, "_session_service", _FakeSessionService(state))
    monkeypatch.setattr(O, "_parse_classified", lambda raw: known)
    # Force the researcher-parse-miss branch that triggered the bug:
    monkeypatch.setattr(O, "_parse_legal_context", lambda raw, notice: None)

    packet = await O.run_pipeline("some ITC mismatch notice text")

    assert isinstance(packet, ResponsePacket)
    assert packet.notice_type == NoticeType.ITC_MISMATCH
