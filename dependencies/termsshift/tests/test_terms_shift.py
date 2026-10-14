"""
Deterministic tests for TermsShift using genlayer-test's Direct Mode.

Inputs are real Internet Archive captures of Circle's USDC Terms and
Tether's Terms of Service, pinned by timestamp and SHA-256 in
tests/fixtures/manifest.json. Run `python3 scripts/fetch_fixtures.py` once
first; the captures are byte-identical to what GenVM's own fetcher gets
(same SHA-256 - see research/README.md). The archive's response headers
(Memento-Datetime, Link rel="original") are served exactly as the archive
sends them.

Real changes are the test cases:
- Circle, Oct 2024 -> Dec 2025: watched clauses changed only by
  "blacklisting" becoming "blocklisting" (CHANGED_NOT_ADVERSE).
- Tether, Dec 2023 -> Feb 2026: redemption ended for EUR₮ and five USD₮
  chains, minimum redemption amounts added, reserves "may include loan
  receivables ... from Affiliates" (MATERIAL_ADVERSE_CHANGE).
- Circle, Oct 2026 capture -> live: every watched clause identical
  (UNCHANGED, decided without the LLM).

Four layers: registration (baseline provenance), verdicts, the reader's
limits (quotes, truncation, garbage), and the consensus boundary.
"""

import json
import pathlib
import re
import sys

import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text())["captures"]
NOW = "2026-10-04T12:00:00Z"

CIRCLE = "https://www.circle.com/legal/usdc-terms"
TETHER = "https://tether.to/en/legal/"
CIRCLE_2024, CIRCLE_2026 = "20241103153936", "20261002182005"
TETHER_2023 = "20240915223352"


def _capture(name: str) -> str:
    path = FIXTURES / "cache" / f"{name}.html"
    if not path.exists():
        pytest.fail("test captures missing - run: python3 scripts/fetch_fixtures.py")
    return path.read_bytes().decode("utf-8", "replace")


def _snapshot_url(ts: str, live: str) -> str:
    return f"https://web.archive.org/web/{ts}id_/{live}"


def _mock(direct_vm, url: str, body: str, status: int = 200, headers=None) -> None:
    # Anchored at BOTH ends: an archive URL ends with the live URL it
    # captured, so an unanchored pattern would serve one for the other.
    direct_vm.mock_web("^" + re.escape(url) + "$", {"method": "GET", "response": {
        "status": status,
        "headers": {k: v.encode("utf-8") for k, v in (headers or {}).items()},
        "body": body.encode("utf-8"),
    }})


def _serve_capture(direct_vm, ts: str, live: str, name: str, memento=None, original=None, status=200) -> None:
    m = MANIFEST[name]
    _mock(direct_vm, _snapshot_url(ts, live), _capture(name), status, {
        "memento-datetime": memento or m["memento_datetime"],
        "link": f'<{original or m["original"]}>; rel="original", <https://web.archive.org/web/timemap/link/{m["original"]}>; rel="timemap"',
    })


def _serve_live(direct_vm, live: str, body: str, status: int = 200) -> None:
    _mock(direct_vm, live, body, status)


def _reader(direct_vm, area: str, adverse, evidence=None) -> None:
    direct_vm.mock_llm(f"Clause area: {area} -", json.dumps({"adverse": adverse, "evidence": evidence}))


def _warp(direct_vm, timestamp: str) -> None:
    # genlayer-test 0.29.2's warp() never refreshes the datetime in the SDK's
    # already-imported gl.message_raw after deploy; set it too. Live GenVM
    # gives every call a fresh timestamp (confirmed on Studio Next).
    direct_vm.warp(timestamp)
    gl = sys.modules.get("genlayer.gl")
    if gl is not None and getattr(gl, "message_raw", None) is not None:
        gl.message_raw["datetime"] = timestamp


def _deploy(direct_vm, direct_deploy, direct_owner):
    direct_vm.warp(NOW)
    direct_vm.sender = direct_owner
    contract = direct_deploy("contracts/terms_shift.py")
    _warp(direct_vm, NOW)
    return contract


def _register(ts_contract, direct_vm, watch_id, live, ts, name, **capture_kw):
    direct_vm.clear_mocks()
    _serve_capture(direct_vm, ts, live, name, **capture_kw)
    ts_contract.register_watch(watch_id, live, ts, watch_id)


