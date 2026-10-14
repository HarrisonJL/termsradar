# TermsShift

**Have a stablecoin issuer's terms changed *against holders* since the version you relied on?** A GenLayer Intelligent Contract that compares an issuer's live terms with an Internet Archive capture of the same page, clause area by clause area, and publishes a verdict a treasury contract can act on: `UNCHANGED`, `CHANGED_NOT_ADVERSE`, `MATERIAL_ADVERSE_CHANGE`, or `UNDETERMINED`.

| | |
|---|---|
| Network | GenLayer Studio Next (chain 61997) |
| TermsShift | [`0x0eF30bA1a5B015721A6Ca0989DA68E119bD11c69`](https://explorer-studio-dev.genlayer.com/address/0x0eF30bA1a5B015721A6Ca0989DA68E119bD11c69) |
| TreasuryPolicy (consumer) | [`0x5923e852A081737Fee943697289E8b37e7C4B541`](https://explorer-studio-dev.genlayer.com/address/0x5923e852A081737Fee943697289E8b37e7C4B541) |
| Live proof | [CONTRACT.md](CONTRACT.md) — real Circle and Tether terms, every verdict, every transaction unanimous |
| Tests | 44 Direct Mode tests on real archived terms; 30/30 safety mutations killed |

## Why this exists

A treasury holding USDC or USD₮ holds a contractual claim defined by the issuer's published terms: who can redeem, when redemption can be suspended, what backs the token, when tokens can be frozen, what it costs. Those terms change, usually without anyone at the treasury noticing. A plain text diff is useless here — Circle's USDC Terms page changed in dozens of places between October 2024 and December 2025 (menus, footers, a sanctions list), and almost none of it matters to a holder. Tether's terms were rewritten between December 2023 and February 2026, and some of it matters a lot.

What a treasury actually needs is a judgment — *did this get worse for me?* — made by someone the treasury doesn't have to trust, re-checkable, and readable by a contract. That's what an LLM-backed validator committee can give.

## How it decides

### 1. The baseline can't be fabricated

There is no "upload the old terms" step. The baseline is the **Internet Archive's capture of the issuer's own page**: the caller gives the live URL and a 14-digit capture timestamp, and the contract builds the archive URL itself. At registration every validator fetches it and checks:

- the archive served **exactly** that capture (`Memento-Datetime` equals the requested timestamp — the archive silently redirects an inexact timestamp to the *nearest* capture, a different document; live proof: refused);
- it is a capture **of that same page** (`Link: …; rel="original"`, ignoring `www.` and a trailing slash).

The validators then agree, byte for byte, on the baseline's clauses, which are stored on-chain. Later checks read only the issuer's live page — they never go back to the archive. (An earlier deployment did, and the archive refused the validators' connections on every check — `research/`.)

### 2. Clause-level, not page-level

Both versions are reduced to real sentences (navigation and buttons are filtered out) and grouped into six watched clause areas — **redemption, suspension, reserves, freezing, fees, amendment** — by paragraph. An area whose sentences are identical is `UNCHANGED` **by plain code, with no LLM involved**. That's why Circle's heavily edited page comes out with four of six areas untouched, and why the October 2026 capture of the same page compares `UNCHANGED` in every area without a single LLM call.

### 3. The LLM judges only what changed — and must quote it

For each changed area, the reader sees only the sentences that differ (old and new) and decides whether the change makes the area **materially worse for a holder**. Its powers are deliberately narrow:

- **An adverse finding counts only with a verbatim quote.** Every fragment of the quote (readers often stitch sentences together or elide with "…") must appear word for word in the changed wording, checked by every validator against its own copy. One invented fragment voids the whole quote — the area becomes `UNDETERMINED`, not a published accusation.
- **"Not adverse" counts only if the reader saw the whole change.** Each reader call shows at most 3,000 characters of old and 6,000 of new wording. If a change is longer, a "not adverse" reading of its first part can't be accepted — that area is `UNDETERMINED`. (Tether's rewritten amendment clauses, live: exactly this.)
- **An unreadable answer is never a default "not adverse"** — it's `UNDETERMINED`.
- **No caller-supplied text reaches the prompt** — only the issuer's wording and the contract's own area definitions.

### 4. Fail closed

| Verdict | Meaning |
|---|---|
| `UNCHANGED` | Every watched area's sentences are identical to the baseline. |
| `CHANGED_NOT_ADVERSE` | Some watched areas changed; every validator's reader agrees none of the changes makes things worse for a holder, having seen each change in full. |
| `MATERIAL_ADVERSE_CHANGE` | At least one area changed for the worse (a quoted finding every validator's reader shares), or a watched area disappeared entirely. Outranks `UNDETERMINED`: one confirmed adverse change is decisive. |
| `UNDETERMINED` | The live page couldn't be read or came back incomplete (a block page has none of the clauses — that's "couldn't read", not "every clause deleted"), or an area couldn't be settled. |

`is_safe(watch_id, max_age_seconds)` is true only for a fresh `UNCHANGED` or `CHANGED_NOT_ADVERSE`.

## Equivalence principle

A custom leader/validator pair (`gl.vm.run_nondet`):

- **Registration:** exact agreement on the archived capture's facts — capture time, original URL, and every baseline sentence stored.
- **Checks — deterministic facts:** exact agreement on everything plain code derives from the live page, including (via a digest) the full changed wording each reader is shown. The record stores per-area previews and the digest; the full wording is reproducible from the archive and the issuer's page.
- **Checks — the reader:** agreement on the **decision a treasury acts on** (the overall verdict), plus: every area the leader calls adverse must be adverse to every validator's own reader, and every quote must be verbatim in every validator's own copy. Areas shown as `NEUTRAL` under a `MATERIAL_ADVERSE_CHANGE` verdict are the leader's reading; they don't change the outcome.
- **The verdict is never taken from the leader** — it's recomputed from the agreed facts and readings.

The consensus-boundary tests (`tests/test_terms_shift.py`, section 4) show validators rejecting: a leader hiding an adverse change, a quote not in the validator's copy, an adverse finding the validator's reader doesn't share (even when the overall verdict wouldn't change), tampered facts or digest, missing or malformed readings, and a registration with a single altered baseline sentence or capture time.

## What this proves — and what it doesn't

| It proves | It does not prove |
|---|---|
| The issuer's current published terms, in six named clause areas, compared with a specific archived version of the same page | Anything about the issuer's actual reserves, solvency, or conduct |
| That a committee of validators agreed on which areas changed, and on whether each change is adverse, with verbatim quotes for every adverse finding | That the terms are legally enforceable, or how a court would read them |
| That an archived baseline is the exact capture of the same URL | Anything about clauses outside the six watched areas (sanctions lists, prohibited uses, dispute resolution) |
| | That the issuer hasn't changed other documents the terms incorporate by reference |

This is not legal advice; it's an early-warning signal a treasury can wire into a contract and a person can audit.

## Using it from another contract

`contracts/treasury_policy.py` is a deployed, working example: a treasury allocation reverts unless the venue's terms are verified safe and fresh.

```python
terms = gl.contract.get_at(self.termsshift_address)
if not terms.view().is_safe(watch_id, self.max_age_seconds):
    raise gl.vm.UserError("terms not verified safe")
```

Live: allocations to Circle succeeded; the allocation to Tether reverted with `allocation to 'tether-since-2023' blocked: …` (CONTRACT.md).

| Method | |
|---|---|
| `register_watch(watch_id, live_url, baseline_timestamp, label)` | Permissionless; immutable; refused unless the archive capture is exact and of the same page. |
| `check(watch_id)` | Permissionless fresh comparison against the live page. |
| `is_safe(watch_id, max_age_seconds)` | The consumer view. |
| `latest_check` / `latest_verdict` / `get_check` / `get_checks(offset, limit)` | Full history: verdict, per-area labels, previews, quotes. |
| `get_watch` / `list_watches` / `watched_areas` / `get_state` | |

## Testing

```bash
python3 -m venv .venv && .venv/bin/pip install genlayer-test==0.29.2 genvm-linter==0.11.0 pytest
python3 scripts/fetch_fixtures.py             # downloads the pinned archive captures (sha256-verified)
.venv/bin/pytest tests -q                     # 44 tests
python3 scripts/mutation_check.py             # 30/30 mutations killed
.venv/bin/genvm-lint check contracts/terms_shift.py
```

- **Real documents, not redistributed.** The tests run on four Internet Archive captures of Circle's and Tether's terms, pinned by timestamp and SHA-256 in `tests/fixtures/manifest.json` and downloaded by `scripts/fetch_fixtures.py` — this repo doesn't republish anyone's legal text. The hashes equal what GenVM's own fetcher received live (`research/`), so tests run on the bytes validators see.
- **Real changes are the test cases**: Circle's rename (not adverse), Tether's rewrite (adverse), an identical recent capture (unchanged). Synthetic cases edit one element of a real page — cutting the freezing paragraphs (`REMOVED`), a block page, an archive redirect.
- **Bugs the real pages caught before deployment**: Circle's navigation menu contains "MiCA Redemption Policy" (now filtered: paragraphs must be sentences); "Circle **reserves the right**" matched the reserves area (excluded); Tether writes "February 26**th**, 2026"; an unanchored test mock let an archive URL — which *ends with* the live URL — be served the live page.
- **Mutation check.** `tests/mutations.txt` lists 30 deliberate breakages, each removing one safety property; `scripts/mutation_check.py` applies each and confirms the suite fails. All 30 are caught.
- TreasuryPolicy's cross-contract call can't run in genlayer-test's Direct Mode (no glsim hook) — it's proven live instead, both an allowed and a reverted allocation.
- `contracts/*.py` are the tested sources (GenVM v0.2.11); `contracts/*_studio_next.py` are mechanical ports (`scripts/port_to_studio_next.py`), and the on-chain code is byte-identical to them (`studio-next/verify_code.ts`).

## Known limitations

- **Only pages that serve their terms in plain HTML can be watched.** Circle and Tether do; on the day this was built, Coinbase's and Crypto.com's terms pages answered 403 and Kraken's and Gemini's served no terms text in their HTML (checked with a plain HTTP fetch before building — `research/`). An unreadable live page is `UNDETERMINED`, never "unchanged".
- **The baseline must exist in the Internet Archive.** That's the price of a baseline nobody can fabricate.
- **Six clause areas, keyword-routed.** A clause about redemption that never uses the words "redeem" or "redemption" isn't watched; a sentence matching several areas is read in each. Paragraph routing keeps continuations ("…(b) EUR₮ … effective as of November 27, 2025") with their clause.
- **Long rewrites can't be cleared.** A change larger than one reader call can be found adverse, but never "not adverse" — it stays `UNDETERMINED`. Fail-closed by design, at the cost of some `UNDETERMINED` areas on wholesale rewrites.
- **Validators read the live page at slightly different moments.** If the issuer edits its terms mid-check, validators disagree and the round rotates rather than recording a mixed reading.
- **Availability is never traded for safety.** Anyone can pay for a fresh check, and the latest check wins. If a source is momentarily unreachable, that check records `UNDETERMINED` (or fails and records nothing), and consumers fail closed until the next good check. A griefer can make a good verdict temporarily unavailable, never a bad one look good, and the next check restores it.
- **Prompt injection.** The issuer controls the text the reader reads, so an issuer who wanted to hide an adverse change could try to plant an instruction in a clause. The mitigations are: everything between the markers is framed as untrusted data; the question per area is narrow; "not adverse" counts only if the reader saw the whole change; and an unchanged area is decided by plain code with no LLM at all. These are mitigations, not a guarantee.
- **Watch ids are first-come, and TreasuryPolicy is a demonstration.** Anyone can register a `watch_id` before you with different parameters; read the immutable record (`get_watch`) and pin what you expect. `TreasuryPolicy.allocate` is owner-only and takes the owner's chosen id, to show the gate; a production treasury would fix one watch per venue.

## Repository layout

```
contracts/terms_shift.py                 tested source (GenVM v0.2.11)
contracts/terms_shift_studio_next.py     deployed port (Studio Next)
contracts/treasury_policy*.py            consumer contract + port
tests/                                   Direct Mode tests, capture manifest, mutations.txt
scripts/                                 capture fetch, port, mutation check
studio-next/                             deploy, schema check, live proof (prove.ts, live_proof.json), verify_code.ts
research/                                pre-build probes: what GenVM can fetch, headers, archive behaviour
```
