"""Basic checks of the rules we agreed on. Run from backend/: python -m pytest"""
import os

os.environ["NOW"] = "2026-10-11T09:00:00Z"

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.seed import build_service
from app.scheduling import find_slot


@pytest.fixture(autouse=True)
def _single_call_unless_asked(monkeypatch):
    """Tests never reach Google. AI tests fake the single Gemini call; the ADK tests switch the agent back on."""
    from app.settings import settings as S
    monkeypatch.setattr(S.ai, "engine", "genai")
    monkeypatch.setattr(S.ai, "background", False)   # wait for the (fake) AI, so each test sees the final answer


@pytest.fixture()
def svc():
    return build_service()


@pytest.fixture()
def client(svc):
    return TestClient(create_app(svc))


def H(person):
    return {"X-Person-Id": person}


def test_priya_items_are_grouped_and_sorted(client):
    data = client.get("/items", params={"mode": "attendee"}, headers=H("p_priya")).json()
    titles_needs = [i["event"]["title"] for i in data["needsAction"]]
    assert titles_needs[0] == "Sprint Planning"           # earliest first
    assert "Q4 Budget Review" in titles_needs
    assert len(data["noActionNeeded"]["teamCheckins"]) == 3     # three stand-ups, auto-handled
    assert len(data["noActionNeeded"]["orgEvents"]) == 1     # the tech talk
    assert all(i["status"] == "auto_handled" for i in data["noActionNeeded"]["teamCheckins"])


def test_proxy_suggested_from_summaries_and_notes_respect_sharing(svc):
    items = {i.event.title: i for i in svc.store.items() if i.absentPersonId == "p_priya"}
    budget = items["Q4 Budget Review"]
    assert budget.ai.recommendation.value == "proxy" and budget.ai.suggestedProxyId == "p_meena"
    assert budget.ai.confidence.value == "high"
    # Design Review notes are NOT shared with Priya -> falls back to hierarchy with low confidence
    design = items["Design Review"]
    assert design.ai.summariesAvailable is False and design.ai.confidence.value == "low"
    # Vendor decision has no summaries at all
    assert items["Vendor Contract Decision"].ai.suggestedProxyId == "p_arjun"


def test_proxy_must_be_a_valid_person_and_accept_flow(client, svc):
    item = next(i for i in svc.store.items() if i.event.title == "Q4 Budget Review")
    for bad_id in ("p_events", "p_priya", "p_nobody"):   # a group, the absent person, someone not in the directory
        bad = client.post(f"/items/{item.id}/action", json={"action": "proxy", "proxyId": bad_id}, headers=H("p_priya"))
        assert bad.status_code == 400
    ok = client.post(f"/items/{item.id}/action", json={"action": "proxy", "proxyId": "p_meena"}, headers=H("p_priya"))
    assert ok.status_code == 200 and ok.json()["status"] == "proxy_requested"
    reqs = client.get("/proxy-requests", headers=H("p_meena")).json()
    assert len(reqs) == 1 and reqs[0]["notesAvailable"] is True
    done = client.post(f"/proxy-requests/{reqs[0]['request']['id']}/respond", json={"response": "accepted"}, headers=H("p_meena"))
    assert done.status_code == 200
    assert client.get("/items", params={"mode": "attendee"}, headers=H("p_priya")).json()["needsAction"]


def test_declined_proxy_notifies_owner_and_organizer(client, svc):
    from app import notify
    item = next(i for i in svc.store.items() if i.event.title == "Q4 Budget Review")
    client.post(f"/items/{item.id}/action", json={"action": "proxy", "proxyId": "p_meena"}, headers=H("p_priya"))
    req = client.get("/proxy-requests", headers=H("p_meena")).json()[0]["request"]
    notify.clear()
    client.post(f"/proxy-requests/{req['id']}/respond", json={"response": "declined"}, headers=H("p_meena"))
    recipients = {m["to"] for m in notify.OUTBOX}
    assert recipients == {"priya@example.com", "sam@example.com"}
    assert svc.store.get_item(item.id).status.value == "proxy_declined"


def test_non_organizer_leaver_cannot_reschedule_directly(client, svc):
    item = next(i for i in svc.store.items() if i.event.title == "Q4 Budget Review")
    r = client.post(f"/items/{item.id}/action", json={"action": "reschedule"}, headers=H("p_priya"))
    assert r.json()["status"] == "awaiting_organizer"
    assert svc.calendar.get("evt_budget").start.day == 21          # untouched
    org = client.get("/items", params={"mode": "organizer"}, headers=H("p_sam")).json()
    assert any(i["id"] == item.id for i in org)
    done = client.post(f"/items/{item.id}/reschedule", headers=H("p_sam"))
    assert done.json()["status"] == "rescheduled"
    assert svc.calendar.get("evt_budget").start.day == 23          # Fri, after Priya is back, same time of day


def test_reschedule_keeps_time_of_day_and_avoids_leave(svc):
    e = svc.calendar.get("evt_budget")
    slot = find_slot(e, svc.calendar, svc.store.absences(), svc.now())
    assert not slot.none
    assert slot.proposedStart.date().isoformat() == "2026-10-23"
    assert (slot.proposedStart.hour, slot.proposedStart.minute) == (e.start.hour, e.start.minute)   # same time of day
    assert slot.windowUsed == "±1h"


def test_sudden_absence_goes_to_the_organizer(client):
    org = client.get("/items", params={"mode": "organizer"}, headers=H("p_sam")).json()
    assert org[0]["event"]["title"] == "Release Readiness"          # earliest first
    assert org[0]["ownerRole"] == "organizer" and org[0]["ai"]["suggestedProxyId"] == "p_dev"
    # Sam also sees Priya's planned-leave items for meetings he organizes, so he can look ahead
    assert {"Q4 Budget Review", "Vendor Contract Decision"} <= {i["event"]["title"] for i in org}
    # no "who is responsible" rule: every unsettled card needs action, for everyone
    counts = client.get("/me", headers=H("p_sam")).json()["counts"]
    meetings = {i["event"]["calendarEventId"] for i in org}       # counted per meeting (one card even if two are out)
    assert counts["organizer"] == len(meetings) and counts["organizerOpen"] == len(meetings)
    assert all(i["needsAttention"] for i in org)
    by = {i["event"]["title"]: i for i in org}
    assert by["Release Readiness"]["urgency"] == "soon"      # starts in 30 hours: amber
    assert by["Q4 Budget Review"]["urgency"] is None        # nine days away: no highlight
    # an unrelated person cannot act on it
    r = client.post(f"/items/{org[0]['id']}/action", json={"action": "proceed_without"}, headers=H("p_neha"))
    assert r.status_code == 403


def test_sick_person_and_organizer_can_both_act(client, svc):
    item = next(i for i in svc.store.items() if i.event.title == "Release Readiness")
    # the absent person (Kiran) names a proxy ...
    r = client.post(f"/items/{item.id}/action", json={"action": "proxy", "proxyId": "p_dev"}, headers=H("p_kiran"))
    assert r.status_code == 200 and r.json()["status"] == "proxy_requested"
    # ... and the organizer (Sam) can still change it
    r = client.post(f"/items/{item.id}/action", json={"action": "proxy", "proxyId": "p_dev"}, headers=H("p_sam"))
    assert r.status_code == 200
    # "I'll attend" is not offered for a sudden absence
    r = client.post(f"/items/{item.id}/action", json={"action": "attend"}, headers=H("p_kiran"))
    assert r.status_code == 400


def test_organizer_can_act_proactively_on_planned_leave_and_leaver_is_told_on_change(client, svc):
    from app import notify
    item = next(i for i in svc.store.items() if i.event.title == "Q4 Budget Review")
    # Sam (organizer) arranges cover for Priya's planned leave before she does anything
    r = client.post(f"/items/{item.id}/action", json={"action": "proxy", "proxyId": "p_meena"}, headers=H("p_sam"))
    assert r.status_code == 200 and r.json()["decidedBy"] == "p_sam"
    # Priya changes it: Sam (who made the decision) gets an email
    notify.clear()
    r = client.post(f"/items/{item.id}/action", json={"action": "proxy", "proxyId": "p_arjun"}, headers=H("p_priya"))
    assert r.status_code == 200
    assert [m["to"] for m in notify.OUTBOX if "changed the decision" in m["subject"]] == ["sam@example.com"]