def _check(ts_contract, direct_vm, watch_id, live, ts, baseline_name, live_body, readers=(), live_status=200):
    # Only the live page is served: a check that touched the archive again
    # would fail on the missing mock. The baseline comes from registration.
    direct_vm.clear_mocks()
    _serve_live(direct_vm, live, live_body, live_status)
    for area, adverse, evidence in readers:
        _reader(direct_vm, area, adverse, evidence)
    ts_contract.check(watch_id)
    return ts_contract.latest_check(watch_id)


CIRCLE_NEUTRAL = [("redemption", False, None), ("freezing", False, None)]
TETHER_QUOTE = "Tether ceased to redeem"
TETHER_READERS = [
    ("redemption", True, TETHER_QUOTE),
    ("suspension", True, TETHER_QUOTE),
    ("reserves", True, "may include loan receivables and other assets from Affiliates"),
    ("freezing", False, None),
    ("fees", True, "subject to minimum redemption amounts and other requirements"),
    ("amendment", True, "may be amended, changed, or updated by Tether at any time"),
]


# --- 1. Registration: the baseline must provably be the right document ------


def test_register_pins_an_exact_capture_of_the_same_page(direct_vm, direct_deploy, direct_owner):
    ts = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(ts, direct_vm, "circle", CIRCLE, CIRCLE_2024, "circle_usdc_2024-11-03")
    w = ts.get_watch("circle")
    assert w["baseline_url"] == _snapshot_url(CIRCLE_2024, CIRCLE)
    assert w["baseline_last_updated"] == "October 4, 2024"
    assert w["baseline_area_sentences"] == {
        "amendment": 16, "fees": 29, "freezing": 6, "redemption": 60, "reserves": 23, "suspension": 30}
    assert len(w["baseline_digest"]) == 64
    assert ts.latest_verdict("circle") == "NONE"
    assert ts.is_safe("circle", 10**6) is False


def test_archive_original_without_www_still_matches(direct_vm, direct_deploy, direct_owner):
    # The 2024 capture is filed under https://circle.com/... (no www); the
    # live page is https://www.circle.com/... - the same page.
    ts = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(ts, direct_vm, "circle", CIRCLE, CIRCLE_2024, "circle_usdc_2024-11-03")
    assert ts.get_state()["watch_count"] == 1


def test_register_refuses_a_timestamp_that_is_not_an_exact_capture(direct_vm, direct_deploy, direct_owner):
    # The archive answers an inexact timestamp with its NEAREST capture -
    # a different document than the one asked for.
    ts = _deploy(direct_vm, direct_deploy, direct_owner)
    with pytest.raises(Exception, match="baseline_not_exact_capture"):
        _register(ts, direct_vm, "tether", TETHER, "20240915000000", "tether_legal_2024-09-15")
    assert ts.get_state()["watch_count"] == 0


def test_register_refuses_a_capture_of_another_page(direct_vm, direct_deploy, direct_owner):
    ts = _deploy(direct_vm, direct_deploy, direct_owner)
    with pytest.raises(Exception, match="baseline_is_another_page"):
        _register(ts, direct_vm, "tether", TETHER, TETHER_2023, "tether_legal_2024-09-15",
                  original="https://tether.to/en/some-other-page/")


def test_register_refuses_a_missing_capture(direct_vm, direct_deploy, direct_owner):
    ts = _deploy(direct_vm, direct_deploy, direct_owner)
    with pytest.raises(Exception, match="baseline_http_404"):
        _register(ts, direct_vm, "tether", TETHER, TETHER_2023, "tether_legal_2024-09-15", status=404)


