"""
Writes CONTRACT.md from studio-next/live_proof.json (the log prove.ts wrote as it ran), so no transaction
hash, verdict or percentage in it is ever transcribed by hand.   python3 scripts/build_contract_md.py
Deployment facts come from studio-next/deployment.json (written by hand once, from the deploy logs).
"""
import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
L = json.loads((REPO / "studio-next" / "live_proof.json").read_text())
D = json.loads((REPO / "studio-next" / "deployment.json").read_text())
X = "https://explorer-studio-dev.genlayer.com"


def tx(h): return f"[`{h[:10]}…`]({X}/tx/{h})"
def votes(v):
    a, d = v.count("AGREE"), v.count("DISAGREE")
    return f"{a} agree" + (f", {d} disagree" if d else "")
def money(s): return f"{int(s):,}"


tracks = [e for e in L if e["step"] == "track"]
checks = [e for e in L if e["step"] == "recheck"]
ladder = [e for e in L if e["id"].startswith(("alloc-", "ack-", "recheck-")) or e["id"].startswith("refuse-ack")]
read = next(e for e in L if e["step"] == "read")
assert all(e["result"] in ("FINISHED_WITH_RETURN", "FINISHED_WITH_ERROR") for e in L if "result" in e)
assert not any(v == "DISAGREE" for e in L for v in e.get("votes", [])), "a disagreement belongs in the text"
decided = [e for e in L if "tx" in e]

o = []
w = o.append
w("# Terms Radar: deployment and live proof\n")
w("## Deployment\n")
w("| | |\n|---|---|")
w("| Network | GenLayer Studio Next, chain 61997 (`chains.studioDevnet`, genlayer-js 2.0.0-rc.1) |")
w(f"| TermsRadar | [`{D['radar']['address']}`]({X}/address/{D['radar']['address']}) - deploy tx {tx(D['radar']['deploy_tx'])}; constructed with TermsShift's address, `max_age_seconds` 86400 and `acknowledged_pct` 50 |")
w(f"| TermsShift (the oracle it reads) | [`{D['shift']['address']}`]({X}/address/{D['shift']['address']}) - deploy tx {tx(D['shift']['deploy_tx'])}, the contract behind the published TermsShift project |")
w("| Runner | `py-genlayer:5jycge4q8k23462jtb0b9fyey1s9qz928sz2nbrd9mg4sxqg2qng` (v0.3.0) |")
w("| Deployer and owner | `0x5cdb5699bc1038e115A973bb91A646f7E98C075b` |\n")
w("TermsRadar passed the live runner's `getContractSchemaForCode` check before deploying, and **the code on-chain is byte-identical to this repo**: `cd studio-next && npx tsx verify_code.ts <address> terms_radar_studio_next.py` fetches it with `gen_getContractCode` and compares.\n")
w("| Contract | SHA-256 on-chain = SHA-256 of the repo file |\n|---|---|")
w(f"| TermsRadar / `contracts/terms_radar_studio_next.py` | `{D['radar']['sha256']}` |\n")
w(f"## Live proof ({D['date']})\n")
w(f"Reproduce with `cd studio-next && npx tsx prove.ts <termsradar> <termsshift> <setup|check|ladder|read>`. Every row is from [`studio-next/live_proof.json`](studio-next/live_proof.json), written as it ran (it resumes where it stopped), with the radar's own status after each step. \"Agree\" counts the validators that actively voted (Studio Next leaves the rest of the 5-seat committee idle). **All {len(decided)} transactions reached consensus with every voting validator agreeing**, including the ones the contract refused: a refusal is a decided outcome.\n")

w("### 1. Tracking issuers, and what the radar refuses\n")
w("The owner chooses which of TermsShift's watches the radar covers and sets a cap on each. TermsShift's watches are public and permissionless; the radar only follows the ones its owner tracks.\n")
w("| What it does | Tx | Outcome |\n|---|---|---|")
for e in tracks:
    out_ = f"tracked with a cap of {money(e['args'][1])}" if e["result"] == "FINISHED_WITH_RETURN" else f"refused: `{e['revert']}`"
    w(f"| {e['note']} | {tx(e['tx'])} {votes(e['votes'])} | {out_} |")