def test_urgency_is_the_same_for_everyone_and_clears_when_settled(client, svc, monkeypatch):
    from app import config
    from datetime import datetime, timezone
    monkeypatch.setattr(config, "now", lambda: datetime(2026, 10, 20, 18, 0, tzinfo=timezone.utc))
    for person, mode in (("p_sam", "organizer"), ("p_priya", "attendee")):
        data = client.get("/items", params={"mode": mode}, headers=H(person)).json()
        items = data["needsAction"] if mode == "attendee" else data
        by = {i["event"]["title"]: i["urgency"] for i in items}
        assert by["Q4 Budget Review"] == "urgent"           # 23 hours away: red, for both sides
        assert by["Vendor Contract Decision"] == "soon"     # 45 hours away: amber
    item = next(i for i in svc.store.items() if i.event.title == "Q4 Budget Review")
    # an unanswered proxy request is still unsettled, so it stays urgent ...
    client.post(f"/items/{item.id}/action", json={"action": "proxy", "proxyId": "p_meena"}, headers=H("p_priya"))
    row = next(i for i in client.get("/items", params={"mode": "organizer"}, headers=H("p_sam")).json() if i["id"] == item.id)
    assert row["needsAttention"] and row["urgency"] == "urgent"
    # ... and it clears once the proxy accepts
    req = client.get("/proxy-requests", headers=H("p_meena")).json()[0]["request"]
    client.post(f"/proxy-requests/{req['id']}/respond", json={"response": "accepted"}, headers=H("p_meena"))
    row = next(i for i in client.get("/items", params={"mode": "organizer"}, headers=H("p_sam")).json() if i["id"] == item.id)
    assert row["needsAttention"] is False and row["urgency"] is None


def test_each_viewer_gets_a_recommendation_from_what_they_can_open(client):
    # Design Review: Meena organizes; her notes are shared with Dev only, so Priya cannot open them.
    org = client.get("/items", params={"mode": "organizer"}, headers=H("p_meena")).json()
    meena_view = next(i for i in org if i["event"]["title"] == "Design Review")["ai"]
    att = client.get("/items", params={"mode": "attendee"}, headers=H("p_priya")).json()["needsAction"]
    priya_view = next(i for i in att if i["event"]["title"] == "Design Review")["ai"]
    assert meena_view["summariesAvailable"] is True and meena_view["suggestedProxyId"] == "p_dev"
    assert priya_view["summariesAvailable"] is False and priya_view["confidence"] == "low"
    assert "no summaries available to you" in priya_view["sources"]
    # Nothing from the notes' text reaches Priya
    assert "mockups" not in str(priya_view).lower() and "layout" not in str(priya_view).lower()
    # Q4 Budget Review: the notes are shared with Priya and Sam is the organizer, so both can open them -> same result
    org_sam = client.get("/items", params={"mode": "organizer"}, headers=H("p_sam")).json()
    sam = next(i for i in org_sam if i["event"]["title"] == "Q4 Budget Review")["ai"]
    priya_q4 = next(i for i in att if i["event"]["title"] == "Q4 Budget Review")["ai"]
    assert sam["summariesAvailable"] and priya_q4["summariesAvailable"]
    assert sam["recommendation"] == priya_q4["recommendation"] == "proxy"


def test_ai_draft_only_when_the_sender_and_the_proxy_can_both_open_the_summary(client, svc):
    item = next(i for i in svc.store.items() if i.event.title == "Q4 Budget Review")
    url = f"/items/{item.id}/note-draft/available"
    # no proxy chosen yet -> off, with a reason
    first = client.get(url, headers=H("p_priya")).json()
    assert first["available"] is False and "Choose a proxy first" in first["reason"]
    # Meena can open the Budget Review summary -> the draft is offered, and it uses the summary
    assert client.get(url, params={"proxyId": "p_meena"}, headers=H("p_priya")).json() == {"available": True, "reason": None}
    ok = client.post(f"/items/{item.id}/note-draft", params={"proxyId": "p_meena"}, headers=H("p_priya"))
    assert ok.status_code == 200 and "vendor" in ok.json()["draft"].lower()
    # Design Review: the summary is shared with Dev only. Meena (organizer) may draft for Dev, who can open it...
    design = next(i for i in svc.store.items() if i.event.title == "Design Review")
    durl = f"/items/{design.id}/note-draft/available"
    assert client.get(durl, params={"proxyId": "p_dev"}, headers=H("p_meena")).json()["available"] is True
    # ...but not for someone who cannot, and the reason names them
    no = client.get(durl, params={"proxyId": "p_asha"}, headers=H("p_meena")).json()
    assert no["available"] is False and "isn't shared with Asha" in no["reason"]
    assert client.post(f"/items/{design.id}/note-draft", params={"proxyId": "p_asha"}, headers=H("p_meena")).status_code == 400
    # Priya cannot open the Design Review summary at all -> nothing to draft from
    mine = client.get(durl, params={"proxyId": "p_dev"}, headers=H("p_priya")).json()
    assert mine["available"] is False and "No meeting summary is available to you" in mine["reason"]
    # strangers cannot ask
    assert client.get(url, headers=H("p_neha")).status_code == 403


def test_note_travels_with_the_proxy_request(client, svc):
    from app import notify
    item = next(i for i in svc.store.items() if i.event.title == "Q4 Budget Review")
    notify.clear()
    r = client.post(f"/items/{item.id}/action", json={"action": "proxy", "proxyId": "p_meena",
                    "note": "  Budget file is in the shared folder.  ", "noteFromAi": True}, headers=H("p_priya"))
    assert r.status_code == 200
    view = client.get("/proxy-requests", headers=H("p_meena")).json()[0]
    assert view["request"]["note"] == "Budget file is in the shared folder."
    assert "Budget file is in the shared folder." in notify.OUTBOX[-1]["body"]
    assert any("started as an AI draft" in h.detail for h in svc.store.history())


def _priya_asks_meena(client, svc):
    item = next(i for i in svc.store.items() if i.event.title == "Q4 Budget Review")
    client.post(f"/items/{item.id}/action", json={"action": "proxy", "proxyId": "p_meena", "note": "See the folder."},
                headers=H("p_priya"))
    return item


def test_accepted_proxy_request_stays_visible_until_the_meeting_has_passed(client, svc, monkeypatch):
    from app import config
    from datetime import datetime, timezone
    item = _priya_asks_meena(client, svc)
    me = client.get("/me", headers=H("p_meena")).json()["counts"]
    assert me["proxyRequests"] == 1 and me["proxyOpen"] == 1          # one to answer
    req = client.get("/proxy-requests", headers=H("p_meena")).json()[0]["request"]
    client.post(f"/proxy-requests/{req['id']}/respond", json={"response": "accepted"}, headers=H("p_meena"))
    rows = client.get("/proxy-requests", headers=H("p_meena")).json()
    assert len(rows) == 1 and rows[0]["request"]["status"] == "accepted" and rows[0]["request"]["note"] == "See the folder."
    me = client.get("/me", headers=H("p_meena")).json()["counts"]
    assert me["proxyRequests"] == 1 and me["proxyOpen"] == 0           # still listed, nothing left to answer
    # the meeting (Oct 21, 17:00-18:00 UTC) has passed -> it moves to Past, for everyone involved
    monkeypatch.setattr(config, "now", lambda: datetime(2026, 10, 22, 20, 0, tzinfo=timezone.utc))
    assert client.get("/proxy-requests", headers=H("p_meena")).json() == []
    past = client.get("/proxy-requests", params={"past": "true"}, headers=H("p_meena")).json()
    assert "Q4 Budget Review" in [v["item"]["event"]["title"] for v in past]   # (the demo's past week adds others)
    priya_now = client.get("/items", params={"mode": "attendee"}, headers=H("p_priya")).json()
    assert "Q4 Budget Review" not in [i["event"]["title"] for i in priya_now["needsAction"]]
    priya_past = client.get("/items", params={"mode": "past"}, headers=H("p_priya")).json()
    assert "Q4 Budget Review" in [i["event"]["title"] for i in priya_past]
    assert all(i["needsAttention"] is False for i in priya_past)       # nothing to do on a finished meeting
    sam_past = client.get("/items", params={"mode": "past"}, headers=H("p_sam")).json()
    assert "Q4 Budget Review" in [i["event"]["title"] for i in sam_past]


def test_choosing_someone_else_withdraws_the_earlier_proxy(client, svc):
    from app import notify
    item = _priya_asks_meena(client, svc)
    req = client.get("/proxy-requests", headers=H("p_meena")).json()[0]["request"]
    client.post(f"/proxy-requests/{req['id']}/respond", json={"response": "accepted"}, headers=H("p_meena"))
    notify.clear()
    client.post(f"/items/{item.id}/action", json={"action": "proxy", "proxyId": "p_arjun"}, headers=H("p_priya"))
    rows = client.get("/proxy-requests", headers=H("p_meena")).json()
    assert rows[0]["request"]["status"] == "withdrawn"                 # still visible, marked as no longer needed
    assert any(m["to"] == "meena@example.com" and "no longer need" in m["subject"] for m in notify.OUTBOX)
    assert client.get("/me", headers=H("p_meena")).json()["counts"]["proxyOpen"] == 0


