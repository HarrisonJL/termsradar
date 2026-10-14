# Trust path: from an issuer's published terms to an allocation

A reviewer's first question about this project is fair: **where in this repository does anything non-deterministic happen?** It does not happen in the radar, and that is on purpose. `contracts/terms_radar.py` is a deterministic policy: it has no web access and no LLM, so it can never be a second, unaudited source of truth about an issuer. Everything that reads the real world, uses a model, and reaches validator consensus is in **TermsShift**, the contract the radar reads. Its **exact deployed source is included in this repository** under [`dependencies/termsshift/`](dependencies/termsshift/), so the whole path can be reviewed here, end to end.

## The path

```
issuer's live terms page          archived baseline (Internet Archive)
            \                         /      every validator fetches both itself
             v                       v       dependencies/termsshift/contracts/terms_shift_studio_next.py:408
   TermsShift.check(watch)
   - plain code parses six clause areas, diffs against the baseline, hashes the changed wording (excerpt_digest)   :295, :170
   - an LLM reads ONLY the changed wording; 'adverse' counts only with a verbatim quote found in it                :418, :457, :342
   - consensus: gl.vm.run_nondet; validators must agree EXACTLY on the facts and on the verdict, and every
     'adverse' finding must be adverse to the validator's own reader                                              :610-655
   - the verdict is recomputed from the agreed facts and readings, never taken from the leader                    :378, :664
            |
            v   stored record: verdict, checked_at, per-area facts incl. excerpt_digest                           :721 (latest_check)
            |
            v   cross-contract VIEW read, at the moment of every call (nothing is cached)
   TermsRadar (contracts/terms_radar_studio_next.py)
   - reads the record                                                                                            :163
   - posture = pure function of the record (CLEAR / CHANGED / ADVERSE_* / UNDETERMINED / STALE / NO_CHECK)       :69
   - a sign-off is bound to a digest of what changed (built from TermsShift's excerpt_digest)                    :60, :192
   - allocate() refuses unless the posture allows it, reading the record again                                   :214
```

Line numbers are for the files as committed here; `tests/test_trust_path.py` regenerates this document and fails if it has gone stale.

## What each stage does, and where it is reviewable

