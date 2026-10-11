# v0.1.0
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

# TermsRadar - a treasury control over stablecoin issuers' terms, built on
# TermsShift's verdicts. TermsShift says whether an issuer's live terms have
# changed against holders since a baseline; TermsRadar turns that into a rule a
# treasury can run on-chain, and puts a person in the loop where it matters:
#
#   - Each tracked issuer has an allocation cap. What may be allocated against
#     it is that cap times a percentage that depends on TermsShift's latest
#     check: 100% while its terms are unchanged or changed but read in full as
#     not adverse; 0% while the check is missing, stale or undetermined.
#   - After a MATERIAL_ADVERSE_CHANGE the percentage is 0% until the treasury's
#     owner has read the change and signed it off on-chain with a note
#     (`acknowledge`), and then a reduced percentage (set at deployment).
#   - A sign-off is bound to the exact wording that changed: it records a digest
#     of which areas changed and of the changed wording, as TermsShift's
#     validators agreed it. A later check that finds the same change keeps the
#     sign-off; one that finds different wording does not, and needs a new one.
#
# Every rule is a pure function of TermsShift's own check record, so it is
# tested on the real checks; the cross-contract reads are proven live.
#
# GenVM v0.2.11 conventions (locally tested source of truth);
# contracts/terms_radar_studio_next.py is the deployed port.
# Header must end in a blank line (real GenVM v0.2.11 requirement).

from genlayer import *
import datetime
import hashlib
import json
import re

ADVERSE = "MATERIAL_ADVERSE_CHANGE"
ACKNOWLEDGEABLE = ("CHANGED_NOT_ADVERSE", "MATERIAL_ADVERSE_CHANGE")
MIN_NOTE_LEN = 20
MAX_NOTE_LEN = 400
MAX_PAGE_LIMIT = 50


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise gl.vm.UserError(message)


def _now() -> datetime.datetime:
    return datetime.datetime.fromisoformat(gl.message_raw['datetime'])


def _seconds(iso: str) -> int:
    return int(datetime.datetime.fromisoformat(iso).timestamp())


def _change_digest(check: dict) -> str:
    """What changed, exactly as TermsShift's validators agreed it: for every area that is not
    UNCHANGED, its status and the digest of the changed wording."""
    areas = (check.get("facts") or {}).get("areas") or {}
    changed = {name: [a.get("status"), a.get("excerpt_digest", "")] for name, a in areas.items()
               if a.get("status") != "UNCHANGED"}
    return hashlib.sha256(json.dumps(changed, sort_keys=True).encode()).hexdigest()


def _posture(check: dict, ack, now_seconds: int, max_age: int, acknowledged_pct: int) -> dict:
    """The control's reading of TermsShift's latest check: {posture, allowed_pct, reason}.
    `ack` is None or the latest sign-off for this watch: {"change_digest": ...}."""
    verdict = check.get("verdict", "NONE")
    if verdict == "NONE":
        return {"posture": "NO_CHECK", "allowed_pct": 0, "reason": "TermsShift has no check of this issuer"}
    age = now_seconds - _seconds(check["checked_at"])
    if not 0 <= age <= max_age:
        return {"posture": "STALE", "allowed_pct": 0,
                "reason": f"the latest check is {age} seconds old; this radar wants at most {max_age}"}
    if verdict == "UNDETERMINED":
        return {"posture": "UNDETERMINED", "allowed_pct": 0, "reason": "the latest check could not settle every area"}
    if verdict == "UNCHANGED":
        return {"posture": "CLEAR", "allowed_pct": 100, "reason": "the issuer's terms are unchanged since the baseline"}
    if verdict == "CHANGED_NOT_ADVERSE":
        return {"posture": "CHANGED", "allowed_pct": 100,
                "reason": "the terms changed, and every change was read in full and judged not adverse to holders"}
    if verdict == ADVERSE:
        if ack is not None and ack["change_digest"] == _change_digest(check):
            return {"posture": "ADVERSE_ACKNOWLEDGED", "allowed_pct": acknowledged_pct,
                    "reason": "a material adverse change, signed off on-chain by the owner"}
        return {"posture": "ADVERSE_UNACKNOWLEDGED", "allowed_pct": 0,
                "reason": "a material adverse change nobody has signed off: read it, then acknowledge it"}
    return {"posture": "UNKNOWN_VERDICT", "allowed_pct": 0, "reason": f"unrecognised verdict {verdict}"}


def _limit(cap: int, allowed_pct: int) -> int:
    return cap * allowed_pct // 100


