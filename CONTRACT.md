# Terms Radar: deployment and live proof

## Deployment

| | |
|---|---|
| Network | GenLayer Studio Next, chain 61997 (`chains.studioDevnet`, genlayer-js 2.0.0-rc.1) |
| TermsRadar | [`0x5f5ce46A8096920B177914d119C1Af048C29BE71`](https://explorer-studio-dev.genlayer.com/address/0x5f5ce46A8096920B177914d119C1Af048C29BE71) - deploy tx [`0x3ba8a93e…`](https://explorer-studio-dev.genlayer.com/tx/0x3ba8a93e2d3a9715ad30e1bc0f81fdcb929cabbb4c35458b8bc566adac81cd85); constructed with TermsShift's address, `max_age_seconds` 86400 and `acknowledged_pct` 50 |
| TermsShift (the oracle it reads) | [`0x0eF30bA1a5B015721A6Ca0989DA68E119bD11c69`](https://explorer-studio-dev.genlayer.com/address/0x0eF30bA1a5B015721A6Ca0989DA68E119bD11c69) - deploy tx [`0xea52e074…`](https://explorer-studio-dev.genlayer.com/tx/0xea52e074f80bd1d8faa55c78c9d15020f3ef48e47228d1a5e804a6e34f6d3c72), the contract behind the published TermsShift project |
| Runner | `py-genlayer:5jycge4q8k23462jtb0b9fyey1s9qz928sz2nbrd9mg4sxqg2qng` (v0.3.0) |
| Deployer and owner | `0x5cdb5699bc1038e115A973bb91A646f7E98C075b` |

TermsRadar passed the live runner's `getContractSchemaForCode` check before deploying, and **the code on-chain is byte-identical to this repo**: `cd studio-next && npx tsx verify_code.ts <address> terms_radar_studio_next.py` fetches it with `gen_getContractCode` and compares.

| Contract | SHA-256 on-chain = SHA-256 of the repo file |
|---|---|
| TermsRadar / `contracts/terms_radar_studio_next.py` | `ac50a737edd42187fbef6112472b47b81db829a4fd3552b07aa75ad9a12f9838` |

## Live proof (2026-10-11)

Reproduce with `cd studio-next && npx tsx prove.ts <termsradar> <termsshift> <setup|check|ladder|read>`. Every row is from [`studio-next/live_proof.json`](studio-next/live_proof.json), written as it ran (it resumes where it stopped), with the radar's own status after each step. "Agree" counts the validators that actively voted (Studio Next leaves the rest of the 5-seat committee idle). **All 19 transactions reached consensus with every voting validator agreeing**, including the ones the contract refused: a refusal is a decided outcome.

### 1. Tracking issuers, and what the radar refuses

The owner chooses which of TermsShift's watches the radar covers and sets a cap on each. TermsShift's watches are public and permissionless; the radar only follows the ones its owner tracks.

| What it does | Tx | Outcome |
|---|---|---|
| tracking: Circle's USDC terms against the version captured on 2 October 2026: unchanged | [`0xc5e5cd1f…`](https://explorer-studio-dev.genlayer.com/tx/0xc5e5cd1f253138616db406173fce5d140fac8c265796cba58433850447b4c3e7) 3 agree | tracked with a cap of 1,000,000 |
| tracking: Circle's USDC terms against October 2024: two areas changed (blacklisting became blocklisting), read as not adverse | [`0x37e3b62b…`](https://explorer-studio-dev.genlayer.com/tx/0x37e3b62bad2deeb944ce77b9ab69ca5aabc27767ba06b7a339db3f3b3bfedfea) 3 agree | tracked with a cap of 1,000,000 |
| tracking: Tether's terms against December 2023: all six areas changed, five judged adverse | [`0x06cd6178…`](https://explorer-studio-dev.genlayer.com/tx/0x06cd6178cdaf4c4517fabf7a8a594ff143b5706a7ef397c0fe28a5adef2bd993) 3 agree | tracked with a cap of 1,000,000 |
| an issuer tracked twice | [`0x55f7d0bc…`](https://explorer-studio-dev.genlayer.com/tx/0x55f7d0bcab664bfdd753475bf11278ebb3f12b38a09863cea471a1e62f7ae8f8) 3 agree | refused: `already tracked` |
| a watch TermsShift has never heard of | [`0x149ab5fe…`](https://explorer-studio-dev.genlayer.com/tx/0x149ab5fe18e587a0262fe39c9e1063a608b20451708baf2b978f43dd4475d871) 3 agree | refused: `'no-such-watch' refused: TermsShift has no such watch` |

### 2. TermsShift reads the issuers' live terms

The radar reads TermsShift's latest check at the moment of every decision, and wants it no older than a day. So the proof first asks TermsShift for a fresh check of each issuer (a permissionless call to the TermsShift contract). The radar's posture follows from the verdict.

| Watch | TermsShift check | Verdict | Areas that changed | Radar posture | Allowed |
|---|---|---|---|---|---|
| `circle-since-2026` | [`0x7dfae2e0…`](https://explorer-studio-dev.genlayer.com/tx/0x7dfae2e0d9a4e44b0d4f625de1f1680834e1be1be4ef0884ec0d93b9080c545d) 3 agree | **UNCHANGED** | none | **CLEAR** | 100% of 1,000,000 |
| `circle-since-2024` | [`0x4fb7f169…`](https://explorer-studio-dev.genlayer.com/tx/0x4fb7f169fc2d9f520e0dea57ec46e43da98c4d67730791805200afa14cd90b4d) 3 agree | **CHANGED_NOT_ADVERSE** | freezing: NEUTRAL, redemption: NEUTRAL | **CHANGED** | 100% of 1,000,000 |
| `tether-since-2023` | [`0xebad5f2f…`](https://explorer-studio-dev.genlayer.com/tx/0xebad5f2fc510538d631d89d978d4e309ec822dc566828999e280cabc0b104db4) 3 agree | **MATERIAL_ADVERSE_CHANGE** | amendment: UNDETERMINED, fees: ADVERSE, freezing: ADVERSE, redemption: ADVERSE, reserves: ADVERSE, suspension: ADVERSE | **ADVERSE_UNACKNOWLEDGED** | 0% of 1,000,000 |

### 3. The allocation ladder, with a person in the loop

| Step | Call | Outcome | Posture after | Available after |
|---|---|---|---|---|
| acknowledging an issuer whose terms have not changed | `acknowledge(circle-since-2026, "Reviewed Tether's change against Dec…")` | refused: `nothing to acknowledge: TermsShift's latest check of 'circle-since-2026' is UNCHANGED` | **CLEAR** | 1,000,000 of 1,000,000 |
| a sign-off with no real note | `acknowledge(tether-since-2023, "ok…")` | refused: `the note must say what was decided, 20-400 characters` | **ADVERSE_UNACKNOWLEDGED** | 0 of 0 |
| unchanged terms: 100% of the cap is available | `allocate(circle-since-2026, 900,000)` | **allowed** | **CLEAR** | 100,000 of 1,000,000 |
| 100,000 is left of the cap: refused | `allocate(circle-since-2026, 200,000)` | refused: `'circle-since-2026' refused: CLEAR allows 100% of the cap 1000000, of which 100000 is left` | **CLEAR** | 100,000 of 1,000,000 |
| changed but read in full as not adverse: still 100% | `allocate(circle-since-2024, 500,000)` | **allowed** | **CHANGED** | 500,000 of 1,000,000 |
| a material adverse change nobody has signed off: nothing is allowed | `allocate(tether-since-2023, 100,000)` | refused: `'tether-since-2023' refused: ADVERSE_UNACKNOWLEDGED - a material adverse change nobody has signed off: read it, then acknowledge it` | **ADVERSE_UNACKNOWLEDGED** | 0 of 0 |
| the owner reads the change and signs it off on-chain, with a note | `acknowledge(tether-since-2023, "Reviewed Tether's change against Dec…")` | **signed off** | **ADVERSE_ACKNOWLEDGED** | 500,000 of 500,000 |
| signed off: 50% of the cap (500,000) is available | `allocate(tether-since-2023, 400,000)` | **allowed** | **ADVERSE_ACKNOWLEDGED** | 100,000 of 500,000 |
| 400,000 is used, 100,000 left: refused | `allocate(tether-since-2023, 200,000)` | refused: `'tether-since-2023' refused: ADVERSE_ACKNOWLEDGED allows 50% of the cap 1000000, of which 100000 is left` | **ADVERSE_ACKNOWLEDGED** | 100,000 of 500,000 |
| TermsShift checks Tether again: the same wording, so the sign-off still holds | `TermsShift.check(tether-since-2023)` | check 9: MATERIAL_ADVERSE_CHANGE | **ADVERSE_ACKNOWLEDGED** (sign-off current) | 100,000 of 500,000 |
| after the re-check the sign-off still applies: the last 100,000 is allowed | `allocate(tether-since-2023, 100,000)` | **allowed** | **ADVERSE_ACKNOWLEDGED** | 0 of 500,000 |

The sign-off is a public record: `get_acknowledgements()` returns it with the note, the TermsShift check it was made against (id 8) and the digest of what changed (`a92c525b16619707…`). The note the owner wrote: *"Reviewed Tether's change against Dec 2023: redemption minimums, no segregation of reserves, wide suspension and freezing rights. Accepted at half the cap."*

### 4. State after the run

| Watch | Posture | Allowed | Cap | Allocated | Available |
|---|---|---|---|---|---|
| `circle-since-2026` | **CLEAR** | 100% | 1,000,000 | 900,000 | 100,000 |
| `circle-since-2024` | **CHANGED** | 100% | 1,000,000 | 500,000 | 500,000 |
| `tether-since-2023` | **ADVERSE_ACKNOWLEDGED** (signed off) | 50% | 1,000,000 | 500,000 | 0 |

`get_config()` reports 3 issuers tracked, 1 sign-off and 4 allocations. Each allocation record keeps the posture it was made under and the TermsShift check id it relied on (`get_allocations()`).

## What the live run found

- **The same graded rule answered three different issuers.** Circle's terms against the capture of 2 October 2026 came back `UNCHANGED` (100% of the cap), Circle against October 2024 came back `CHANGED_NOT_ADVERSE` (still 100%: two areas changed, both read in full and judged not adverse), and Tether against December 2023 came back `MATERIAL_ADVERSE_CHANGE` (0% until a person signs it off). All three verdicts are TermsShift's own, read fresh from the issuers' live pages by its validators during this run.
- **A person is in the loop exactly where the evidence is adverse.** Allocating to Tether was refused as `ADVERSE_UNACKNOWLEDGED`. Once the owner signed off with a note, the same call was allowed up to 50% of the cap, and the 200,000 that would have passed 50% was refused with the amount still available.
- **The sign-off follows the wording, not the check.** After the sign-off the owner asked TermsShift to check Tether again (a new check id, a new timestamp); the radar still reported `ADVERSE_ACKNOWLEDGED` with `current: true`, because the digest of what changed was identical, and the last 100,000 was allowed.
- **Nothing to sign off, nothing signed.** Acknowledging Circle's unchanged terms was refused (`nothing to acknowledge`), and so was a one-word note.

## Superseded deployments

| Contract | Address | Why it is superseded |
|---|---|---|
| TermsRadar (trial instance) | `0x65415d34d298AD9B854000389957aEc7A9784D58` | Same code (byte-identical), deployed for a trial run; its state holds trial tracking and sign-offs. Replaced by a clean deployment so every row of the live proof starts from empty. |

## Proven in tests, not live

Direct Mode proves these on TermsShift's real check records (captured from the live contract, `tests/fixtures/`); none has a live transaction:

- **A stale check** (older than the radar's limit, or dated in the future) and **no check at all** give 0%. A live refusal would need a day to pass.
- **A different change voids the sign-off.** The digest covers every area that is not `UNCHANGED`, its status and the digest of its changed wording; changing any one of them, or the set of areas, gives a different digest and the posture falls back to `ADVERSE_UNACKNOWLEDGED`. Reordering the areas does not.
- **An `UNDETERMINED` check** gives 0%, and an unrecognised verdict gives 0%.
- Every owner-only check, a zero cap or amount, invalid configuration, acknowledging or allocating against an issuer that is not tracked, and the cap arithmetic (limits are integer percentages of the cap, never above it). A note that is too short is refused live (section 3); the 400-character upper bound has no live row.
- The cross-contract reads themselves (`list_watches`, `latest_check`) cannot be simulated in Direct Mode, so every code path that makes them is proven by the live tables above.