| Stage | Non-deterministic? | Who must agree | Code | Tests |
|---|---|---|---|---|
| Fetch the live page and the archived baseline | yes (web) | every validator fetches itself; exact agreement on the facts (via `facts_digest`) | [`terms_shift_studio_next.py:408`](dependencies/termsshift/contracts/terms_shift_studio_next.py#L408) | [`dependencies/termsshift/tests/`](dependencies/termsshift/tests/) (44 tests on real captures) |
| Parse the six areas and diff | no (plain code) | exact, as above | [`terms_shift_studio_next.py:295`](dependencies/termsshift/contracts/terms_shift_studio_next.py#L295) | same |
| Judge whether a change is adverse | yes (LLM) | the leader's verdict and every adverse area must match each validator's own reader; the quote must be verbatim in each validator's own copy | [`terms_shift_studio_next.py:418`](dependencies/termsshift/contracts/terms_shift_studio_next.py#L418), [`terms_shift_studio_next.py:342`](dependencies/termsshift/contracts/terms_shift_studio_next.py#L342) | consensus-boundary tests in the same suite |
| Decide the verdict | no | recomputed after consensus | [`terms_shift_studio_next.py:378`](dependencies/termsshift/contracts/terms_shift_studio_next.py#L378) | same |
| Read the record and set a posture | no (pure) | n/a: a function of one record | [`terms_radar_studio_next.py:69`](contracts/terms_radar_studio_next.py#L69) | [`tests/test_terms_radar.py`](tests/test_terms_radar.py) on real check records |
| Bind a sign-off to the changed wording | no (pure) | n/a | [`terms_radar_studio_next.py:60`](contracts/terms_radar_studio_next.py#L60) | same, plus mutation checks |

## Evidence that it ran: the live transactions

Registration of each watch (TermsShift reads the archived baseline and stores its clauses), from the dependency's own live proof ([`dependencies/termsshift/CONTRACT.md`](dependencies/termsshift/CONTRACT.md)):

| Watch | Registration | First check |
|---|---|---|
| `circle-since-2024` | [0xb25d4bc2…](https://explorer-studio-dev.genlayer.com/tx/0xb25d4bc2b7caee36b5293d10577f86c99c5aced9360dd26f67350d8611ee1571) | [0x5517bce4…](https://explorer-studio-dev.genlayer.com/tx/0x5517bce4c75807b31b13244ea734e0b6a821c3676d1bb7baf0b0feb51834a418) |
| `circle-since-2026` | [0x23255e51…](https://explorer-studio-dev.genlayer.com/tx/0x23255e5198cdd3b2d528e9b24ffb1f6987d28c0d816a756b41531d6b2e157faf) | [0xcccc1b3c…](https://explorer-studio-dev.genlayer.com/tx/0xcccc1b3c5a41aae45fda10c40507dd65aa11881e7bd710e69a022a4de69bb977) |
| `tether-since-2023` | [0x8b8b2491…](https://explorer-studio-dev.genlayer.com/tx/0x8b8b2491819200111400f31afbab3bd59d15d56da533e6b90934090a994ea5f3) | [0x13b4561f…](https://explorer-studio-dev.genlayer.com/tx/0x13b4561fe49cfef9c34b6748fdf4de60c45ca5de557e7493e112b0bf883a7180) |

Checks run during this project's live proof, each a TermsShift transaction that its validators decided before the radar read it ([`CONTRACT.md`](CONTRACT.md), section 2):

| Check | Tx | Validators | TermsShift's verdict | Areas it found changed |
|---|---|---|---|---|
| `circle-since-2026` (check 6) | [`0x7dfae2e0…`](https://explorer-studio-dev.genlayer.com/tx/0x7dfae2e0d9a4e44b0d4f625de1f1680834e1be1be4ef0884ec0d93b9080c545d) | 3 agree | **UNCHANGED** | none |
| `circle-since-2024` (check 7) | [`0x4fb7f169…`](https://explorer-studio-dev.genlayer.com/tx/0x4fb7f169fc2d9f520e0dea57ec46e43da98c4d67730791805200afa14cd90b4d) | 3 agree | **CHANGED_NOT_ADVERSE** | freezing: NEUTRAL, redemption: NEUTRAL |
| `tether-since-2023` (check 8) | [`0xebad5f2f…`](https://explorer-studio-dev.genlayer.com/tx/0xebad5f2fc510538d631d89d978d4e309ec822dc566828999e280cabc0b104db4) | 3 agree | **MATERIAL_ADVERSE_CHANGE** | amendment: UNDETERMINED, fees: ADVERSE, freezing: ADVERSE, redemption: ADVERSE, reserves: ADVERSE, suspension: ADVERSE |
| `tether-since-2023` (check 9) | [`0xd477dafb…`](https://explorer-studio-dev.genlayer.com/tx/0xd477dafb408a8e39add446e0ae89f7c46e0dfb4b66d44305450e88cef5ad8728) | 3 agree | **MATERIAL_ADVERSE_CHANGE** | amendment: UNDETERMINED, fees: ADVERSE, freezing: ADVERSE, redemption: ADVERSE, reserves: ADVERSE, suspension: ADVERSE |

## Identity of the dependency

| | |
|---|---|
| TermsShift (deployed) | [`0x0eF30bA1a5B015721A6Ca0989DA68E119bD11c69`](https://explorer-studio-dev.genlayer.com/address/0x0eF30bA1a5B015721A6Ca0989DA68E119bD11c69), deploy tx [`0xea52e074…`](https://explorer-studio-dev.genlayer.com/tx/0xea52e074f80bd1d8faa55c78c9d15020f3ef48e47228d1a5e804a6e34f6d3c72) |
| Vendored from | [github.com/HarrisonJL/termsshift](https://github.com/HarrisonJL/termsshift), every tracked file at the commit recorded in [`dependencies/README.md`](dependencies/README.md) |
| Deployed file | `dependencies/termsshift/contracts/terms_shift_studio_next.py`, byte-identical to the code on-chain (SHA-256 in `dependencies/README.md`; checked by `tests/test_trust_path.py` and by `studio-next/verify_dependency.ts` against the chain) |

## How to review it

```bash
# 1. the radar's tests, and the checks that tie it to the vendored dependency
.venv/bin/pytest tests -q
# 2. the dependency's own tests (it needs its pinned archive captures first)
cd dependencies/termsshift && python3 scripts/fetch_fixtures.py && ../../.venv/bin/pytest tests -q
# 3. the vendored code is what is deployed
cd studio-next && npm ci && npx tsx verify_dependency.ts
```