def _schedule(client, who, title, start, end, attendees):
    return client.post("/events", headers=H(who), json={
        "title": title, "start": start, "end": end,
        "attendees": [{"personId": p, "optional": opt} for p, opt in attendees]})


def test_scheduling_a_meeting_while_a_key_person_is_out_alerts_the_organizer(client, svc):
    from app import notify
    notify.clear()
    r = _schedule(client, "p_sam", "Vendor Kickoff", "2026-10-21T10:00:00Z", "2026-10-21T11:00:00Z",
                  [("p_priya", False), ("p_meena", False)])
    assert r.status_code == 200
    affected = r.json()["affected"]
    assert [i["absentPersonId"] for i in affected] == ["p_priya"]          # Priya is out on Oct 21
    # the same email as the other flows: one email, to the organizer only
    assert [(m["to"], m["subject"]) for m in notify.OUTBOX] == [
        ("sam@example.com", "You scheduled 'Vendor Kickoff' while Priya Sharma is out")]
    # the card is in the organizer's tab and the absent person's tab, ready for the usual actions
    org = client.get("/items", params={"mode": "organizer"}, headers=H("p_sam")).json()
    assert "Vendor Kickoff" in [i["event"]["title"] for i in org]
    mine = client.get("/items", params={"mode": "attendee"}, headers=H("p_priya")).json()["needsAction"]
    assert "Vendor Kickoff" in [i["event"]["title"] for i in mine]
    # the organizer can fix it at once: reschedule to a day when everyone is free
    item_id = affected[0]["id"]
    moved = client.post(f"/items/{item_id}/reschedule", headers=H("p_sam")).json()
    assert moved["status"] == "rescheduled" and moved["rescheduledTo"].startswith("2026-10-23T10")


def test_optional_attendees_and_people_who_are_in_do_not_trigger_it(client):
    from app import notify
    notify.clear()
    r = _schedule(client, "p_sam", "FYI session", "2026-10-21T10:00:00Z", "2026-10-21T11:00:00Z",
                  [("p_priya", True), ("p_meena", False)])             # Priya is only optional
    assert r.json()["affected"] == [] and notify.OUTBOX == []
    r = _schedule(client, "p_sam", "Later", "2026-10-26T10:00:00Z", "2026-10-26T11:00:00Z",
                  [("p_priya", False)])                                 # Priya is back by then
    assert r.json()["affected"] == [] and notify.OUTBOX == []


def test_several_key_people_out_means_one_email(client):
    from app import notify
    client.post("/dev/simulate-leave-system", json={"personId": "p_meena", "start": "2026-10-21", "end": "2026-10-21"})
    notify.clear()
    r = _schedule(client, "p_sam", "Planning", "2026-10-21T12:00:00Z", "2026-10-21T13:00:00Z",
                  [("p_priya", False), ("p_meena", False)])
    assert len(r.json()["affected"]) == 2
    assert len(notify.OUTBOX) == 1 and notify.OUTBOX[0]["subject"] == "You scheduled 'Planning' while Priya Sharma and Meena Iyer are out"


def test_adding_someone_to_an_existing_meeting_runs_the_same_check(client, svc):
    from app import notify
    r = _schedule(client, "p_sam", "Review", "2026-10-21T12:00:00Z", "2026-10-21T13:00:00Z", [("p_meena", False)])
    event_id = r.json()["eventId"]
    notify.clear()
    stranger = client.post(f"/events/{event_id}/attendees", json={"personId": "p_priya"}, headers=H("p_meena"))
    assert stranger.status_code == 403                                  # only the organizer can add people
    added = client.post(f"/events/{event_id}/attendees", json={"personId": "p_priya"}, headers=H("p_sam"))
    assert added.status_code == 200 and added.json()[0]["absentPersonId"] == "p_priya"
    assert [m["to"] for m in notify.OUTBOX] == ["sam@example.com"]


def test_sudden_means_less_than_24_hours_notice(client):
    # reported on Oct 11 09:00 for a leave that has already started or starts within a day: sudden
    a = client.post("/dev/simulate-leave-system", json={"personId": "p_meena", "start": "2026-10-11", "end": "2026-10-11"}).json()
    assert a["type"] == "sudden"
    b = client.post("/dev/simulate-leave-system", json={"personId": "p_meena", "start": "2026-10-12", "end": "2026-10-12"}).json()
    assert b["type"] == "sudden"                         # starts in 15 hours
    c = client.post("/dev/simulate-leave-system", json={"personId": "p_meena", "start": "2026-10-21", "end": "2026-10-22"}).json()
    assert c["type"] == "planned"                        # ten days' notice, even if it is a planned sick day


def test_no_organizer_email_when_planned_leave_is_created(client):
    from app import notify
    notify.clear()
    r = client.post("/dev/simulate-leave-system", json={"personId": "p_meena", "start": "2026-10-21", "end": "2026-10-22"})
    assert r.status_code == 200
    recipients = {m["to"] for m in notify.OUTBOX}
    assert recipients == {"meena@example.com"}          # only the leaver; Sam (organizer) is not emailed


def test_organizer_is_alerted_once_when_unattended_meeting_is_under_24_hours(client, svc, monkeypatch):
    from app import config, notify
    from datetime import datetime, timezone
    monkeypatch.setattr(config, "now", lambda: datetime(2026, 10, 20, 18, 0, tzinfo=timezone.utc))
    notify.clear()
    client.post("/jobs/run-reminders")
    alerts = [m for m in notify.OUTBOX if m["subject"].startswith("Unresolved")]
    assert any("Q4 Budget Review" in m["subject"] and m["to"] == "sam@example.com" for m in alerts)
    n = len(alerts)
    client.post("/jobs/run-reminders")                  # second run must not repeat the alert
    assert len([m for m in notify.OUTBOX if m["subject"].startswith("Unresolved")]) == n


def test_unrelated_person_has_nothing_to_do(client):
    me = client.get("/me", headers=H("p_neha")).json()
    assert me["counts"] == {"attendee": 0, "organizer": 0, "proxyRequests": 0,
                            "attendeeOpen": 0, "organizerOpen": 0, "proxyOpen": 0}


def test_silent_proxy_gets_reminders_but_nothing_is_changed(client, svc):
    item = next(i for i in svc.store.items() if i.event.title == "Q4 Budget Review")
    client.post(f"/items/{item.id}/action", json={"action": "proxy", "proxyId": "p_meena"}, headers=H("p_priya"))
    for _ in range(5):
        client.post("/jobs/run-reminders")
    req = next(r for r in svc.store.proxy_requests() if r.itemId == item.id)
    assert req.remindersSent == 3 and req.status.value == "pending"
    assert svc.store.get_item(item.id).status.value == "proxy_requested"


def test_outside_proxy_is_added_at_request_and_may_still_decline(client, svc):
    from app import notify
    item = next(i for i in svc.store.items() if i.event.title == "Q4 Budget Review")
    event = svc.calendar.get(item.event.calendarEventId)
    assert "p_asha" not in {a.personId for a in event.attendees}
    found = client.get("/directory", params={"q": "asha@", "day": "2026-10-21"}, headers=H("p_priya")).json()
    assert [p["id"] for p in found] == ["p_asha"] and found[0]["title"] and found[0]["out"] is False
    notify.clear()
    r = client.post(f"/items/{item.id}/action", json={"action": "proxy", "proxyId": "p_asha", "note": "Own the budget ask."},
                    headers=H("p_priya"))
    assert r.status_code == 200 and r.json()["status"] == "proxy_requested"      # no organizer permission needed
    # on the invite straight away, as an optional attendee, whatever she answers
    assert any(a.personId == "p_asha" and a.optional for a in event.attendees)
    assert {m["to"] for m in notify.OUTBOX} == {"asha@example.com", "sam@example.com"}   # request+invite, FYI to organizer
    assert any(h.type == "proxy_added_to_meeting" for h in svc.store.history())
    req = client.get("/proxy-requests", headers=H("p_asha")).json()[0]["request"]
    assert req["addedToMeeting"] is True and req["note"] == "Own the budget ask."
    client.post(f"/proxy-requests/{req['id']}/respond", json={"response": "declined"}, headers=H("p_asha"))
    assert svc.store.get_item(item.id).status.value == "proxy_declined"           # covering was her choice
    assert any(a.personId == "p_asha" for a in event.attendees)                   # still on the invite