@pytest.mark.parametrize("watch_id,live,ts_value,label,message", [
    ("", TETHER, TETHER_2023, "x", "watch_id must be"),
    ("has space", TETHER, TETHER_2023, "x", "watch_id must be"),
    ("t", "http://tether.to/en/legal/", TETHER_2023, "x", "live_url must be"),
    ("t", "https://tether.to/en/legal/?a=1", TETHER_2023, "x", "live_url must be"),
    ("t", "tether.to/en/legal/", TETHER_2023, "x", "live_url must be"),
    ("t", "https://localhost/terms", TETHER_2023, "x", "live_url must be"),
    ("t", TETHER, "2024091522335", "x", "baseline_timestamp must be"),
    ("t", TETHER, "2024-09-15", "x", "baseline_timestamp must be"),
    ("t", TETHER, TETHER_2023, "", "label must be"),
])
def test_register_rejects_malformed_input(direct_vm, direct_deploy, direct_owner, watch_id, live, ts_value, label,
                                          message):
    # Rejected by input validation itself - before anything is fetched.
    ts = _deploy(direct_vm, direct_deploy, direct_owner)
    direct_vm.clear_mocks()
    with pytest.raises(Exception, match=message):
        ts.register_watch(watch_id, live, ts_value, label)


def test_register_rejects_duplicates_and_check_rejects_unknown(direct_vm, direct_deploy, direct_owner):
    ts = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(ts, direct_vm, "circle", CIRCLE, CIRCLE_2024, "circle_usdc_2024-11-03")
    with pytest.raises(Exception):
        _register(ts, direct_vm, "circle", CIRCLE, CIRCLE_2026, "circle_usdc_2026-10-02")
    with pytest.raises(Exception):
        ts.check("nope")


# --- 2. Verdicts on real terms ---------------------------------------------


def test_unchanged_clauses_are_decided_without_the_llm(direct_vm, direct_deploy, direct_owner):
    ts = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(ts, direct_vm, "circle", CIRCLE, CIRCLE_2026, "circle_usdc_2026-10-02")
    c = _check(ts, direct_vm, "circle", CIRCLE, CIRCLE_2026, "circle_usdc_2026-10-02",
               _capture("circle_usdc_2026-10-02"))  # no reader mocks: calling the LLM would fail
    assert c["verdict"] == "UNCHANGED"
    assert set(c["labels"].values()) == {"UNCHANGED"}
    assert c["readings"] == {}
    assert ts.is_safe("circle", 3600) is True


def test_real_cosmetic_change_is_not_adverse(direct_vm, direct_deploy, direct_owner):
    # Circle, Oct 2024 -> Dec 2025. The page changed in dozens of places
    # (menus, footer, sanctions list); in the six watched areas, only
    # "blacklisting policy" became "blocklisting policy".
    ts = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(ts, direct_vm, "circle", CIRCLE, CIRCLE_2024, "circle_usdc_2024-11-03")
    c = _check(ts, direct_vm, "circle", CIRCLE, CIRCLE_2024, "circle_usdc_2024-11-03",
               _capture("circle_usdc_2026-10-02"), CIRCLE_NEUTRAL)
    areas = c["facts"]["areas"]
    assert {n for n, a in areas.items() if a["status"] == "CHANGED"} == {"redemption", "freezing"}
    assert "blacklisting policy" in areas["freezing"]["old_preview"]
    assert "blocklisting policy" in areas["freezing"]["new_preview"]
    assert c["facts"]["baseline_last_updated"] == "October 4, 2024"
    assert c["facts"]["live_last_updated"] == "December 12, 2025"
    assert c["verdict"] == "CHANGED_NOT_ADVERSE"
    assert c["labels"]["redemption"] == "NEUTRAL" and c["labels"]["reserves"] == "UNCHANGED"
    assert ts.is_safe("circle", 3600) is True


def test_real_adverse_change_is_material(direct_vm, direct_deploy, direct_owner):
    # Tether, Dec 2023 -> Feb 2026.
    ts = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(ts, direct_vm, "tether", TETHER, TETHER_2023, "tether_legal_2024-09-15")
    c = _check(ts, direct_vm, "tether", TETHER, TETHER_2023, "tether_legal_2024-09-15",
               _capture("tether_legal_2026-03-06"), TETHER_READERS)
    assert c["verdict"] == "MATERIAL_ADVERSE_CHANGE"
    assert c["labels"]["redemption"] == "ADVERSE"
    assert c["labels"]["reserves"] == "ADVERSE"
    assert c["readings"]["redemption"]["evidence"] == TETHER_QUOTE
    assert c["readings"]["redemption"]["grounded"] is True
    assert c["facts"]["live_last_updated"] == "February 26, 2026"
    assert ts.is_safe("tether", 10**6) is False


