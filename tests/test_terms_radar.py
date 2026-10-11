"""
Deterministic tests for TermsRadar using genlayer-test's Direct Mode.

Every decision TermsRadar makes is a pure function of TermsShift's own check
record, so the inputs here are TermsShift's real checks as they stand on Studio
Next (captured 2026-10-11, tests/fixtures/): Circle's USDC terms unchanged since
2 October 2026; Circle's against October 2024 (two areas changed, read in full
and judged not adverse - "blacklisting" became "blocklisting"); and Tether's
against December 2023 (all six areas changed, five judged adverse with verified
quotes). Direct Mode can't simulate a cross-contract call, so the reads of
TermsShift (track, acknowledge, allocate, get_status) are proven live; what is
tested here is every rule they apply, and everything that runs before them.

Three layers: the sign-off digest, the posture ladder, and the contract's own
checks.
"""

import copy
import json
import pathlib
import sys

import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
CIRCLE_CLEAR = json.loads((FIXTURES / "check_circle-since-2026.json").read_text())
CIRCLE_CHANGED = json.loads((FIXTURES / "check_circle-since-2024.json").read_text())
TETHER_ADVERSE = json.loads((FIXTURES / "check_tether-since-2023.json").read_text())
SHIFT = "0x" + "77" * 20     # never actually called in these tests
MAX_AGE = 3600
ACKED_PCT = 50


def _deploy(direct_vm, direct_deploy, owner, max_age=MAX_AGE, pct=ACKED_PCT):
    direct_vm.sender = owner
    return direct_deploy("contracts/terms_radar.py", SHIFT, max_age, pct)


@pytest.fixture
def mod(direct_vm, direct_deploy, direct_owner):
    """The loaded contract module itself, for its pure functions (Direct Mode allows one contract class per process)."""
    _deploy(direct_vm, direct_deploy, direct_owner)
    return sys.modules["_contract_terms_radar"]


def _seconds(check):
    import datetime
    return int(datetime.datetime.fromisoformat(check["checked_at"]).timestamp())


def _posture(mod, check, ack=None, seconds_after=60, max_age=MAX_AGE, pct=ACKED_PCT):
    return mod._posture(check, ack, _seconds(check) + seconds_after, max_age, pct)


# --- 1. The sign-off digest ------------------------------------------------------------


def test_the_digest_binds_the_areas_that_changed_and_their_wording(mod):
    d = mod._change_digest(TETHER_ADVERSE)
    assert len(d) == 64 and d == mod._change_digest(copy.deepcopy(TETHER_ADVERSE))
    one = copy.deepcopy(TETHER_ADVERSE)
    one["facts"]["areas"]["fees"]["excerpt_digest"] = "0" * 64                 # the changed wording differs
    assert mod._change_digest(one) != d
    two = copy.deepcopy(TETHER_ADVERSE)
    two["facts"]["areas"]["fees"]["status"] = "REMOVED"                         # the area's status differs
    assert mod._change_digest(two) != d
    three = copy.deepcopy(TETHER_ADVERSE)
    del three["facts"]["areas"]["amendment"]                                    # an area that changed is missing
    assert mod._change_digest(three) != d


def test_the_digest_does_not_depend_on_the_order_the_areas_arrive_in(mod):
    d = mod._change_digest(TETHER_ADVERSE)
    shuffled = copy.deepcopy(TETHER_ADVERSE)
    shuffled["facts"]["areas"] = dict(reversed(list(shuffled["facts"]["areas"].items())))
    assert list(shuffled["facts"]["areas"]) != list(TETHER_ADVERSE["facts"]["areas"])
    assert mod._change_digest(shuffled) == d


def test_the_digest_ignores_what_validators_may_say_differently_each_time(mod):
    d = mod._change_digest(TETHER_ADVERSE)
    other = copy.deepcopy(TETHER_ADVERSE)
    other.update(check_id=99, checked_at="2026-12-01T00:00:00+00:00", submitted_by="0x" + "11" * 20, reasons=["adverse:fees"])
    other["labels"] = {k: "UNDETERMINED" for k in other["labels"]}
    other["readings"] = {}
    for a in other["facts"]["areas"].values():
        a["old_preview"], a["new_preview"] = "different preview text", "different preview text"
    assert mod._change_digest(other) == d