w("\n### 2. TermsShift reads the issuers' live terms\n")
w("The radar reads TermsShift's latest check at the moment of every decision, and wants it no older than a day. So the proof first asks TermsShift for a fresh check of each issuer (a permissionless call to the TermsShift contract). The radar's posture follows from the verdict.\n")
w("| Watch | TermsShift check | Verdict | Areas that changed | Radar posture | Allowed |\n|---|---|---|---|---|---|")
for e in checks[:3]:
    labels = e["check"]["labels"]
    changed = ", ".join(f"{k}: {v}" for k, v in labels.items() if v != "UNCHANGED") or "none"
    st = e["status"]
    w(f"| `{e['args'][0]}` | {tx(e['tx'])} {votes(e['votes'])} | **{e['check']['verdict']}** | {changed} | **{st['posture']}** | {st['allowed_pct']}% of {money(st['cap'])} |")

w("\n### 3. The allocation ladder, with a person in the loop\n")
w("| Step | Call | Outcome | Posture after | Available after |\n|---|---|---|---|---|")
for e in ladder:
    st = e["status"]
    if e["step"] == "recheck":
        w(f"| {e['note']} | `TermsShift.check({e['args'][0]})` | check {e['check']['check_id']}: {e['check']['verdict']} | **{st['posture']}**{' (sign-off current)' if st.get('acknowledgement') and st['acknowledgement']['current'] else ''} | {money(st['available'])} of {money(st['limit'])} |")
        continue
    call = "acknowledge" if e["step"] == "acknowledge" else "allocate"
    argtxt = f"{e['args'][0]}, \"{e['args'][1][:36]}…\"" if call == "acknowledge" else f"{e['args'][0]}, {money(e['args'][1])}"
    ok = "**signed off**" if call == "acknowledge" else "**allowed**"
    out_ = (ok if e["result"] == "FINISHED_WITH_RETURN" else f"refused: `{e['revert']}`")
    w(f"| {e['note']} | `{call}({argtxt})` | {out_} | **{st['posture']}** | {money(st['available'])} of {money(st['limit'])} |")
ack = read["acknowledgements"][0]
w(f"\nThe sign-off is a public record: `get_acknowledgements()` returns it with the note, the TermsShift check it was made against (id {ack['check_id']}) and the digest of what changed (`{ack['change_digest'][:16]}…`). The note the owner wrote: *\"{ack['note']}\"*\n")

w("### 4. State after the run\n")
w("| Watch | Posture | Allowed | Cap | Allocated | Available |\n|---|---|---|---|---|---|")
for k, st in read["status"].items():
    w(f"| `{k}` | **{st['posture']}**{' (signed off)' if st['acknowledgement'] and st['acknowledgement']['current'] else ''} | {st['allowed_pct']}% | {money(st['cap'])} | {money(st['allocated'])} | {money(st['available'])} |")
cfg = read["config"]
w(f"\n`get_config()` reports {cfg['tracked_count']} issuers tracked, {cfg['acknowledgement_count']} sign-off and {cfg['allocation_count']} allocations. Each allocation record keeps the posture it was made under and the TermsShift check id it relied on (`get_allocations()`).\n")

w("## What the live run found\n")
for t in D.get("found_live", []):
    w("- " + t)
w("")
if D.get("superseded"):
    w("## Superseded deployments\n")
    w("| Contract | Address | Why it is superseded |\n|---|---|---|")
    for s in D["superseded"]:
        w(f"| {s['contract']} | `{s['address']}` | {s['why']} |")
    w("")
w("## Proven in tests, not live\n")
w("Direct Mode proves these on TermsShift's real check records (captured from the live contract, `tests/fixtures/`); none has a live transaction:\n")
w("- **A stale check** (older than the radar's limit, or dated in the future) and **no check at all** give 0%. A live refusal would need a day to pass.")
w("- **A different change voids the sign-off.** The digest covers every area that is not `UNCHANGED`, its status and the digest of its changed wording; changing any one of them, or the set of areas, gives a different digest and the posture falls back to `ADVERSE_UNACKNOWLEDGED`. Reordering the areas does not.")
w("- **An `UNDETERMINED` check** gives 0%, and an unrecognised verdict gives 0%.")
w("- Every owner-only check, a zero cap or amount, invalid configuration, acknowledging or allocating against an issuer that is not tracked, and the cap arithmetic (limits are integer percentages of the cap, never above it). A note that is too short is refused live (section 3); the 400-character upper bound has no live row.")
w("- The cross-contract reads themselves (`list_watches`, `latest_check`) cannot be simulated in Direct Mode, so every code path that makes them is proven by the live tables above.")
(REPO / "CONTRACT.md").write_text("\n".join(o) + "\n")
print("wrote CONTRACT.md,", len(o), "lines;", len(decided), "transactions")