def test_removed_clause_area_is_adverse_without_the_llm(direct_vm, direct_deploy, direct_owner):
    # The real Dec 2025 Circle page with every paragraph about blocking or
    # freezing cut out: a watched area with all its sentences gone is
    # adverse by construction - the reader is never asked about it.
    ts = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(ts, direct_vm, "circle", CIRCLE, CIRCLE_2026, "circle_usdc_2026-10-02")

    def drop(m):
        return "" if re.search(r"block\s?list|freez|frozen", re.sub(r"<[^>]+>", " ", m.group(0)), re.I) else m.group(0)

    live, n = re.subn(r"<p\b[^>]*>.*?</p>", drop, _capture("circle_usdc_2026-10-02"), flags=re.S | re.I)
    # Those paragraphs also mention redemption and reserves, so those areas
    # changed too and are read normally (here: not adverse).
    c = _check(ts, direct_vm, "circle", CIRCLE, CIRCLE_2026, "circle_usdc_2026-10-02", live,
               [("redemption", False, None), ("reserves", False, None)])
    assert c["labels"]["freezing"] == "REMOVED"
    assert "freezing" not in c["readings"]
    assert c["verdict"] == "MATERIAL_ADVERSE_CHANGE"
    assert c["reasons"] == ["adverse:freezing"]


def test_unreachable_live_page_is_undetermined(direct_vm, direct_deploy, direct_owner):
    ts = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(ts, direct_vm, "circle", CIRCLE, CIRCLE_2026, "circle_usdc_2026-10-02")
    c = _check(ts, direct_vm, "circle", CIRCLE, CIRCLE_2026, "circle_usdc_2026-10-02", "blocked", live_status=403)
    assert c["verdict"] == "UNDETERMINED"
    assert c["reasons"] == ["live_http_403"]
    assert ts.is_safe("circle", 10**6) is False


def test_block_page_served_with_200_is_undetermined_not_removed(direct_vm, direct_deploy, direct_owner):
    # A challenge page has none of the clauses - that's "couldn't read the
    # terms", not "every clause was deleted".
    ts = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(ts, direct_vm, "circle", CIRCLE, CIRCLE_2026, "circle_usdc_2026-10-02")
    block = "<html><body><p>Checking your browser before accessing circle.com. This process is automatic.</p></body></html>"
    c = _check(ts, direct_vm, "circle", CIRCLE, CIRCLE_2026, "circle_usdc_2026-10-02", block)
    assert c["verdict"] == "UNDETERMINED"
    assert c["reasons"] == ["live_page_incomplete"]


def test_network_failure_on_the_live_page_records_nothing(direct_vm, direct_deploy, direct_owner):
    # A connection-level failure (here: nothing answering at all) is retried,
    # then fails the transaction - no half-read verdict is stored.
    ts = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(ts, direct_vm, "circle", CIRCLE, CIRCLE_2026, "circle_usdc_2026-10-02")
    direct_vm.clear_mocks()
    with pytest.raises(Exception):
        ts.check("circle")
    assert ts.get_state()["check_count"] == 0
    assert ts.latest_verdict("circle") == "NONE"


def test_baseline_clauses_are_stored_at_registration(direct_vm, direct_deploy, direct_owner):
    ts = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(ts, direct_vm, "tether", TETHER, TETHER_2023, "tether_legal_2024-09-15")
    w = ts.get_watch("tether")
    assert w["baseline_last_updated"] == "December 7, 2023"
    assert w["baseline_area_sentences"]["redemption"] == 28


# --- 3. The reader's limits --------------------------------------------------


def test_adverse_claim_without_a_real_quote_is_not_published(direct_vm, direct_deploy, direct_owner):
    ts = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(ts, direct_vm, "circle", CIRCLE, CIRCLE_2024, "circle_usdc_2024-11-03")
    c = _check(ts, direct_vm, "circle", CIRCLE, CIRCLE_2024, "circle_usdc_2024-11-03",
               _capture("circle_usdc_2026-10-02"),
               [("redemption", True, "Circle may suspend all redemptions indefinitely"), ("freezing", False, None)])
    assert c["readings"]["redemption"]["grounded"] is False
    assert c["labels"]["redemption"] == "UNDETERMINED"
    assert c["verdict"] == "UNDETERMINED"