def test_replaced_outside_proxy_stays_on_the_invite_but_is_withdrawn(client, svc):
    item = next(i for i in svc.store.items() if i.event.title == "Q4 Budget Review")
    event = svc.calendar.get(item.event.calendarEventId)
    client.post(f"/items/{item.id}/action", json={"action": "proxy", "proxyId": "p_asha"}, headers=H("p_priya"))
    client.post(f"/items/{item.id}/action", json={"action": "proxy", "proxyId": "p_meena"}, headers=H("p_priya"))
    assert any(a.personId == "p_asha" and a.optional for a in event.attendees)      # someone chose her on purpose
    assert svc.store.get_item(item.id).event.attendees == event.attendees           # cards stay in step with the calendar
    old = client.get("/proxy-requests", headers=H("p_asha")).json()[0]["request"]
    assert old["status"] == "withdrawn"                                             # but she no longer has to cover


def test_ai_draft_is_not_offered_for_an_outside_proxy(client, svc):
    item = next(i for i in svc.store.items() if i.event.title == "Q4 Budget Review")
    ok = client.get(f"/items/{item.id}/note-draft/available", params={"proxyId": "p_meena"}, headers=H("p_priya")).json()
    out = client.get(f"/items/{item.id}/note-draft/available", params={"proxyId": "p_asha"}, headers=H("p_priya")).json()
    assert ok["available"] is True and out["available"] is False
    bad = client.post(f"/items/{item.id}/action", json={"action": "proxy", "proxyId": "p_asha", "note": "x", "noteFromAi": True},
                      headers=H("p_priya"))
    assert bad.status_code == 400


def test_proxy_who_is_out_that_day_is_refused(client, svc):
    item = next(i for i in svc.store.items() if i.event.title == "Q4 Budget Review")   # Oct 21; Priya herself is out
    client.post("/absences", json={"personId": "p_rohan", "start": "2026-10-21", "end": "2026-10-21"}, headers=H("p_rohan"))
    r = client.post(f"/items/{item.id}/action", json={"action": "proxy", "proxyId": "p_rohan"}, headers=H("p_priya"))
    assert r.status_code == 400 and "out of office" in r.json()["detail"]
    flagged = client.get("/directory", params={"q": "rohan", "day": "2026-10-21"}, headers=H("p_priya")).json()
    assert flagged[0]["out"] is True


def _org_event(**kw):
    from datetime import datetime, timezone
    from app.models import CalEvent, EventAttendee
    return CalEvent(id="evt_x", title="Site Town Hall", description=kw.get("description", ""),
                    start=datetime(2026, 10, 21, 15, tzinfo=timezone.utc), end=datetime(2026, 10, 21, 16, tzinfo=timezone.utc),
                    organizerId=kw.get("organizer", "p_events"), attendees=[EventAttendee(personId="p_events")],
                    inviteGroup="site-all")


def test_org_event_is_automatic_unless_the_absent_person_runs_it(svc):
    from agents.recommender import recommend
    from app.models import ItemKind
    people = svc.people_map()
    priya = people["p_priya"]
    assert recommend(_org_event(), priya, people, [])[0] == ItemKind.org_event
    # the organizer is out: they may need to hand it over
    kind, ai = recommend(_org_event(organizer="p_priya"), priya, people, [])
    assert kind == ItemKind.key_meeting and ai.confidence.value == "medium"
    # named as a host in the invite text
    kind, _ = recommend(_org_event(description="Priya will host the Q&A at the end."), priya, people, [])
    assert kind == ItemKind.key_meeting
    # named, but not in a hosting role
    kind, _ = recommend(_org_event(description="Priya from Finance may attend."), priya, people, [])
    assert kind == ItemKind.org_event


def test_settings_file_loads_and_drives_the_app(tmp_path):
    from app import settings as cfg
    s = cfg.settings
    assert s.reminders.milestones_hours_before_meeting == [168, 72, 24, 4, 2]
    assert s.reminders.recipients == ["leaver", "organizer"] and s.reminders.send_as_digest is True
    assert s.urgency.urgent_hours == 24 and s.urgency.soon_hours == 72
    # another file can be loaded (SETTINGS_PATH does the same at startup); a missing setting fails loudly
    f = tmp_path / "s.toml"
    f.write_text("[urgency]\nsoon_hours = 48\n", encoding="utf-8")
    other = cfg.load(f)
    assert other.urgency.soon_hours == 48
    with pytest.raises(AttributeError):
        other.urgency.urgent_hours


# ---- the Gemini recommender, tested offline with a fake Gemini (no network, no cost) ----

class _FakeGemini:
    """Stands in for the Google client: returns a ready answer and remembers what it was asked."""
    def __init__(self, answer):
        self.answer, self.asked = answer, []
        self.models = self

    def generate_content(self, model, contents, config):
        self.asked.append(contents)
        from types import SimpleNamespace
        return SimpleNamespace(parsed=self.answer)


def _priya_event(svc, title):
    item = next(i for i in svc.store.items() if i.absentPersonId == "p_priya" and i.event.title == title)
    return svc.calendar.get(item.event.calendarEventId)


def test_ai_prompt_holds_only_what_the_viewer_may_read_and_real_candidates(svc):
    from agents.recommender_ai import build_prompt
    people = svc.people_map()
    priya = people["p_priya"]
    # Design Review: its summaries are NOT shared with Priya -> none may appear
    e = _priya_event(svc, "Design Review")
    prompt = build_prompt(e, priya, people, svc.calendar.visible_notes(e, "p_priya"))
    assert "(none available)" in prompt
    # Q4 Budget Review: summaries are shared; Priya herself is not a candidate; the org-wide group never is
    e = _priya_event(svc, "Q4 Budget Review")
    prompt = build_prompt(e, priya, people, svc.calendar.visible_notes(e, "p_priya"))
    assert "Priya owns the final vendor decision" in prompt
    cand_section = prompt.split("Candidate proxies")[1]
    assert "p_meena" in cand_section and "p_priya" not in cand_section
    e = _priya_event(svc, "Site-wide Tech Talk: Cloud Cost Optimization")
    assert "p_events" not in build_prompt(e, priya, people, []).split("Candidate proxies")[1]


def test_ai_answer_becomes_the_cards_ai_block(svc):
    from agents.recommender_ai import Recommendation, recommend_ai
    from app.models import Action, Confidence, ItemKind
    people = svc.people_map()
    e = _priya_event(svc, "Q4 Budget Review")
    notes = svc.calendar.visible_notes(e, "p_priya")
    fake = _FakeGemini(Recommendation(kind=ItemKind.key_meeting, recommendation=Action.proxy, reason="Meena prepared the numbers.",
                                      confidence=Confidence.high, suggested_proxy_id="p_meena"))
    kind, card = recommend_ai(e, people["p_priya"], people, notes, client=fake)
    assert kind == ItemKind.key_meeting and card.recommendation == Action.proxy and card.suggestedProxyId == "p_meena"
    assert card.sources[0] == "previous summaries (1)" and card.summariesAvailable is True      # facts we know, not AI output
    assert card.fingerprint and fake.asked
    # no summaries: the card says so, whatever the model claimed
    e2 = _priya_event(svc, "Design Review")
    _, card2 = recommend_ai(e2, people["p_priya"], people, [], client=fake)
    assert card2.summariesAvailable is False and "no summaries available to you" in card2.sources


# ---- layer C (agents/guard.py) and the fallback, all offline ----

def _guard_case(svc, title, **ai_fields):
    from agents import guard
    from agents.recommender import recommend
    from app.models import AiResult, ItemKind
    people = svc.people_map()
    priya = people["p_priya"]
    e = _priya_event(svc, title)
    notes = svc.calendar.visible_notes(e, "p_priya")
    kind = ai_fields.pop("kind", ItemKind.key_meeting)
    ai = AiResult(**ai_fields)
    return guard.check(kind, ai, e, priya, people, notes, svc._is_out, lambda: recommend(e, priya, people, notes))


def test_guard_drops_a_proxy_who_is_not_a_candidate_or_is_out(client, svc):
    from app.models import Action, Confidence
    _, ai = _guard_case(svc, "Q4 Budget Review", recommendation=Action.proxy, confidence=Confidence.high, suggestedProxyId="p_zoya")
    assert ai.suggestedProxyId is None and ai.needsHumanChoice and "not one of the candidates" in ai.checks[0]
    client.post("/absences", json={"personId": "p_meena", "start": "2026-10-21", "end": "2026-10-21"}, headers=H("p_meena"))
    _, ai = _guard_case(svc, "Q4 Budget Review", recommendation=Action.proxy, confidence=Confidence.high, suggestedProxyId="p_meena")
    assert ai.suggestedProxyId is None and any("out of office" in c for c in ai.checks)


