# Research: what TermsRadar reads, and what had to be proven live

TermsRadar has no data source of its own. Everything it knows about an issuer comes from [TermsShift](https://github.com/HarrisonJL/termsshift), read as a **cross-contract view** at the moment of each call. What follows are the facts that shaped the design.

## What TermsShift's check record offers

A check (`latest_check(watch_id)`) carries, among other things (fixtures: [`tests/fixtures/`](../tests/fixtures/), captured from the live contract):

- `verdict`: `UNCHANGED`, `CHANGED_NOT_ADVERSE`, `MATERIAL_ADVERSE_CHANGE`, `UNDETERMINED` (or `NONE` before any check);
- `checked_at`: the transaction time of the check, so a consumer can judge how old it is;
- `facts.areas[<area>]`: for each of six clause areas its status (`UNCHANGED`, `CHANGED`, ...), the previews of old and new wording, and an **`excerpt_digest`**, the SHA-256 of the changed wording **as every validator agreed it** (the validators must reproduce it exactly to reach consensus);
- `labels` and `readings`: the per-area judgement and the reader's verbatim quote.

The `excerpt_digest` is what makes a sign-off bindable. The radar's own digest is a SHA-256 of `{area: [status, excerpt_digest]}` for every area that is not `UNCHANGED`, with sorted keys. It does **not** include anything an LLM may say differently from one run to the next (the labels, the quotes): the tests change those and show the digest does not move, and change a status, a wording digest, or the set of areas and show it does. Two checks of the same unchanged-since-then wording therefore give the same digest, however many checks have happened in between; the official radar and a visitor's desk produce the identical digest for Tether's change (`a92c525b…`).

## What can and cannot be tested without a chain

Direct Mode (genlayer-test) cannot simulate a cross-contract call, so the radar is split: every rule is a **pure function** of a check record (`_posture`, `_change_digest`, `_limit`, `_available`), tested on the three real check records (Circle unchanged, Circle changed-not-adverse, Tether adverse) and on edited copies of them; the calls that read TermsShift (`track`, `acknowledge`, `allocate`, `get_status`) are proven by live transactions (CONTRACT.md). The mutation check (`tests/mutations.txt`) covers the pure rules; mutants of the cross-contract lines are covered by the live proof, not claimed as unit-tested.

## Things the live runs established

- A **view can read another contract's view** (`get_status` reads TermsShift's `latest_check`), and so can a write; both were exercised on the deployed radar.
- Amounts are `u256` and must be passed as `BigInt` from genlayer-js; views return them as strings, because GenVM calldata cannot carry big integers as numbers and a view must never return a float.
- A **deployed contract can be created from a browser**, by a wallet or a throwaway account, from the contract source alone: the app's "Create my desk" does that, and the resulting on-chain code was compared byte for byte with the repository's port.
- The rate limit of the public RPC (30 reads a minute per client) shapes the app, which paces its own reads (see `web/src/lib/genlayer.ts`).