def test_stitched_quote_of_genuine_fragments_is_grounded(direct_vm, direct_deploy, direct_owner):
    # What the live reader actually returned for Tether: real sentences,
    # joined, one of them elided with "...". Every fragment is verbatim.
    ts = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(ts, direct_vm, "tether", TETHER, TETHER_2023, "tether_legal_2024-09-15")
    stitched = "make redemptions of Tether Tokens through the Site. ... Tether ceased to redeem"
    c = _check(ts, direct_vm, "tether", TETHER, TETHER_2023, "tether_legal_2024-09-15",
               _capture("tether_legal_2026-03-06"), [("redemption", True, stitched)] +
               [(a, False, None) for a, _, _ in TETHER_READERS[1:]])
    assert c["readings"]["redemption"]["grounded"] is True
    assert c["labels"]["redemption"] == "ADVERSE"


def test_stitched_quote_with_one_invented_fragment_is_not_grounded(direct_vm, direct_deploy, direct_owner):
    ts = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(ts, direct_vm, "tether", TETHER, TETHER_2023, "tether_legal_2024-09-15")
    stitched = ("As previously announced, Tether ceased to redeem. ... Tether may also seize reserves without "
                "notice to holders.")
    c = _check(ts, direct_vm, "tether", TETHER, TETHER_2023, "tether_legal_2024-09-15",
               _capture("tether_legal_2026-03-06"), [("redemption", True, stitched)] +
               [(a, False, None) for a, _, _ in TETHER_READERS[1:]])
    assert c["readings"]["redemption"]["grounded"] is False
    assert c["labels"]["redemption"] == "UNDETERMINED"


def test_not_adverse_on_a_truncated_change_is_never_accepted(direct_vm, direct_deploy, direct_owner):
    # Tether's rewrite is longer than one reader call shows. "Nothing
    # adverse in what I saw" isn't "nothing adverse".
    ts = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(ts, direct_vm, "tether", TETHER, TETHER_2023, "tether_legal_2024-09-15")
    c = _check(ts, direct_vm, "tether", TETHER, TETHER_2023, "tether_legal_2024-09-15",
               _capture("tether_legal_2026-03-06"), [(a, False, None) for a, _, _ in TETHER_READERS])
    assert c["facts"]["areas"]["redemption"]["truncated"] is True
    assert c["facts"]["areas"]["freezing"]["truncated"] is False
    assert c["labels"]["redemption"] == "UNDETERMINED"
    assert c["labels"]["freezing"] == "NEUTRAL"
    assert c["verdict"] == "UNDETERMINED"


def test_one_adverse_area_outranks_areas_that_stay_undetermined(direct_vm, direct_deploy, direct_owner):
    # Tether: the reader finds the redemption change adverse, and calls the
    # other truncated areas "not adverse" - which can't be accepted, so they
    # stay UNDETERMINED. One confirmed adverse change is still decisive.
    ts = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(ts, direct_vm, "tether", TETHER, TETHER_2023, "tether_legal_2024-09-15")
    readers = [("redemption", True, TETHER_QUOTE)] + [(a, False, None) for a, _, _ in TETHER_READERS[1:]]
    c = _check(ts, direct_vm, "tether", TETHER, TETHER_2023, "tether_legal_2024-09-15",
               _capture("tether_legal_2026-03-06"), readers)
    assert c["labels"]["redemption"] == "ADVERSE"
    assert c["labels"]["reserves"] == "UNDETERMINED"
    assert c["verdict"] == "MATERIAL_ADVERSE_CHANGE"
    assert c["reasons"][0] == "adverse:redemption"
    assert "undetermined:reserves" in c["reasons"]


def test_unreadable_llm_answer_is_undetermined_not_neutral(direct_vm, direct_deploy, direct_owner):
    ts = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(ts, direct_vm, "circle", CIRCLE, CIRCLE_2024, "circle_usdc_2024-11-03")
    direct_vm.clear_mocks()
    _serve_live(direct_vm, CIRCLE, _capture("circle_usdc_2026-10-02"))
    direct_vm.mock_llm("Clause area: redemption -", json.dumps({"adverse": "no"}))
    _reader(direct_vm, "freezing", False)
    ts.check("circle")
    c = ts.latest_check("circle")
    assert c["readings"]["redemption"] is None
    assert c["labels"]["redemption"] == "UNDETERMINED"
    assert c["verdict"] == "UNDETERMINED"