def test_guard_caps_a_proxy_chosen_without_summaries_but_not_a_title_based_answer(svc):
    from app.models import Action, Confidence
    # Vendor Contract Decision has no summaries: a proxy picked from the reporting line is at most low
    _, ai = _guard_case(svc, "Vendor Contract Decision", recommendation=Action.proxy, confidence=Confidence.high, suggestedProxyId="p_arjun")
    assert ai.confidence == Confidence.low and any("lowered confidence" in c for c in ai.checks)
    # but a reschedule judged from the title alone keeps its confidence
    _, ai = _guard_case(svc, "Vendor Contract Decision", recommendation=Action.reschedule, confidence=Confidence.high)
    assert ai.confidence == Confidence.high and ai.checks == []


def test_guard_keeps_auto_handling_for_confident_cases_only(svc):
    from app.models import Action, Confidence, ItemKind
    kind, _ = _guard_case(svc, "Daily Stand-up", kind=ItemKind.team_checkin, recommendation=Action.proceed_without, confidence=Confidence.high)
    assert kind == ItemKind.team_checkin
    kind, ai = _guard_case(svc, "Daily Stand-up", kind=ItemKind.team_checkin, recommendation=Action.proceed_without, confidence=Confidence.medium)
    assert kind == ItemKind.key_meeting and "not auto-handled" in ai.checks[-1]
    kind, ai = _guard_case(svc, "Design Review", kind=ItemKind.team_checkin, recommendation=Action.proceed_without, confidence=Confidence.high)
    assert kind == ItemKind.key_meeting and "no summaries" in ai.checks[0]          # Priya can't open its summaries


def test_guard_never_lets_the_ai_recommend_attend(svc):
    from app.models import Action, Confidence
    _, ai = _guard_case(svc, "Q4 Budget Review", recommendation=Action.attend, confidence=Confidence.high)
    assert ai.recommendation != Action.attend and "only the person can choose" in ai.checks[0]
    assert ai.engine == "rules_override"          # the card must not claim this came from Gemini


def test_ai_failure_retries_then_falls_back_to_rules_and_is_not_cached(svc, monkeypatch):
    from agents import recommender_ai
    from app.settings import settings as S
    monkeypatch.setattr(S.ai, "enabled", True)
    monkeypatch.setattr(S.ai, "retry_wait_seconds", [0, 0])
    calls = []

    class TooMany(Exception):
        code = 429

    def failing(*a, **k):
        calls.append(1)
        raise TooMany("Resource exhausted")
    monkeypatch.setattr(recommender_ai, "recommend_ai", failing)
    item = next(i for i in svc.store.items() if i.event.title == "Q4 Budget Review")
    svc._analysis_cache.clear()   # the seed analysed every card with the AI off; start fresh
    view = svc._view(item, "p_priya")
    assert len(calls) == S.ai.attempts                                    # tried a few times
    assert view.ai.engine == "rules_fallback" and view.ai.recommendation is not None   # the card still has an answer
    svc._view(item, "p_priya")
    assert len(calls) == 2 * S.ai.attempts                                # not cached: asked again next time


def test_ai_does_not_retry_our_own_mistakes(svc, monkeypatch):
    from agents import recommender_ai
    from app.settings import settings as S
    monkeypatch.setattr(S.ai, "enabled", True)
    calls = []

    class BadRequest(Exception):
        code = 400

    def failing(*a, **k):
        calls.append(1)
        raise BadRequest("bad")
    monkeypatch.setattr(recommender_ai, "recommend_ai", failing)
    item = next(i for i in svc.store.items() if i.event.title == "Q4 Budget Review")
    svc._analysis_cache.clear()
    assert svc._view(item, "p_priya").ai.engine == "rules_fallback" and len(calls) == 1


def test_cache_reuses_answers_until_the_meeting_or_summaries_change(svc, monkeypatch):
    from agents import recommender_ai
    from app.models import Action, AiResult, Confidence, ItemKind
    from app.settings import settings as S
    monkeypatch.setattr(S.ai, "enabled", True)
    calls = []

    def fake(event, absent, people, notes, client=None, is_out=None):
        calls.append(event.description)
        return ItemKind.key_meeting, AiResult(recommendation=Action.proxy, confidence=Confidence.high, reason="r")
    monkeypatch.setattr(recommender_ai, "recommend_ai", fake)
    item = next(i for i in svc.store.items() if i.event.title == "Q4 Budget Review")
    svc._analysis_cache.clear()
    svc._view(item, "p_priya"); svc._view(item, "p_priya")
    assert len(calls) == 1                                   # same meeting, same summaries: Gemini asked once
    svc.calendar.get(item.event.calendarEventId).description = "Now also: approve the travel budget."
    svc._view(item, "p_priya")
    assert len(calls) == 2                                   # the meeting changed: Gemini asked again


def test_creating_cards_never_waits_for_the_ai(svc, monkeypatch, client):
    from agents import recommender_ai
    from app.settings import settings as S
    monkeypatch.setattr(S.ai, "enabled", True)
    monkeypatch.setattr(S.ai, "analyse_on_creation", False)
    called = []
    monkeypatch.setattr(recommender_ai, "recommend_ai", lambda *a, **k: called.append(1))
    r = client.post("/absences", json={"personId": "p_dev", "start": "2026-10-21", "end": "2026-10-21"}, headers=H("p_dev"))
    assert r.status_code == 200 and called == []             # the absence was created with rule-based cards


# ---- Decision 55: one organizer card per meeting; large events; optional invitees ----

def _two_out_meeting(client):
    """Sam organizes a meeting on Oct 21 where both Priya (on leave Oct 20-22) and Dev (out that day) are required."""
    client.post("/absences", json={"personId": "p_dev", "start": "2026-10-21", "end": "2026-10-21"}, headers=H("p_dev"))
    r = client.post("/events", json={"title": "Budget Sync", "description": "Agree the Q4 numbers.",
                                      "start": "2026-10-21T10:00:00Z", "end": "2026-10-21T11:00:00Z",
                                      "attendees": [{"personId": "p_priya"}, {"personId": "p_dev"}, {"personId": "p_meena"}]},
                    headers=H("p_sam"))
    return r.json()["eventId"]


def test_organizer_sees_one_card_per_meeting_naming_everyone_out(client):
    event_id = _two_out_meeting(client)
    meetings = client.get("/organizer/meetings", headers=H("p_sam")).json()
    card = next(m for m in meetings if m["calendarEventId"] == event_id)
    assert sorted(a["absentPersonId"] for a in card["absentees"]) == ["p_dev", "p_priya"]   # one card, both named
    assert card["needsAttention"] and card["ai"]["recommendation"]
    assert len([m for m in meetings if m["calendarEventId"] == event_id]) == 1
    counts = client.get("/me", headers=H("p_sam")).json()["counts"]
    assert counts["organizer"] == len(meetings)                                       # counted per meeting


def test_meeting_level_reschedule_moves_once_and_settles_everyone(client, svc):
    event_id = _two_out_meeting(client)
    before = svc.calendar.get(event_id).start
    card = client.post(f"/meetings/{event_id}/action", json={"action": "reschedule"}, headers=H("p_sam")).json()
    after = svc.calendar.get(event_id).start
    assert after.date().isoformat() == "2026-10-23" and after.hour == before.hour      # first day both are back, same time
    assert {a["status"] for a in card["absentees"]} == {"rescheduled"}
    assert client.post(f"/meetings/{event_id}/action", json={"action": "reschedule"}, headers=H("p_priya")).status_code == 403


def test_rescheduled_meeting_moves_to_no_action_needed_and_leaves_the_counts(client):
    event_id = _two_out_meeting(client)
    before = client.get("/me", headers=H("p_dev")).json()["counts"]["attendee"]
    org_before = client.get("/me", headers=H("p_sam")).json()["counts"]["organizer"]
    client.post(f"/meetings/{event_id}/action", json={"action": "reschedule"}, headers=H("p_sam"))
    dev = client.get("/items", params={"mode": "attendee"}, headers=H("p_dev")).json()
    moved = [i for i in dev["noActionNeeded"]["rescheduledOrCancelled"] if i["event"]["calendarEventId"] == event_id]
    assert len(moved) == 1 and moved[0]["originalStart"].startswith("2026-10-21T10:00")   # old time kept, to strike out
    assert moved[0]["event"]["start"].startswith("2026-10-23")
    assert not any(i["event"]["calendarEventId"] == event_id for i in dev["needsAction"])
    assert client.get("/me", headers=H("p_dev")).json()["counts"]["attendee"] == before - 1
    card = next(m for m in client.get("/organizer/meetings", headers=H("p_sam")).json() if m["calendarEventId"] == event_id)
    assert card["done"]                                                               # organizer: under "Done"
    assert client.get("/me", headers=H("p_sam")).json()["counts"]["organizer"] == org_before - 1


