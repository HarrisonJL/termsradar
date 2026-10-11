# Terms Radar

**How much may we allocate to this stablecoin issuer, given what its terms say today?** A GenLayer Intelligent Contract that turns [TermsShift](https://github.com/HarrisonJL/termsshift)'s verdicts about an issuer's live terms into a rule a treasury can run on-chain, with a person in the loop exactly where the evidence is adverse. The cap you may allocate to an issuer is a share of its limit that depends on the latest check: 100% while the terms are unchanged (or changed but read in full as not adverse), **0% after a material adverse change until the owner has read it and signed it off on-chain with a note**, then a reduced share. The sign-off is bound to the exact wording that changed.

| | |
|---|---|
| Network | GenLayer Studio Next (chain 61997) |
| TermsRadar | [`0x5f5ce46A8096920B177914d119C1Af048C29BE71`](https://explorer-studio-dev.genlayer.com/address/0x5f5ce46A8096920B177914d119C1Af048C29BE71) |
| Reads | [TermsShift `0x0eF30bA1…D11c69`](https://explorer-studio-dev.genlayer.com/address/0x0eF30bA1a5B015721A6Ca0989DA68E119bD11c69) (the published oracle: its validators read Circle's and Tether's live terms) |
| Live app | TERMSRADAR_URL (source in [`web/`](web/)) |
| Live proof | [CONTRACT.md](CONTRACT.md): three real issuers, the whole allocation ladder, a sign-off that survives a re-check, every refusal, every transaction linked |
| Tests | 32 Direct Mode tests on TermsShift's real check records; 32 safety mutations, all killed; 24 web-app tests |

> **Accounting, not custody.** The radar records and limits allocations; it does not hold or move tokens. It is the control a treasury's own contracts or process consult before moving value, not the treasury itself.

## Why this exists

[TermsShift](https://github.com/HarrisonJL/termsshift) answers a factual question: have an issuer's published terms changed against holders since a baseline, in the six areas that matter (redemption, suspension, freezing, reserves, fees, amendment)? Its own consumer, TreasuryPolicy, is a switch: safe or blocked.

Treasuries do not run on switches. An adverse change to Tether's terms is a reason to stop and read, not a reason to be locked out forever, and "we read it and accepted it at half the limit" is a decision that deserves a record. Terms Radar adds the part that is missing: a graded response, a human decision recorded on-chain, and a guarantee that the decision cannot be reused for different wording.

## How it decides

The radar reads TermsShift's **latest check for the issuer at the moment of every call** (nothing is cached), and answers with a posture:

| Posture | May be allocated | When |
|---|---|---|
| `CLEAR` | 100% of the cap | The latest check found the terms unchanged since the baseline |
| `CHANGED` | 100% | The terms changed, and every change was read in full and judged not adverse |
| `ADVERSE_ACKNOWLEDGED` | the owner's percentage (50% here) | A material adverse change that the owner signed off, for exactly this wording |
| `ADVERSE_UNACKNOWLEDGED` | 0% | A material adverse change nobody has signed off |
| `UNDETERMINED` | 0% | The check could not settle every area |
| `STALE` | 0% | The latest check is older than the radar allows (a day here), or dated in the future |
| `NO_CHECK` | 0% | TermsShift has never checked the issuer |

What may be allocated is that percentage of the issuer's **cap** (set by the owner when tracking it), minus what has already been allocated. Integer arithmetic throughout.

### The sign-off is bound to the wording

`acknowledge(watch_id, note)` records the owner's note with a **digest of what changed**: for every area that is not `UNCHANGED`, its status and the digest of the changed wording, exactly as TermsShift's validators agreed it. A later check that finds the same change keeps the sign-off (the digest is identical, whatever the check id or time). A check that finds different wording gives a different digest, the posture falls back to `ADVERSE_UNACKNOWLEDGED`, and a new, informed sign-off is needed. A sign-off of an old adverse change does not dim a later clean check. The note must say what was decided (20 to 400 characters), and only a latest check that found a change can be signed off.

## The three calls

| Call (owner only) | What it does |
|---|---|
| `track(watch_id, cap)` | Cover one of TermsShift's watches, with the most that may ever be allocated against it. Refused if already tracked, or if TermsShift has no such watch. |
| `acknowledge(watch_id, note)` | "I have read what changed, and accept it." Refused if TermsShift's latest check found nothing to accept, or the note is too short. |
| `allocate(watch_id, amount)` | Record an allocation. The latest check is read right now; refused if the posture allows 0%, or the amount is more than is left. |

Views: `get_status(watch_id)` (posture, allowed percentage, cap, allocated, available, the TermsShift check relied on, and the current sign-off with `current: true` when it applies to the present wording), `list_tracked`, `get_acknowledgements`, `get_allocations`, `get_config`, `get_rules` (the ladder itself, so an app can show the contract's own numbers).

## Using it from another contract

```python
radar = gl.contract.get_at(RADAR_ADDRESS)        # Studio Next syntax
status = radar.view().get_status("tether-since-2023")
if status["allowed_pct"] == 0 or int(status["available"]) < amount:
    raise gl.vm.UserError(f"allocation refused: {status['posture']}")
```

`allowed_pct` and `available` are computed at the moment of the call from TermsShift's latest check, so a consumer inherits the freshness rule without implementing it.

## The web app

[`web/`](web/) is a Vite + React app that reads the radar live and sends real transactions through the whole consensus lifecycle (genlayer-js 2.0.0-rc.1, Studio Next). Reading needs no account; writing uses a wallet (MetaMask) or a throwaway in-browser account funded from Studio Next's faucet.

- **The board** shows each tracked issuer's posture, how much of its cap is allocated and available, how old TermsShift's check is, and the contract's own ladder.
- **One issuer in detail** shows TermsShift's six areas with the reader's quote, verified word for word, for every adverse finding.
- **Ask TermsShift for a fresh check** is a real transaction anyone can send: every validator reads the issuer's live terms and the archived baseline. The result shown is the check **this** transaction created (compared before and after, and by sender), never "the latest one".
- **Sign off, allocate and track** are owner-only, as they would be for a real treasury. So the app lets you **create your own desk**: it deploys this exact contract from your account (the code the app carries is byte-identical to the deployed one; a test checks its SHA-256 against the code on-chain), and you are its owner. A refused call shows the contract's own message and records nothing.

### Try it in five minutes

1. Open the app. **Use a temporary account**, then **Get 100 test GEN**.
2. Click **Create my desk**. When the panel says "accepted by consensus", the desk is yours.
3. Under **Track an issuer**, choose `tether-since-2023` and click **Track**.
4. The issuer shows **Adverse, not signed off**, 0% available. Try to allocate: it is refused.
5. Under **Sign the change off**, write a note of at least 20 characters and click **Sign off**. The issuer becomes **Adverse, signed off**, with 50% of its cap available.
6. Allocate part of it. Then try to allocate more than is left: the contract refuses, and says why.
7. Optional: click **Ask TermsShift for a fresh check** and watch the validators vote (a minute or two). The sign-off still applies, because the wording is the same.

## What this proves, and what it doesn't

| It proves | It does not prove |
|---|---|
| What TermsShift's validators agreed an issuer's published terms say, against an archived version, in six clause areas, as of a check time | Anything about the issuer's reserves, solvency or conduct, or how a court would read the terms |
| The owner read the change and said so, on-chain, against one specific check and the digest of one specific change | That the owner read it well: a sign-off is a recorded decision, not a review of its quality |
| Every allocation was made under a posture, and records which check it relied on | That tokens were moved, or that the allocation was prudent |
| A sign-off cannot be reused for different wording | That nothing outside the six areas changed |

## Known limitations

- **It trusts TermsShift for facts.** The radar adds policy and a human decision, not a second reading of the terms. Everything TermsShift cannot read (pages that do not serve their terms in plain HTML; Circle and Tether are the proven ones), it reports as `UNDETERMINED`, and the radar allows nothing.
- **A materially long change can only be read in part.** TermsShift marks such an area `UNDETERMINED` rather than judging it from a fragment (Tether's rewritten amendment clauses, live). The radar is then driven by the other areas' findings.
- **A sign-off follows the changed wording of the six areas** and nothing else.
- **Owner-only controls.** One owner per radar. A real deployment would put a multisig behind it; the proof uses a single account.
- **A stale check cannot be demonstrated live in a day** (the limit is a day); it is proven in tests on the real records.
- **Studio Next only.**

## Running it

```bash
python3 -m venv .venv && .venv/bin/pip install genlayer-test==0.29.2 genvm-linter==0.11.0 pytest
.venv/bin/pytest tests -q                       # 32 tests on TermsShift's real check records
.venv/bin/genvm-lint check contracts/terms_radar.py
python3 scripts/mutation_check.py               # every safety mutation must be killed

cd studio-next && npm ci
npx tsx verify_code.ts <address> terms_radar_studio_next.py     # on-chain code == this repo

cd ../web && npm ci && npm test && npm run build && npm run preview
```

## Repository layout

```
contracts/terms_radar.py              tested source (GenVM v0.2.11)
contracts/terms_radar_studio_next.py  deployed port (Studio Next); web/src/lib carries a byte-identical copy
tests/                                Direct Mode tests, TermsShift's real check records, mutations.txt
scripts/                              port, mutation check, CONTRACT.md builder
studio-next/                          deploy, live proof (prove.ts, live_proof.json), verify_code.ts
web/                                  the live app (Vite + React + genlayer-js)
research/                             what the radar reads from TermsShift, and why
```