def _available(cap: int, allowed_pct: int, allocated: int) -> int:
    return max(_limit(cap, allowed_pct) - allocated, 0)


@allow_storage
class Tracked:
    label: str
    cap: u256
    allocated: u256
    tracked_by: Address
    tracked_at: datetime.datetime
    has_ack: bool
    latest_ack_id: u32  # meaningful only when has_ack


@allow_storage
class Ack:
    watch_id: str
    check_id: u32
    verdict: str
    change_digest: str
    note: str
    acknowledged_by: Address
    acknowledged_at: datetime.datetime


@allow_storage
class Allocation:
    watch_id: str
    amount: u256
    posture: str
    allowed_pct: u32
    check_id: u32
    allocated_by: Address
    allocated_at: datetime.datetime


def _ack_dict(ack_id: int, a: Ack) -> dict:
    return {"ack_id": ack_id, "watch_id": a.watch_id, "check_id": a.check_id, "verdict": a.verdict,
            "change_digest": a.change_digest, "note": a.note, "acknowledged_by": a.acknowledged_by.as_hex,
            "acknowledged_at": a.acknowledged_at.isoformat()}


class TermsRadar(gl.Contract):
    owner: Address
    shift_address: Address
    max_age_seconds: u32
    acknowledged_pct: u32
    tracked: TreeMap[str, Tracked]
    acks: DynArray[Ack]
    allocations: DynArray[Allocation]

    def __init__(self, shift_address: str, max_age_seconds: u32, acknowledged_pct: u32) -> None:
        _require(max_age_seconds > 0, "max_age_seconds must be positive")
        _require(0 <= acknowledged_pct <= 100, "acknowledged_pct must be between 0 and 100")
        self.owner = gl.message.sender_address
        self.shift_address = Address(shift_address)
        self.max_age_seconds = max_age_seconds
        self.acknowledged_pct = acknowledged_pct

    def _latest_check(self, watch_id: str) -> dict:
        return gl.get_contract_at(self.shift_address).view().latest_check(watch_id)

    def _ack_for(self, t: Tracked):
        if not t.has_ack:
            return None
        a = self.acks[t.latest_ack_id]
        return {"change_digest": a.change_digest, "check_id": int(a.check_id)}

    # Owner only: which of TermsShift's watches this radar covers, and the most that may be allocated against it.
    @gl.public.write
    def track(self, watch_id: str, cap: u256) -> None:
        _require(gl.message.sender_address == self.owner, "only the owner can track an issuer")
        _require(cap > 0, "cap must be positive")
        _require(watch_id not in self.tracked, "already tracked")
        watches = gl.get_contract_at(self.shift_address).view().list_watches()
        found = [w for w in watches if w["watch_id"] == watch_id]
        _require(len(found) == 1, f"{watch_id!r} refused: TermsShift has no such watch")
        t = self.tracked.get_or_insert_default(watch_id)
        t.label = found[0]["label"]
        t.cap = cap
        t.allocated = u256(0)
        t.tracked_by = gl.message.sender_address
        t.tracked_at = _now()
        t.has_ack = False
        t.latest_ack_id = u32(0)

    # Owner only: "I have read what changed, and accept it." The sign-off is bound to the wording
    # that changed: a later check that finds a different change needs a new one.
    @gl.public.write
    def acknowledge(self, watch_id: str, note: str) -> None:
        _require(gl.message.sender_address == self.owner, "only the owner can acknowledge a change")
        _require(watch_id in self.tracked, "not tracked")
        _require(MIN_NOTE_LEN <= len(note.strip()) <= MAX_NOTE_LEN,
                 f"the note must say what was decided, {MIN_NOTE_LEN}-{MAX_NOTE_LEN} characters")
        check = self._latest_check(watch_id)
        _require(check["verdict"] in ACKNOWLEDGEABLE,
                 f"nothing to acknowledge: TermsShift's latest check of {watch_id!r} is {check['verdict']}")
        t = self.tracked[watch_id]
        a = self.acks.append_new_get()
        a.watch_id = watch_id
        a.check_id = u32(check["check_id"])
        a.verdict = check["verdict"]
        a.change_digest = _change_digest(check)
        a.note = note.strip()
        a.acknowledged_by = gl.message.sender_address
        a.acknowledged_at = _now()
        t.has_ack = True
        t.latest_ack_id = u32(len(self.acks) - 1)

    # Owner only. The latest check is read right now, so a stale or worsened issuer is refused.
    @gl.public.write
    def allocate(self, watch_id: str, amount: u256) -> None:
        _require(gl.message.sender_address == self.owner, "only the owner can allocate")
        _require(amount > 0, "amount must be positive")
        _require(watch_id in self.tracked, "not tracked")
        t = self.tracked[watch_id]
        check = self._latest_check(watch_id)
        p = _posture(check, self._ack_for(t), int(_now().timestamp()), self.max_age_seconds, self.acknowledged_pct)
        _require(p["allowed_pct"] > 0, f"{watch_id!r} refused: {p['posture']} - {p['reason']}")
        available = _available(int(t.cap), p["allowed_pct"], int(t.allocated))
        _require(int(amount) <= available,
                 f"{watch_id!r} refused: {p['posture']} allows {p['allowed_pct']}% of the cap {t.cap}, "
                 f"of which {available} is left")
        rec = self.allocations.append_new_get()
        rec.watch_id = watch_id
        rec.amount = amount
        rec.posture = p["posture"]
        rec.allowed_pct = u32(p["allowed_pct"])
        rec.check_id = u32(check["check_id"])
        rec.allocated_by = gl.message.sender_address
        rec.allocated_at = _now()
        t.allocated = u256(int(t.allocated) + int(amount))

    # --- Views -----------------------------------------------------------------

    # The control's answer, from TermsShift's latest check and this radar's sign-offs, as of right now.
    @gl.public.view
    def get_status(self, watch_id: str) -> dict:
        if watch_id not in self.tracked:
            return {"watch_id": watch_id, "tracked": False}
        t = self.tracked[watch_id]
        check = self._latest_check(watch_id)
        ack = self._ack_for(t)
        now = int(_now().timestamp())
        p = _posture(check, ack, now, self.max_age_seconds, self.acknowledged_pct)
        cap, allocated = int(t.cap), int(t.allocated)
        out = {"watch_id": watch_id, "tracked": True, "label": t.label, "posture": p["posture"],
               "allowed_pct": p["allowed_pct"], "reason": p["reason"], "cap": str(cap), "allocated": str(allocated),
               "limit": str(_limit(cap, p["allowed_pct"])), "available": str(_available(cap, p["allowed_pct"], allocated)),
               "check_id": check.get("check_id"), "verdict": check["verdict"], "checked_at": check.get("checked_at", ""),
               "age_seconds": (now - _seconds(check["checked_at"])) if "checked_at" in check else None,
               "acknowledgement": None}
        if t.has_ack:
            a = self.acks[t.latest_ack_id]
            out["acknowledgement"] = dict(_ack_dict(int(t.latest_ack_id), a),
                                          current=check["verdict"] == ADVERSE and a.change_digest == _change_digest(check))
        return out

    @gl.public.view
    def list_tracked(self) -> list:
        return [{"watch_id": k, "label": t.label, "cap": str(t.cap), "allocated": str(t.allocated), "has_ack": t.has_ack}
                for k, t in self.tracked.items()]

    @gl.public.view
    def get_acknowledgements(self, offset: u32, limit: u32) -> list:
        limit = min(limit, MAX_PAGE_LIMIT)
        out = []
        i = len(self.acks) - 1 - offset
        while i >= 0 and len(out) < limit:
            out.append(_ack_dict(i, self.acks[i]))
            i -= 1
        return out

    @gl.public.view
    def get_allocations(self, offset: u32, limit: u32) -> list:
        limit = min(limit, MAX_PAGE_LIMIT)
        out = []
        i = len(self.allocations) - 1 - offset
        while i >= 0 and len(out) < limit:
            a = self.allocations[i]
            out.append({"allocation_id": i, "watch_id": a.watch_id, "amount": str(a.amount), "posture": a.posture,
                        "allowed_pct": a.allowed_pct, "check_id": a.check_id, "allocated_by": a.allocated_by.as_hex,
                        "allocated_at": a.allocated_at.isoformat()})
            i -= 1
        return out

    @gl.public.view
    def get_config(self) -> dict:
        return {"owner": self.owner.as_hex, "shift_address": self.shift_address.as_hex,
                "max_age_seconds": self.max_age_seconds, "acknowledged_pct": self.acknowledged_pct,
                "tracked_count": len(self.tracked), "acknowledgement_count": len(self.acks),
                "allocation_count": len(self.allocations)}

    @gl.public.view
    def get_rules(self) -> dict:
        return {"max_age_seconds": self.max_age_seconds,
                "ladder": {"CLEAR": 100, "CHANGED": 100, "ADVERSE_ACKNOWLEDGED": self.acknowledged_pct,
                           "ADVERSE_UNACKNOWLEDGED": 0, "UNDETERMINED": 0, "STALE": 0, "NO_CHECK": 0},
                "min_note_length": MIN_NOTE_LEN}