def test_go_on_without_them_keeps_a_proxy_already_arranged(client, svc):
    event_id = _two_out_meeting(client)
    priya_item = next(i for i in svc.store.items() if i.event.calendarEventId == event_id and i.absentPersonId == "p_priya")
    client.post(f"/items/{priya_item.id}/action", json={"action": "proxy", "proxyId": "p_meena"}, headers=H("p_priya"))
    card = client.post(f"/meetings/{event_id}/action", json={"action": "proceed_without"}, headers=H("p_sam")).json()
    status = {a["absentPersonId"]: a["status"] for a in card["absentees"]}
    assert status == {"p_priya": "proxy_requested", "p_dev": "proceeding_without"}


def test_alert_under_24_hours_is_one_email_per_meeting(client, svc):
    from app import notify
    event_id = _two_out_meeting(client)
    for i in svc.store.items():
        if i.event.calendarEventId == event_id:
            i.organizerAlerted = False
    svc.now = lambda: __import__("datetime").datetime(2026, 10, 20, 15, tzinfo=__import__("datetime").timezone.utc)
    notify.clear()
    svc.run_reminders()
    to_sam = [m for m in notify.OUTBOX if m["to"] == "sam@example.com" and "Budget Sync" in m["subject"]]
    assert len(to_sam) == 1 and "Dev Nair and Priya Sharma are out" in to_sam[0]["subject"]


def test_large_event_ordinary_attendee_is_not_a_key_person(monkeypatch, client, svc):
    from app.settings import settings as S
    many = [{"personId": p} for p in ("p_priya", "p_arjun", "p_meena", "p_kiran", "p_dev", "p_vera", "p_neha", "p_asha",
                                       "p_rohan", "p_tara", "p_ishaan", "p_naomi", "p_leo", "p_zoya", "p_ben", "p_lena")]
    monkeypatch.setattr(S.recommendation, "large_meeting_required_threshold", 15)   # the rule, whatever the config value
    assert len(many) > S.recommendation.large_meeting_required_threshold
    r = client.post("/events", json={"title": "Q4 All-Hands", "description": "Vera will host. Ben is the keynote speaker.",
                                      "start": "2026-10-21T16:00:00Z", "end": "2026-10-21T17:00:00Z", "attendees": many},
                    headers=H("p_sam"))
    event_id = r.json()["eventId"]
    # Priya (on leave) is an ordinary attendee: her own quiet card only, no organizer card
    mine = client.get("/items", params={"mode": "attendee"}, headers=H("p_priya")).json()
    assert any(i["event"]["title"] == "Q4 All-Hands" for i in mine["noActionNeeded"]["orgEvents"])
    assert all(m["calendarEventId"] != event_id for m in client.get("/organizer/meetings", headers=H("p_sam")).json())
    # Ben is the keynote speaker: if he is out, the organizer needs to act
    client.post("/absences", json={"personId": "p_ben", "start": "2026-10-21", "end": "2026-10-21"}, headers=H("p_ben"))
    card = next(m for m in client.get("/organizer/meetings", headers=H("p_sam")).json() if m["calendarEventId"] == event_id)
    assert [a["absentPersonId"] for a in card["absentees"]] == ["p_ben"]


def test_optional_invitees_never_trigger_anything(client, svc):
    r = client.post("/events", json={"title": "FYI Demo", "start": "2026-10-21T12:00:00Z", "end": "2026-10-21T12:30:00Z",
                                      "attendees": [{"personId": "p_meena"}, {"personId": "p_neha", "optional": True}]},
                    headers=H("p_sam"))
    event_id = r.json()["eventId"]
    client.post("/absences", json={"personId": "p_neha", "start": "2026-10-21", "end": "2026-10-21"}, headers=H("p_neha"))
    assert not [i for i in svc.store.items() if i.event.calendarEventId == event_id]


def test_ai_prompt_never_lists_the_whole_audience(svc):
    from agents.recommender_ai import build_prompt
    from app.models import CalEvent, EventAttendee
    from app.settings import settings as S
    from datetime import datetime, timezone
    people = svc.people_map()
    ids = [p for p in people if p not in ("p_priya", "p_events")]
    e = CalEvent(id="evt_big", title="Planning", start=datetime(2026, 10, 21, 9, tzinfo=timezone.utc),
                 end=datetime(2026, 10, 21, 10, tzinfo=timezone.utc), organizerId="p_sam",
                 attendees=[EventAttendee(personId=p) for p in ids + ["p_priya"]])
    old = S.ai.max_candidates
    S.ai.max_candidates = 5
    try:
        prompt = build_prompt(e, people["p_priya"], people, [])
    finally:
        S.ai.max_candidates = old
    listed = prompt.split("Candidate proxies")[1].strip().splitlines()[1:]
    assert len(listed) == 5 and f"Invitees besides the person on leave: {len(ids)}" in prompt
    assert any("p_arjun" in line for line in listed)        # the manager (reporting line) makes the short list



def test_people_out_that_day_are_never_offered_to_the_ai(client, svc):
    from agents.recommender_ai import build_prompt
    event_id = _two_out_meeting(client)
    e = svc.calendar.get(event_id)
    people = svc.people_map()
    prompt = build_prompt(e, people["p_dev"], people, [], svc._is_out)
    cands = prompt.split("Candidate proxies")[1]
    assert "p_priya" not in cands and "p_meena" in cands          # Priya is on leave that day too
    # and if the AI names her anyway, the checks drop her and the reason says why
    from app.models import Action, Confidence
    from agents import guard
    from agents.recommender import recommend
    from app.models import AiResult, ItemKind
    _, ai = guard.check(ItemKind.key_meeting, AiResult(recommendation=Action.proxy, confidence=Confidence.medium,
                        reason="Priya can cover.", suggestedProxyId="p_priya"), e, people["p_dev"], people, [],
                        svc._is_out, lambda: recommend(e, people["p_dev"], people, []))
    assert ai.suggestedProxyId is None and "also out that day" in ai.reason


# ---- the ADK meeting advisor (agents/adk_advisor.py), all offline: a fake loop stands in for Gemini ----

def _adk_on(monkeypatch, fake_run):
    from agents import adk_advisor
    from app.settings import settings as S
    monkeypatch.setattr(S.ai, "enabled", True)
    monkeypatch.setattr(S.ai, "engine", "adk")
    monkeypatch.setattr(adk_advisor, "_get_agent_client", lambda: None)
    monkeypatch.setattr(adk_advisor, "_run_sync", fake_run)


def test_adk_tools_see_only_this_meeting_and_this_viewers_summaries(svc, client):
    from agents.adk_advisor import make_tools
    people = svc.people_map()
    e = _priya_event(svc, "Design Review")                      # its summaries are NOT shared with Priya
    tools = {t.__name__: t for t in make_tools(e, people["p_priya"], people, svc.calendar.visible_notes(e, "p_priya"))}
    assert set(tools) == {"read_summaries", "list_proxy_candidates", "check_if_out"}
    assert tools["read_summaries"]() == {"summaries": [], "count": 0}
    from agents.adk_advisor import describe_meeting
    assert "Meeting: Design Review" in describe_meeting(e, people["p_priya"], people)      # details go in the message
    # people out that day are never candidates, and check_if_out answers by name or id
    event_id = _two_out_meeting(client)
    e2 = svc.calendar.get(event_id)
    tools2 = {t.__name__: t for t in make_tools(e2, people["p_priya"], people, [], svc._is_out)}
    ids = [c["id"] for c in tools2["list_proxy_candidates"]()["candidates"]]
    assert "p_dev" not in ids and "p_priya" not in ids and "p_meena" in ids
    assert tools2["check_if_out"]("Dev")["out_on_meeting_day"] is True
    assert tools2["check_if_out"]("p_meena")["out_on_meeting_day"] is False
    assert tools2["check_if_out"]("Nobody")["found"] is False