def test_is_safe_requires_freshness_and_latest_check_wins(direct_vm, direct_deploy, direct_owner):
    ts = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(ts, direct_vm, "circle", CIRCLE, CIRCLE_2026, "circle_usdc_2026-10-02")
    _check(ts, direct_vm, "circle", CIRCLE, CIRCLE_2026, "circle_usdc_2026-10-02", _capture("circle_usdc_2026-10-02"))
    _warp(direct_vm, "2026-10-04T12:59:59Z")
    assert ts.is_safe("circle", 3600) is True
    _warp(direct_vm, "2026-10-04T13:00:01Z")
    assert ts.is_safe("circle", 3600) is False
    assert ts.is_safe("circle", 7200) is True
    _check(ts, direct_vm, "circle", CIRCLE, CIRCLE_2026, "circle_usdc_2026-10-02", "x", live_status=500)
    assert ts.latest_verdict("circle") == "UNDETERMINED"
    assert ts.is_safe("circle", 10**6) is False
    assert [c["verdict"] for c in ts.get_checks(0, 10)] == ["UNDETERMINED", "UNCHANGED"]
    assert ts.get_watch("circle")["check_count"] == 2


# --- 4. Consensus boundary ---------------------------------------------------


def test_registration_validator_requires_the_exact_same_baseline(direct_vm, direct_deploy, direct_owner):
    ts = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(ts, direct_vm, "circle", CIRCLE, CIRCLE_2024, "circle_usdc_2024-11-03")
    assert direct_vm.run_validator() is True
    leader = _leader(direct_vm)
    leader["baseline"]["sentences"][0] = "Circle may suspend redemptions at its discretion."
    assert direct_vm.run_validator(leader_result=json.dumps(leader)) is False
    leader = _leader(direct_vm)
    leader["capture"] = "20241103000000"
    assert direct_vm.run_validator(leader_result=json.dumps(leader)) is False
    assert direct_vm.run_validator(leader_result="[]") is False


def _leader(direct_vm):
    """The leader result the last check() actually produced."""
    stored, _leader_fn, _validator_fn = direct_vm._captured_validators[-1]
    return json.loads(stored)


def test_validator_accepts_an_honest_leader(direct_vm, direct_deploy, direct_owner):
    ts = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(ts, direct_vm, "tether", TETHER, TETHER_2023, "tether_legal_2024-09-15")
    _check(ts, direct_vm, "tether", TETHER, TETHER_2023, "tether_legal_2024-09-15",
           _capture("tether_legal_2026-03-06"), TETHER_READERS)
    assert direct_vm.run_validator() is True


def test_validator_rejects_leader_hiding_an_adverse_change(direct_vm, direct_deploy, direct_owner):
    ts = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(ts, direct_vm, "tether", TETHER, TETHER_2023, "tether_legal_2024-09-15")
    _check(ts, direct_vm, "tether", TETHER, TETHER_2023, "tether_legal_2024-09-15",
           _capture("tether_legal_2026-03-06"), TETHER_READERS)
    leader = _leader(direct_vm)
    for name in leader["readings"]:
        leader["readings"][name] = {"adverse": False, "evidence": None, "grounded": False}
    assert direct_vm.run_validator(leader_result=json.dumps(leader)) is False


def test_validator_rejects_a_quote_not_in_its_own_copy(direct_vm, direct_deploy, direct_owner):
    ts = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(ts, direct_vm, "tether", TETHER, TETHER_2023, "tether_legal_2024-09-15")
    _check(ts, direct_vm, "tether", TETHER, TETHER_2023, "tether_legal_2024-09-15",
           _capture("tether_legal_2026-03-06"), TETHER_READERS)
    leader = _leader(direct_vm)
    leader["readings"]["redemption"] = {"adverse": True, "evidence": "Tether may confiscate all reserves at will",
                                        "grounded": True}
    assert direct_vm.run_validator(leader_result=json.dumps(leader)) is False


