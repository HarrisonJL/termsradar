# v0.1.0
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

# TreasuryPolicy - a minimal consumer of TermsShift, proving the verdict can
# drive an action on-chain: a treasury's allocation to a stablecoin or
# custodian is only recorded if TermsShift's latest check of that issuer's
# terms is UNCHANGED or CHANGED_NOT_ADVERSE, and no older than this
# policy's max_age_seconds. Anything else - a material adverse change, an
# undetermined check, no check at all, or a stale one - reverts.
#
# GenVM v0.2.11 conventions (locally tested source of truth);
# contracts/treasury_policy_studio_next.py is the deployed port.
# Header must end in a blank line (real GenVM v0.2.11 requirement).

from genlayer import *
import datetime
import json

MAX_PAGE_LIMIT = 50


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise gl.vm.UserError(message)


def _now() -> datetime.datetime:
    return datetime.datetime.fromisoformat(gl.message_raw['datetime'])


@allow_storage
class Allocation:
    watch_id: str
    amount: u256
    recorded_by: Address
    recorded_at: datetime.datetime


class TreasuryPolicy(gl.Contract):
    owner: Address
    termsshift_address: Address
    max_age_seconds: u32
    allocations: DynArray[Allocation]
    totals: TreeMap[str, u256]

    def __init__(self, termsshift_address: str, max_age_seconds: u32) -> None:
        _require(max_age_seconds > 0, "max_age_seconds must be positive")
        self.owner = gl.message.sender_address
        self.termsshift_address = Address(termsshift_address)
        self.max_age_seconds = max_age_seconds

    @gl.public.write
    def allocate(self, watch_id: str, amount: u256) -> None:
        _require(gl.message.sender_address == self.owner, "only the treasury owner can allocate")
        _require(amount > 0, "amount must be positive")
        terms = gl.get_contract_at(self.termsshift_address)
        safe = terms.view().is_safe(watch_id, self.max_age_seconds)
        _require(safe, f"allocation to {watch_id!r} blocked: TermsShift has no fresh check showing its terms "
                       f"unchanged or changed without adverse effect")

        a = self.allocations.append_new_get()
        a.watch_id = watch_id
        a.amount = amount
        a.recorded_by = gl.message.sender_address
        a.recorded_at = _now()
        self.totals[watch_id] = u256(self.totals.get(watch_id, u256(0)) + amount)

    @gl.public.view
    def total_for(self, watch_id: str) -> int:
        return self.totals.get(watch_id, u256(0))

    @gl.public.view
    def get_allocations(self, offset: u32, limit: u32) -> list:
        limit = min(limit, MAX_PAGE_LIMIT)
        out = []
        i = len(self.allocations) - 1 - offset
        while i >= 0 and len(out) < limit:
            a = self.allocations[i]
            out.append({"watch_id": a.watch_id, "amount": a.amount, "recorded_by": a.recorded_by.as_hex,
                        "recorded_at": a.recorded_at.isoformat()})
            i -= 1
        return out

    @gl.public.view
    def get_config(self) -> dict:
        return {"owner": self.owner.as_hex, "termsshift_address": self.termsshift_address.as_hex,
                "max_age_seconds": self.max_age_seconds, "allocation_count": len(self.allocations)}