def test_adk_agent_answers_the_card_with_the_tools_it_used(monkeypatch, svc):
    def fake_run(agent, text):
        assert agent.name == "meeting_advisor" and len(agent.tools) == 3 and "Q4 Budget Review" in text
        summaries = agent.tools[0]()                         # the loop calls our real tools
        assert summaries["count"] == 1
        return ({"kind": "key_meeting", "recommendation": "proxy", "reason": "Meena prepared the cost comparison.",
                 "confidence": "high", "suggested_proxy_id": "p_meena"}, ["get_meeting", "read_summaries", "list_proxy_candidates"])
    _adk_on(monkeypatch, fake_run)
    item = next(i for i in svc.store.items() if i.absentPersonId == "p_priya" and i.event.title == "Q4 Budget Review")
    svc._analysis_cache.clear()
    ai = svc._view(item, "p_priya").ai
    assert ai.engine == "gemini_adk" and ai.suggestedProxyId == "p_meena"
    assert ai.toolsUsed == ["get_meeting", "read_summaries", "list_proxy_candidates"]


def test_adk_answer_is_still_checked_by_our_rules(monkeypatch, client, svc):
    event_id = _two_out_meeting(client)
    _adk_on(monkeypatch, lambda agent, text: ({"kind": "key_meeting", "recommendation": "proxy", "reason": "Dev can cover.",
                                         "confidence": "high", "suggested_proxy_id": "p_dev"}, ["list_proxy_candidates"]))
    item = next(i for i in svc.store.items() if i.event.calendarEventId == event_id and i.absentPersonId == "p_priya")
    svc._analysis_cache.clear()
    ai = svc._view(item, "p_sam").ai
    assert ai.engine == "gemini_adk" and ai.suggestedProxyId is None and "also out that day" in ai.reason


def test_adk_failure_falls_back_to_the_single_call_then_the_rules(monkeypatch, svc):
    from agents import recommender_ai
    from agents.recommender_ai import Recommendation
    from app.models import Action, Confidence, ItemKind
    from app.settings import settings as S

    def broken(agent, text):
        raise TimeoutError("agent too slow")
    _adk_on(monkeypatch, broken)
    monkeypatch.setattr(S.ai, "retry_wait_seconds", [0, 0])
    single = []

    def one_call(event, absent, people, notes, client=None, is_out=None):
        single.append(1)
        return recommender_ai.to_ai_result(Recommendation(kind=ItemKind.key_meeting, recommendation=Action.proxy,
                                           reason="Meena can cover.", confidence=Confidence.medium,
                                           suggested_proxy_id="p_meena"), notes)
    monkeypatch.setattr(recommender_ai, "recommend_ai", one_call)
    item = next(i for i in svc.store.items() if i.absentPersonId == "p_priya" and i.event.title == "Q4 Budget Review")
    svc._analysis_cache.clear()
    ai = svc._view(item, "p_priya").ai
    assert ai.engine == "gemini" and single and any("ADK agent unavailable" in c for c in ai.checks)

    def also_broken(*a, **k):
        raise TimeoutError("no answer")
    monkeypatch.setattr(recommender_ai, "recommend_ai", also_broken)
    svc._analysis_cache.clear()
    assert svc._view(item, "p_priya").ai.engine == "rules_fallback"


def test_background_analysis_answers_at_once_then_fills_in_the_ai(monkeypatch, svc):
    from app.settings import settings as S
    _adk_on(monkeypatch, lambda agent, text: ({"kind": "key_meeting", "recommendation": "proxy", "reason": "Meena can cover.",
                                         "confidence": "high", "suggested_proxy_id": "p_meena"}, ["get_meeting"]))
    monkeypatch.setattr(S.ai, "background", True)
    item = next(i for i in svc.store.items() if i.absentPersonId == "p_priya" and i.event.title == "Q4 Budget Review")
    svc._analysis_cache.clear()
    first = svc._view(item, "p_priya").ai
    assert first.engine == "analysing" and first.recommendation is not None   # rules' suggestion shown right away
    svc.wait_for_analysis()
    assert svc._view(item, "p_priya").ai.engine == "gemini_adk"                # then the agent's answer

    # a failure is shown as "AI unavailable" and not retried on every refresh
    def broken(agent, text):
        raise TimeoutError("slow")
    from agents import adk_advisor, recommender_ai
    monkeypatch.setattr(adk_advisor, "_run_sync", broken)
    monkeypatch.setattr(recommender_ai, "recommend_ai", lambda *a, **k: (_ for _ in ()).throw(TimeoutError("slow")))
    monkeypatch.setattr(S.ai, "retry_wait_seconds", [0, 0])
    svc._analysis_cache.clear()
    svc._view(item, "p_priya"); svc.wait_for_analysis()
    assert svc._view(item, "p_priya").ai.engine == "rules_fallback"
    assert not svc._pending                                                    # nothing re-queued straight away


# ---- the Gemini handover brief (agents/note_drafter.py), offline ----

def test_gemini_handover_brief_is_built_from_the_shared_summaries(monkeypatch, svc):
    from agents import note_drafter
    from agents.note_drafter import HandoverBrief, draft_note
    from app.settings import settings as S
    monkeypatch.setattr(S.ai, "enabled", True)
    people = svc.people_map()
    e = _priya_event(svc, "Q4 Budget Review")
    notes = svc.calendar.visible_notes(e, "p_priya")
    fake = _FakeGemini(HandoverBrief(
        meeting_purpose="The quarterly review of the budget and vendor choice.",
        covering_for="You cover Priya's final vendor decision and sign-off.",
        key_points=["Vendor shortlist approved.", "  ", "Meena prepared the cost comparison."],
        open_items=["Confirm the contract terms."], check_with="Check with Sam (organizer) if unsure."))
    text, engine = draft_note(e, people["p_priya"], notes, people["p_meena"], client=fake)
    assert engine == "gemini" and text.startswith("Hi Meena, thanks for covering 'Q4 Budget Review'")
    assert "- Vendor shortlist approved." in text and "Still open:" in text and "- Confirm the contract terms." in text
    assert "-   " not in text                                         # empty points dropped by our code
    prompt = fake.asked[0]
    assert "Priya owns the final vendor decision" in prompt and "Meena Iyer" in prompt
    # privacy: only the summaries passed in reach Gemini
    _, engine2 = draft_note(e, people["p_priya"], [], people["p_meena"], client=fake)
    assert "Priya owns" not in fake.asked[1]


def test_handover_brief_falls_back_to_the_simple_draft(monkeypatch, client, svc):
    from agents import note_drafter
    from app.settings import settings as S
    monkeypatch.setattr(S.ai, "enabled", True)
    monkeypatch.setattr(S.ai, "retry_wait_seconds", [0, 0])

    def broken(prompt, client=None):
        raise TimeoutError("no answer")
    monkeypatch.setattr(note_drafter, "ask_gemini", broken)
    item = next(i for i in svc.store.items() if i.event.title == "Q4 Budget Review")
    r = client.post(f"/items/{item.id}/note-draft", params={"proxyId": "p_meena"}, headers=H("p_priya")).json()
    assert r["engine"] == "rules_fallback" and "vendor" in r["draft"].lower()      # still a usable draft


def test_handover_brief_never_sends_the_proxy_to_themselves_or_to_the_absent_person(svc):
    from agents.note_drafter import _check_with
    people = svc.people_map()
    priya, dev, meena, sam = people["p_priya"], people["p_dev"], people["p_meena"], people["p_sam"]
    assert _check_with("If unsure, check with Dev.", priya, dev, meena) == \
        "If anything is unclear, check with Meena, who organizes the meeting."          # not the proxy himself
    assert "Sam" in _check_with("Check with Priya if anything is unclear.", priya, meena, sam)   # Priya is away
    assert _check_with("Ask Dev.", priya, dev, dev) == "If anything is unclear, reply to this note."  # proxy organizes
    assert _check_with("Check with Arjun, her manager.", priya, meena, sam) == "Check with Arjun, her manager."


def test_large_event_goes_to_the_ai_only_when_the_absent_person_is_named(svc):
    from agents.orchestrator import ai_needed
    from app.models import CalEvent, EventAttendee
    from datetime import datetime, timezone
    people = svc.people_map()
    when = datetime(2026, 10, 27, 10, tzinfo=timezone.utc)
    base = dict(id="x", start=when, end=when, organizerId="p_vera", inviteGroup="site-all",
                attendees=[EventAttendee(personId="p_arjun"), EventAttendee(personId="p_meena")])
    talk = CalEvent(title="All-hands: H2 plan", description="Arjun walks us through the H2 numbers.", **base)
    assert ai_needed(talk, people["p_arjun"], []) is True          # named, no hosting word: the AI should look
    assert ai_needed(talk, people["p_meena"], []) is False         # ordinary attendee: rules, no AI call