def test_an_unchanged_area_does_not_enter_the_digest(mod):
    empty = mod._change_digest(CIRCLE_CLEAR)                                    # nothing changed
    assert empty == mod._change_digest({"facts": {"areas": {}}}) == mod._change_digest({})
    clear = copy.deepcopy(CIRCLE_CLEAR)
    clear["facts"]["areas"]["fees"]["excerpt_digest"] = "ab" * 32               # an UNCHANGED area's digest is noise
    assert mod._change_digest(clear) == empty


def test_the_digest_differs_between_the_real_checks(mod):
    digests = {mod._change_digest(c) for c in (CIRCLE_CLEAR, CIRCLE_CHANGED, TETHER_ADVERSE)}
    assert len(digests) == 3


# --- 2. The posture ladder, on TermsShift's real checks ------------------------------------------


def test_unchanged_terms_are_clear_at_full_allocation(mod):
    p = _posture(mod, CIRCLE_CLEAR)
    assert p["posture"] == "CLEAR" and p["allowed_pct"] == 100


def test_terms_that_changed_but_were_read_in_full_as_not_adverse_are_allowed_in_full(mod):
    p = _posture(mod, CIRCLE_CHANGED)
    assert p["posture"] == "CHANGED" and p["allowed_pct"] == 100


def test_a_material_adverse_change_nobody_signed_off_allows_nothing(mod):
    p = _posture(mod, TETHER_ADVERSE)
    assert p["posture"] == "ADVERSE_UNACKNOWLEDGED" and p["allowed_pct"] == 0 and "acknowledge" in p["reason"]


def test_a_signed_off_adverse_change_allows_the_reduced_percentage(mod):
    ack = {"change_digest": mod._change_digest(TETHER_ADVERSE), "check_id": 2}
    for pct in (0, 25, 50, 100):
        p = _posture(mod, TETHER_ADVERSE, ack, pct=pct)
        assert p["posture"] == "ADVERSE_ACKNOWLEDGED" and p["allowed_pct"] == pct


def test_a_sign_off_of_other_wording_does_not_carry_over(mod):
    ack = {"change_digest": mod._change_digest(CIRCLE_CHANGED), "check_id": 1}      # a real sign-off, of another change
    assert _posture(mod, TETHER_ADVERSE, ack)["posture"] == "ADVERSE_UNACKNOWLEDGED"
    worse = copy.deepcopy(TETHER_ADVERSE)
    ack = {"change_digest": mod._change_digest(TETHER_ADVERSE), "check_id": 2}
    worse["facts"]["areas"]["redemption"]["excerpt_digest"] = "f" * 64              # the issuer changed the wording again
    assert _posture(mod, worse, ack)["posture"] == "ADVERSE_UNACKNOWLEDGED"


def test_a_sign_off_of_an_adverse_change_does_not_dim_a_later_clean_check(mod):
    ack = {"change_digest": mod._change_digest(TETHER_ADVERSE), "check_id": 2}
    assert _posture(mod, CIRCLE_CLEAR, ack)["posture"] == "CLEAR"
    assert _posture(mod, CIRCLE_CHANGED, ack)["posture"] == "CHANGED"


@pytest.mark.parametrize("check", [CIRCLE_CLEAR, CIRCLE_CHANGED, TETHER_ADVERSE])
def test_a_check_older_than_the_limit_is_stale_whatever_it_said(mod, check):
    p = _posture(mod, check, {"change_digest": mod._change_digest(check), "check_id": 1}, seconds_after=MAX_AGE + 1)
    assert p["posture"] == "STALE" and p["allowed_pct"] == 0 and str(MAX_AGE + 1) in p["reason"]


def test_the_limit_is_inclusive_and_a_check_from_the_future_is_stale(mod):
    assert _posture(mod, CIRCLE_CLEAR, seconds_after=MAX_AGE)["posture"] == "CLEAR"
    assert _posture(mod, CIRCLE_CLEAR, seconds_after=MAX_AGE + 1)["posture"] == "STALE"
    assert _posture(mod, CIRCLE_CLEAR, seconds_after=0)["posture"] == "CLEAR"
    assert _posture(mod, CIRCLE_CLEAR, seconds_after=-1)["posture"] == "STALE"


def test_an_undetermined_check_allows_nothing(mod):
    undetermined = dict(copy.deepcopy(CIRCLE_CLEAR), verdict="UNDETERMINED")
    p = _posture(mod, undetermined)
    assert p["posture"] == "UNDETERMINED" and p["allowed_pct"] == 0


def test_a_watch_with_no_check_allows_nothing(mod):
    p = mod._posture({"watch_id": "x", "verdict": "NONE"}, None, 10 ** 10, MAX_AGE, ACKED_PCT)
    assert p["posture"] == "NO_CHECK" and p["allowed_pct"] == 0