def test_validator_rejects_an_adverse_finding_its_own_reader_does_not_share(direct_vm, direct_deploy, direct_owner):
    # Circle's rename, called adverse by the leader with a real quote: the
    # quote is genuine, but this validator's reader sees nothing adverse.
    ts = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(ts, direct_vm, "circle", CIRCLE, CIRCLE_2024, "circle_usdc_2024-11-03")
    _check(ts, direct_vm, "circle", CIRCLE, CIRCLE_2024, "circle_usdc_2024-11-03",
           _capture("circle_usdc_2026-10-02"), CIRCLE_NEUTRAL)
    leader = _leader(direct_vm)
    leader["readings"]["freezing"] = {"adverse": True, "evidence": "as permitted under the blocklisting policy",
                                      "grounded": True}
    assert direct_vm.run_validator(leader_result=json.dumps(leader)) is False


def test_validator_confirms_each_adverse_area_not_just_the_verdict(direct_vm, direct_deploy, direct_owner):
    # Same overall verdict (Tether is adverse either way), but the leader
    # also calls the freezing change adverse - with a genuine quote - while
    # this validator's reader finds freezing not adverse. Every adverse
    # label on the record must be one every validator's reader shares.
    ts = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(ts, direct_vm, "tether", TETHER, TETHER_2023, "tether_legal_2024-09-15")
    c = _check(ts, direct_vm, "tether", TETHER, TETHER_2023, "tether_legal_2024-09-15",
               _capture("tether_legal_2026-03-06"), TETHER_READERS)
    assert c["labels"]["freezing"] == "NEUTRAL"
    leader = _leader(direct_vm)
    real_quote = leader["facts"]["areas"]["freezing"]["new_preview"][:60]
    leader["readings"]["freezing"] = {"adverse": True, "evidence": real_quote, "grounded": True}
    assert direct_vm.run_validator(leader_result=json.dumps(leader)) is False


def test_validator_rejects_a_missing_reading_even_when_the_verdict_survives(direct_vm, direct_deploy, direct_owner):
    ts = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(ts, direct_vm, "tether", TETHER, TETHER_2023, "tether_legal_2024-09-15")
    _check(ts, direct_vm, "tether", TETHER, TETHER_2023, "tether_legal_2024-09-15",
           _capture("tether_legal_2026-03-06"), TETHER_READERS)
    leader = _leader(direct_vm)
    del leader["readings"]["freezing"]  # still MATERIAL_ADVERSE_CHANGE without it
    assert direct_vm.run_validator(leader_result=json.dumps(leader)) is False


def test_validator_rejects_tampered_facts(direct_vm, direct_deploy, direct_owner):
    ts = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(ts, direct_vm, "tether", TETHER, TETHER_2023, "tether_legal_2024-09-15")
    _check(ts, direct_vm, "tether", TETHER, TETHER_2023, "tether_legal_2024-09-15",
           _capture("tether_legal_2026-03-06"), TETHER_READERS)
    leader = _leader(direct_vm)
    leader["facts"]["areas"]["redemption"]["status"] = "UNCHANGED"
    assert direct_vm.run_validator(leader_result=json.dumps(leader)) is False
    leader = _leader(direct_vm)
    leader["facts_digest"] = "0" * 64
    assert direct_vm.run_validator(leader_result=json.dumps(leader)) is False


def test_validator_rejects_malformed_or_misaligned_readings(direct_vm, direct_deploy, direct_owner):
    ts = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(ts, direct_vm, "circle", CIRCLE, CIRCLE_2024, "circle_usdc_2024-11-03")
    _check(ts, direct_vm, "circle", CIRCLE, CIRCLE_2024, "circle_usdc_2024-11-03",
           _capture("circle_usdc_2026-10-02"), CIRCLE_NEUTRAL)
    leader = _leader(direct_vm)
    del leader["readings"]["freezing"]
    assert direct_vm.run_validator(leader_result=json.dumps(leader)) is False
    leader = _leader(direct_vm)
    leader["readings"]["freezing"] = {"adverse": "no"}
    assert direct_vm.run_validator(leader_result=json.dumps(leader)) is False
    leader = _leader(direct_vm)
    leader["readings"]["freezing"] = {"adverse": False, "evidence": "smuggled text", "grounded": False}
    assert direct_vm.run_validator(leader_result=json.dumps(leader)) is False
    assert direct_vm.run_validator(leader_error=Exception("fetch failed")) is False
    assert direct_vm.run_validator(leader_result="not json") is False