def test_ai_can_raise_an_auto_handled_card_but_never_hide_one(monkeypatch, svc):
    from app.models import AiResult, Confidence, ItemKind, ItemStatus, Action
    from app.settings import settings as S
    standup = next(i for i in svc.store.items() if i.absentPersonId == "p_priya" and i.kind == ItemKind.team_checkin)
    assert standup.status == ItemStatus.auto_handled
    ai = AiResult(recommendation=Action.proxy, confidence=Confidence.high, reason="Sign-offs happen here.", engine="gemini_adk")
    svc._maybe_raise(standup.id, "p_sam", ItemKind.key_meeting, ai)              # not the absent person's view: no change
    assert svc.store.get_item(standup.id).kind == ItemKind.team_checkin
    svc._maybe_raise(standup.id, "p_priya", ItemKind.key_meeting, ai)            # the absent person's view: raised
    raised = svc.store.get_item(standup.id)
    assert raised.kind == ItemKind.key_meeting and raised.status == ItemStatus.pending_decision
    assert any(h.type == "ai_raised" for h in svc.store.history())
    budget = next(i for i in svc.store.items() if i.absentPersonId == "p_priya" and i.event.title == "Q4 Budget Review")
    svc._maybe_raise(budget.id, "p_priya", ItemKind.team_checkin, ai)            # never downwards
    assert svc.store.get_item(budget.id).kind == ItemKind.key_meeting
    monkeypatch.setattr(S.ai, "ai_may_raise_to_key_meeting", False)              # and it can be switched off
    other = next(i for i in svc.store.items() if i.absentPersonId == "p_priya" and i.kind == ItemKind.team_checkin)
    svc._maybe_raise(other.id, "p_priya", ItemKind.key_meeting, ai)
    assert svc.store.get_item(other.id).kind == ItemKind.team_checkin


def test_impact_tiles_start_from_the_handled_past_week(client, svc):
    m = client.get("/metrics").json()
    assert m["meetingsWithPlan"] >= 4 and m["meetingsAffected"] > m["meetingsWithPlan"]
    assert m["teamHoursSaved"] > 0 and m["avgNoticeDays"] > 0
    assert m["decisionsCounted"] >= 4 and m["recommendationsFollowedPct"] is not None
    assert "proxy accepted 36 min" in m["estimateNote"]                      # the formula comes from the config
    # the past week does not show as an upcoming absence
    assert client.get("/absences", headers=H("p_dev")).json() == []


def test_reset_demo_restores_the_data_and_empties_the_ai_cache(client, svc):
    item = next(i for i in svc.store.items() if i.event.title == "Q4 Budget Review")
    client.post(f"/items/{item.id}/action", json={"action": "proceed_without"}, headers=H("p_priya"))
    svc._analysis_cache[("x",)] = None
    assert client.post("/dev/reset-demo").json() == {"ok": True}
    again = next(i for i in svc.store.items() if i.event.title == "Q4 Budget Review")
    assert again.status.value == "pending_decision" and ("x",) not in svc._analysis_cache


def test_routine_kind_with_an_action_becomes_a_key_meeting(svc):
    from agents import guard
    from agents.recommender import recommend
    from app.models import Action, AiResult, Confidence, ItemKind
    people = svc.people_map()
    e = svc.calendar.get("evt_allhands")
    kind, ai = guard.check(ItemKind.org_event, AiResult(recommendation=Action.reschedule, confidence=Confidence.high,
                           reason="Arjun presents the H2 numbers."), e, people["p_arjun"], people, [],
                           svc._is_out, lambda: recommend(e, people["p_arjun"], people, []))
    assert kind == ItemKind.key_meeting and any("needs a decision" in c for c in ai.checks)


def test_a_repeated_answer_is_harmless_and_messages_are_polite(client, svc):
    item = next(i for i in svc.store.items() if i.event.title == "Q4 Budget Review")
    client.post(f"/items/{item.id}/action", json={"action": "proxy", "proxyId": "p_meena"}, headers=H("p_priya"))
    req = next(r for r in svc.store.proxy_requests() if r.itemId == item.id and r.status.value == "pending")
    url = f"/proxy-requests/{req.id}/respond"
    assert client.post(url, json={"response": "accepted"}, headers=H("p_meena")).status_code == 200
    assert client.post(url, json={"response": "accepted"}, headers=H("p_meena")).status_code == 200   # double click
    changed = client.post(url, json={"response": "declined"}, headers=H("p_meena"))
    assert changed.status_code == 400 and changed.json()["detail"] == "You've already answered this request."
    missing = client.post("/items/nope/action", json={"action": "proceed_without"}, headers=H("p_priya")).json()["detail"]
    assert missing[0].isupper() and missing.endswith(".")


def test_second_choice_is_checked_like_the_first(client, svc):
    from agents import guard
    from agents.recommender import recommend
    from app.models import Action, AiResult, Confidence, ItemKind
    people = svc.people_map()
    event_id = _two_out_meeting(client)                       # Budget Sync, Oct 21: Priya and Dev out, Meena in
    e = svc.calendar.get(event_id)
    chk = lambda ai: guard.check(ItemKind.key_meeting, ai, e, people["p_priya"], people, [], svc._is_out,   # noqa: E731
                                 lambda: recommend(e, people["p_priya"], people, []))
    # second choice out that day -> dropped
    _, ai = chk(AiResult(recommendation=Action.proxy, confidence=Confidence.medium, reason="x",
                         suggestedProxyId="p_meena", backupProxyId="p_dev"))
    assert ai.suggestedProxyId == "p_meena" and ai.backupProxyId is None
    # first choice out, second fine -> the second moves up, and the reason says so
    _, ai = chk(AiResult(recommendation=Action.proxy, confidence=Confidence.medium, reason="x",
                         suggestedProxyId="p_dev", backupProxyId="p_meena"))
    assert ai.suggestedProxyId == "p_meena" and ai.backupProxyId is None and "Meena Iyer is suggested instead" in ai.reason
    # same person twice, or a second choice on a non-proxy answer -> dropped
    _, ai = chk(AiResult(recommendation=Action.proxy, confidence=Confidence.medium, reason="x",
                         suggestedProxyId="p_meena", backupProxyId="p_meena"))
    assert ai.backupProxyId is None
    _, ai = chk(AiResult(recommendation=Action.reschedule, confidence=Confidence.medium, reason="x", backupProxyId="p_meena"))
    assert ai.backupProxyId is None


def test_a_decline_is_shown_without_asking_the_ai_again(monkeypatch, client, svc):
    from agents import recommender_ai
    from agents.recommender_ai import Recommendation
    from app.models import Action, Confidence, ItemKind
    from app.settings import settings as S
    monkeypatch.setattr(S.ai, "enabled", True)
    calls = []

    def fake(event, absent, people, notes, client=None, is_out=None):
        calls.append(1)
        return recommender_ai.to_ai_result(Recommendation(kind=ItemKind.key_meeting, recommendation=Action.proxy,
                                           reason="Meena prepared the numbers.", confidence=Confidence.high,
                                           suggested_proxy_id="p_meena", backup_proxy_id="p_arjun"), notes)
    monkeypatch.setattr(recommender_ai, "recommend_ai", fake)
    item = next(i for i in svc.store.items() if i.event.title == "Q4 Budget Review")
    svc._analysis_cache.clear()
    first = svc._view(item, "p_priya")
    assert (first.ai.suggestedProxyId, first.ai.backupProxyId) == ("p_meena", "p_arjun") and len(calls) == 1
    client.post(f"/items/{item.id}/action", json={"action": "proxy", "proxyId": "p_meena"}, headers=H("p_priya"))
    req = next(r for r in svc.store.proxy_requests() if r.itemId == item.id and r.status.value == "pending")
    client.post(f"/proxy-requests/{req.id}/respond", json={"response": "declined"}, headers=H("p_meena"))
    after = svc._view(svc.store.get_item(item.id), "p_priya")
    assert after.status.value == "proxy_declined" and after.declinedProxyIds == ["p_meena"]
    assert len(calls) == 1                                                    # no new AI call after the decline
    assert after.ai.backupProxyId == "p_arjun"                                # the second choice is still on the card
    cands = {c["personId"]: c for c in client.get(f"/items/{item.id}/proxy-candidates", headers=H("p_priya")).json()}
    assert cands["p_meena"]["declined"] is True and cands["p_meena"]["choice"] == "first"   # still pickable, marked
    assert cands["p_arjun"]["choice"] == "second"