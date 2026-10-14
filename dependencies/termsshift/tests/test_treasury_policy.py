"""
Direct Mode tests for TreasuryPolicy.

Direct Mode can't simulate cross-contract calls without a "glsim" hook (the
same documented limitation as this account's earlier consumers, ListingGate
and RetainerConsumer), so allocate()'s read of TermsShift.is_safe() is
proven live instead - an allowed allocation and a reverted one, both linked
in CONTRACT.md. What's tested here is everything that runs before that call.
"""

import pytest

TS_ADDRESS = "0x" + "22" * 20  # never actually called in these tests


def _deploy(direct_vm, direct_deploy, owner, max_age=3600):
    direct_vm.sender = owner
    return direct_deploy("contracts/treasury_policy.py", TS_ADDRESS, max_age)


def test_config_and_empty_state(direct_vm, direct_deploy, direct_owner):
    tp = _deploy(direct_vm, direct_deploy, direct_owner)
    cfg = tp.get_config()
    assert cfg["max_age_seconds"] == 3600
    assert cfg["allocation_count"] == 0
    assert cfg["termsshift_address"].lower() == TS_ADDRESS
    assert tp.total_for("circle") == 0
    assert tp.get_allocations(0, 10) == []


def test_zero_max_age_is_rejected(direct_vm, direct_deploy, direct_owner):
    with pytest.raises(Exception):
        _deploy(direct_vm, direct_deploy, direct_owner, max_age=0)


def test_only_the_owner_can_allocate(direct_vm, direct_deploy, direct_owner, direct_alice):
    tp = _deploy(direct_vm, direct_deploy, direct_owner)
    direct_vm.sender = direct_alice
    with pytest.raises(Exception, match="only the treasury owner"):
        tp.allocate("circle", 100)


def test_zero_amount_is_rejected_before_any_cross_contract_call(direct_vm, direct_deploy, direct_owner):
    tp = _deploy(direct_vm, direct_deploy, direct_owner)
    with pytest.raises(Exception, match="amount must be positive"):
        tp.allocate("circle", 0)


def test_allocate_reaches_termsshift_which_direct_mode_cannot_simulate(direct_vm, direct_deploy, direct_owner):
    # Documented, not silently skipped: a valid allocate() call goes on to
    # gl.get_contract_at(...).view().is_safe(...), which needs glsim.
    tp = _deploy(direct_vm, direct_deploy, direct_owner)
    with pytest.raises(Exception):
        tp.allocate("circle", 100)
    assert tp.get_config()["allocation_count"] == 0
