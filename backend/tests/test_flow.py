"""Basic checks of the rules we agreed on. Run from backend/: python -m pytest"""
import os

os.environ["NOW"] = "2026-10-11T09:00:00Z"

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.seed import build_service
from app.scheduling import find_slot


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
    assert slot.proposedStart.hour == 17 and slot.windowUsed == "±1h"


def test_sudden_absence_goes_to_the_organizer(client):
    org = client.get("/items", params={"mode": "organizer"}, headers=H("p_sam")).json()
    assert org[0]["event"]["title"] == "Release Readiness"          # earliest first
    assert org[0]["ownerRole"] == "organizer" and org[0]["ai"]["suggestedProxyId"] == "p_dev"
    # Sam also sees Priya's planned-leave items for meetings he organizes, so he can look ahead
    assert {"Q4 Budget Review", "Vendor Contract Decision"} <= {i["event"]["title"] for i in org}
    # no "who is responsible" rule: every unsettled card needs action, for everyone
    counts = client.get("/me", headers=H("p_sam")).json()["counts"]
    assert counts["organizer"] == len(org) and counts["organizerOpen"] == len(org)
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


def test_ai_draft_only_when_the_summary_is_shared_with_everyone_invited(client, svc):
    from app.models import EventAttendee
    item = next(i for i in svc.store.items() if i.event.title == "Q4 Budget Review")
    url = f"/items/{item.id}/note-draft/available"
    # the host shared the Budget Review notes with every invitee -> the draft is offered
    assert client.get(url, headers=H("p_priya")).json() == {"available": True}
    ok = client.post(f"/items/{item.id}/note-draft", headers=H("p_priya"))
    assert ok.status_code == 200 and "vendor" in ok.json()["draft"].lower()
    # a partly shared summary (Dev is invited but the notes are not shared with him) -> no draft for anyone
    svc.calendar.get("evt_budget").attendees.append(EventAttendee(personId="p_dev"))
    assert client.get(url, headers=H("p_priya")).json() == {"available": False}
    assert client.post(f"/items/{item.id}/note-draft", headers=H("p_priya")).status_code == 400
    # Design Review notes are shared with Dev only -> not open to everyone
    design = next(i for i in svc.store.items() if i.event.title == "Design Review")
    assert client.get(f"/items/{design.id}/note-draft/available", headers=H("p_meena")).json() == {"available": False}
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
    assert [v["item"]["event"]["title"] for v in past] == ["Q4 Budget Review"]
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
    req = svc.store.proxy_requests()[0]
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
