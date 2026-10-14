# TermsShift - deployment and live proof

## Deployment

| | |
|---|---|
| Network | GenLayer Studio Next, chain 61997 (`chains.studioDevnet`, genlayer-js 2.0.0-rc.1) |
| TermsShift | [`0x0eF30bA1a5B015721A6Ca0989DA68E119bD11c69`](https://explorer-studio-dev.genlayer.com/address/0x0eF30bA1a5B015721A6Ca0989DA68E119bD11c69) - deploy tx [`0xea52e074…`](https://explorer-studio-dev.genlayer.com/tx/0xea52e074f80bd1d8faa55c78c9d15020f3ef48e47228d1a5e804a6e34f6d3c72) |
| TreasuryPolicy | [`0x5923e852A081737Fee943697289E8b37e7C4B541`](https://explorer-studio-dev.genlayer.com/address/0x5923e852A081737Fee943697289E8b37e7C4B541) - deploy tx [`0x323bd483…`](https://explorer-studio-dev.genlayer.com/tx/0x323bd4834a2456b3d3cd9dfed5a0db8d24bca3b3c5481a88bbbe45fea241fc52); constructed with TermsShift's address and `max_age_seconds = 604800` (7 days) |
| Runner | `py-genlayer:5jycge4q8k23462jtb0b9fyey1s9qz928sz2nbrd9mg4sxqg2qng` (v0.3.0) |
| Deployer | `0x5cdb5699bc1038e115A973bb91A646f7E98C075b` |

Both contracts passed the live runner's `getContractSchemaForCode` check before deploying, and **the code on-chain is byte-identical to this repo** - `cd studio-next && npx tsx verify_code.ts <address> <file>` fetches it with `gen_getContractCode` and compares:

| Contract | SHA-256 on-chain = SHA-256 of the repo file |
|---|---|
| TermsShift / `contracts/terms_shift_studio_next.py` | `72dcd10612b9b43c3e8bb667274467591cebb17b3f22d20f294c6ab36da7f1c3` |
| TreasuryPolicy / `contracts/treasury_policy_studio_next.py` | `511ebd86aab7cb52ba806ee37de0651b7e437b4477bd30e4e5469d9614bba28d` |

## Live proof (4 October 2026)

Reproduce with `cd studio-next && npx tsx prove.ts <termsshift> <treasurypolicy> <register|check|refuse|allocate|read>`. Every row is from [`studio-next/live_proof.json`](studio-next/live_proof.json), written as it ran, with each check's full record. "Agree" counts the validators that actively voted (Studio Next leaves the rest of the 5-seat committee idle). **All ten transactions were unanimous.**

### Watches and checks

| Watch | Baseline vs live | Registration | Check | Verdict | Areas that changed |
|---|---|---|---|---|---|
| `circle-since-2024` | Circle USDC Terms, archived 3 Nov 2024 ("Last Updated: October 4, 2024") vs live ("December 12, 2025") | [register](https://explorer-studio-dev.genlayer.com/tx/0xb25d4bc2b7caee36b5293d10577f86c99c5aced9360dd26f67350d8611ee1571) 3/3 | [check](https://explorer-studio-dev.genlayer.com/tx/0x5517bce4c75807b31b13244ea734e0b6a821c3676d1bb7baf0b0feb51834a418) 3/3 | **CHANGED_NOT_ADVERSE** | freezing: NEUTRAL, redemption: NEUTRAL |
| `circle-since-2026` | Circle USDC Terms, archived 2 Oct 2026 vs live | [register](https://explorer-studio-dev.genlayer.com/tx/0x23255e5198cdd3b2d528e9b24ffb1f6987d28c0d816a756b41531d6b2e157faf) 3/3 | [check](https://explorer-studio-dev.genlayer.com/tx/0xcccc1b3c5a41aae45fda10c40507dd65aa11881e7bd710e69a022a4de69bb977) 3/3 | **UNCHANGED** | all six areas UNCHANGED |
| `tether-since-2023` | Tether Terms, archived 15 Sep 2024 ("Last updated: December 7, 2023") vs live ("February 26, 2026") | [register](https://explorer-studio-dev.genlayer.com/tx/0x8b8b2491819200111400f31afbab3bd59d15d56da533e6b90934090a994ea5f3) 3/3 | [check](https://explorer-studio-dev.genlayer.com/tx/0x13b4561fe49cfef9c34b6748fdf4de60c45ca5de557e7493e112b0bf883a7180) 3/3 | **MATERIAL_ADVERSE_CHANGE** | amendment: UNDETERMINED, fees: ADVERSE, freezing: ADVERSE, redemption: ADVERSE, reserves: ADVERSE, suspension: ADVERSE |

Registration stored each baseline's clauses as agreed by every validator: Circle - 104 distinct sentences across the six areas (redemption 60, suspension 30, fees 29, reserves 23, amendment 16, freezing 6); Tether 2023 - redemption 28, suspension 73, reserves 31, fees 18, amendment 20, freezing 7.

### What the reader said

**Circle, Oct 2024 -> live** (`CHANGED_NOT_ADVERSE`). Of everything that changed on the page, only two sentences in the watched areas differ, and only by one word:

> "…in accordance with Circle's ~~blacklisting~~ **blocklisting** policy." (the same rename appears in two sentences)

Every validator's reader judged this not adverse, in both areas it falls in (redemption, freezing) - with no example of this rename anywhere in the prompt.

**Tether, Dec 2023 terms -> live** (`MATERIAL_ADVERSE_CHANGE`). Every quote below was verified word for word against every validator's own copy of the changed wording:

| Area | Adverse | Quote verified | Excerpt of the quote (full quote in the on-chain record) |
|---|---|---|---|
| redemption | yes | yes | "…subject to minimum redemption amounts and other requirements." |
| fees | yes | yes | "…subject to minimum redemption amounts and other requirements." |
| reserves | yes | yes | "…not segregated assets held in your name or for your benefit…" |
| suspension | yes | yes | "Tether may suspend or terminate your access to the Site…" |
| freezing | yes | yes | "…freeze any Tether Tokens held by you…" |
| amendment | no | - | - |

The complete quotes are in `latest_check("tether-since-2023").readings` on-chain, and in `studio-next/live_proof.json`.

`amendment` is `UNDETERMINED`, not `NEUTRAL`: the change was longer than one reader call shows, and a "not adverse" reading of part of a change is never accepted.

### Refusal: a baseline that isn't the exact capture

`register_watch("tether-inexact", "https://tether.to/en/legal/", "20240915000000", …)` - [`0xd293f546…`](https://explorer-studio-dev.genlayer.com/tx/0xd293f546a14b2e15fc79034c2f845720a37ee46a0c4632e3555b6fad4441aa87), FINISHED_WITH_ERROR, 3/3 validators agreeing on the facts behind it. Revert message: `baseline refused: baseline_not_exact_capture`. The archive had answered `20240915000000` with its nearest capture (22:33:52) - a different document than the one named. Nothing was stored.

### The consumer acting on the verdict

| Call (TreasuryPolicy, owner) | Transaction | Result | Total allocated after |
|---|---|---|---|
| `allocate("circle-since-2024", 1000000)` | [0xf8f323a5…](https://explorer-studio-dev.genlayer.com/tx/0xf8f323a551738e29e646ade7a4904585fd501b4c80a37367e34f82a432308847) | FINISHED_WITH_RETURN | 1000000 |
| `allocate("tether-since-2023", 1000000)` | [0x824f66c9…](https://explorer-studio-dev.genlayer.com/tx/0x824f66c96aeedf41273da504e15f03f5a88412d5c51e9fcb1f93363025337b1e) | FINISHED_WITH_ERROR | 0 |
| `allocate("circle-since-2026", 250000)` | [0x824cb538…](https://explorer-studio-dev.genlayer.com/tx/0x824cb538303842630a8a4214b83e300f06551fd39c242ee324de705b755c871c) | FINISHED_WITH_RETURN | 250000 |

The Tether allocation reverted with `allocation to 'tether-since-2023' blocked: TermsShift has no fresh check showing its terms unchanged or changed without adverse effect`.

Consumer view, read after the run:

```
is_safe("circle-since-2024", 86400) = true    # CHANGED_NOT_ADVERSE, checked minutes ago
is_safe("circle-since-2024", 1)     = false   # same check, older than 1 second
is_safe("circle-since-2026", 86400) = true    # UNCHANGED
is_safe("tether-since-2023", 86400) = false   # MATERIAL_ADVERSE_CHANGE
```

## Earlier deployments (superseded)

None of these is the deployment to review; each was replaced before submission, and the reason is recorded.

| TermsShift / TreasuryPolicy | Why superseded |
|---|---|
| `0x20ceaF728CB3841D6A835ABb58710572c4293A9f` / `0xA6cD536aa63d9F9622A3f3371e0f0364158A5914` | Never used. The reader's prompt used "blacklist -> blocklist" as its example of a cosmetic change - which is the Circle demo case itself. Replaced with generic examples so the live result shows the reader generalising, not recognising its own example. |
| `0xcE241a16543A06781472905e56B3E8c1F457f471` / `0xBc084B680882D2fE69CacB357208737E8C0Ea939` | Re-fetched the archived baseline on every check; the archive refused the validators' connections (`SENDING_REQUEST`, e.g. [`0x8545530d…`](https://explorer-studio-dev.genlayer.com/tx/0x8545530d8d5f3c505dce7b25447d38f8cafbeffae5b62cd32ddd2683eb32d676)). Redesigned: the archive is read once, at registration, and the agreed baseline stored on-chain; fetches retry up to three times. |
| `0x9b6CE2C46652f716504d006eb395d2F82a505497` / `0x969C4Cb7cA8b0D454249f89060297A40B8493EC7` | Same verdicts as above, but on Tether the reader's stitched quotes ("…requirements. Tether may…", with "…") failed a contiguous-substring check, so four genuinely adverse areas came out `UNDETERMINED` and two validators disagreed ([`0x3387c403…`](https://explorer-studio-dev.genlayer.com/tx/0x3387c4032b8821c11780bf46bc76e6c2f859bd993a73a84785effddfb05d494c)). Grounding now requires every fragment of a quote to be verbatim - just as strict against invention, without rejecting genuine quotes. |