def test_a_verdict_this_radar_does_not_know_allows_nothing(mod):
    odd = dict(copy.deepcopy(CIRCLE_CLEAR), verdict="SOMETHING_NEW")
    assert _posture(mod, odd)["posture"] == "UNKNOWN_VERDICT" and _posture(mod, odd)["allowed_pct"] == 0


@pytest.mark.parametrize("cap, pct, allocated, limit, available", [
    (1_000_000, 100, 0, 1_000_000, 1_000_000),
    (1_000_000, 50, 400_000, 500_000, 100_000),
    (1_000_000, 50, 500_000, 500_000, 0),
    (1_000_000, 0, 0, 0, 0),
    (1_000_000, 50, 900_000, 500_000, 0),            # the limit shrank below what was already allocated: nothing, not negative
    (999_999, 50, 0, 499_999, 499_999),               # whole units: the cap's share rounds down
])
def test_what_is_left_to_allocate(mod, cap, pct, allocated, limit, available):
    assert mod._limit(cap, pct) == limit and mod._available(cap, pct, allocated) == available


# --- 3. The contract's own checks, before it reads TermsShift --------------------------------------------


def test_config_rules_and_empty_state(direct_vm, direct_deploy, direct_owner):
    radar = _deploy(direct_vm, direct_deploy, direct_owner)
    cfg = radar.get_config()
    assert cfg["shift_address"].lower() == SHIFT and (cfg["max_age_seconds"], cfg["acknowledged_pct"]) == (MAX_AGE, ACKED_PCT)
    assert (cfg["tracked_count"], cfg["acknowledgement_count"], cfg["allocation_count"]) == (0, 0, 0)
    rules = radar.get_rules()
    assert rules["ladder"] == {"CLEAR": 100, "CHANGED": 100, "ADVERSE_ACKNOWLEDGED": 50, "ADVERSE_UNACKNOWLEDGED": 0,
                               "UNDETERMINED": 0, "STALE": 0, "NO_CHECK": 0}
    assert radar.list_tracked() == [] and radar.get_acknowledgements(0, 10) == [] and radar.get_allocations(0, 10) == []
    assert radar.get_status("nope") == {"watch_id": "nope", "tracked": False}


@pytest.mark.parametrize("max_age, pct", [(0, 50), (3600, -1), (3600, 101)])
def test_invalid_configuration_is_rejected(direct_vm, direct_deploy, direct_owner, max_age, pct):
    with pytest.raises(Exception):
        _deploy(direct_vm, direct_deploy, direct_owner, max_age, pct)


def test_a_radar_can_be_configured_to_allow_nothing_after_an_adverse_change(direct_vm, direct_deploy, direct_owner):
    assert _deploy(direct_vm, direct_deploy, direct_owner, pct=0).get_rules()["ladder"]["ADVERSE_ACKNOWLEDGED"] == 0


def test_only_the_owner_can_track_acknowledge_or_allocate(direct_vm, direct_deploy, direct_owner, direct_alice):
    radar = _deploy(direct_vm, direct_deploy, direct_owner)
    direct_vm.sender = direct_alice
    with pytest.raises(Exception, match="only the owner can track an issuer"):
        radar.track("tether-since-2023", 1000)
    with pytest.raises(Exception, match="only the owner can acknowledge a change"):
        radar.acknowledge("tether-since-2023", "I have read the change and accept it.")
    with pytest.raises(Exception, match="only the owner can allocate"):
        radar.allocate("tether-since-2023", 100)


def test_a_zero_cap_and_a_zero_amount_are_rejected_before_any_cross_contract_call(direct_vm, direct_deploy, direct_owner):
    radar = _deploy(direct_vm, direct_deploy, direct_owner)
    with pytest.raises(Exception, match="cap must be positive"):
        radar.track("tether-since-2023", 0)
    with pytest.raises(Exception, match="amount must be positive"):
        radar.allocate("tether-since-2023", 0)


def test_an_issuer_that_is_not_tracked_cannot_be_acknowledged_or_allocated(direct_vm, direct_deploy, direct_owner):
    radar = _deploy(direct_vm, direct_deploy, direct_owner)
    with pytest.raises(Exception, match="not tracked"):
        radar.acknowledge("tether-since-2023", "I have read the change and accept it.")
    with pytest.raises(Exception, match="not tracked"):
        radar.allocate("tether-since-2023", 100)
