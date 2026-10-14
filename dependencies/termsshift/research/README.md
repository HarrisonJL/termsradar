# Pre-build research (Studio Next, 2026-10-04)

What GenVM can actually fetch, and how, was checked on the live network before the contract was designed - not assumed. The probe contracts here are throwaway instruments: their validators accept any successful leader result, which is fine for measuring and wrong for anything else.

## Which terms pages can be read at all

A plain HTTP fetch of candidate pages (from a local machine, 2026-10-04):

| Page | Result |
|---|---|
| Circle USDC Terms, EURC Terms | 200, full terms text in the HTML (~12,600 words) |
| Tether Terms | 200, full terms text in the HTML (~12,700 words) |
| Coinbase user agreement, custody agreement; Crypto.com terms | 403 |
| Kraken legal, Gemini user agreement, Paxos USDP terms | 200, but no terms text in the HTML (client-rendered) |
| BitGo, Anchorage, PayPal PYUSD, Ripple RLUSD (URLs tried) | 404 or empty |

So TermsShift targets stablecoin issuers whose terms are served as HTML. Circle's raw HTML differs between two fetches but its extracted text doesn't - hence comparing text, never bytes.

## Probe 1 - `fetch_probe_studio_next.py`

Contract [`0xd5145AE06f6392C522501B0ea3de34047A641359`](https://explorer-studio-dev.genlayer.com/address/0xd5145AE06f6392C522501B0ea3de34047A641359).

| Call | Result on Studio Next |
|---|---|
| [`probe_modules`](https://explorer-studio-dev.genlayer.com/tx/0xf8b27a10868d18b4b94cc0f8cb52445aa7c3c1a539425a110675bbf54e1fdee6) | `difflib`, `gzip`, `zlib`, `unicodedata`, `html` all available |
| [Tether terms](https://explorer-studio-dev.genlayer.com/tx/0xda1bd778cfe1c250aa15377b010dea96e8e30d2bf693e4f2c079d3982d16fa50) | 200, 147,563 bytes |
| [Circle USDC terms](https://explorer-studio-dev.genlayer.com/tx/0x380dbbb8d97997ac9868bf2e0f980d3082a1f9699323bf3072c894de8ec6e88b) | 200, 380,986 bytes |
| [Archive: Tether, 2024-09-15](https://explorer-studio-dev.genlayer.com/tx/0x7157db22735a0231d9713916ae508a413babd73564b47cb5e0eda5ea4ea54be5) | 200, 125,139 bytes, SHA-256 `d60eee0e…` - **already decompressed** (the archive stores this capture gzip-encoded; GenVM's fetcher decodes it) and identical to the test fixture's hash |
| [Archive: Circle, 2024-11-03](https://explorer-studio-dev.genlayer.com/tx/0x5e304c5f13c1ffff4533caba4da15ac9686feb94dedc559d6bfddcedf17aa239) | 200, 210,973 bytes, SHA-256 `396eb7d9…` - identical to the test fixture's hash |
| [`httpbin.org/headers`, default](https://explorer-studio-dev.genlayer.com/tx/0x7eb1197742aa4663e01f3b9ba9b9e309a86a2c4272c40c792b0475e37fc9495e) / [with a custom User-Agent](https://explorer-studio-dev.genlayer.com/tx/0x75b1c262ce33382b0fa8402d7ae28565b47a3660b87aa2bd3984fe29115e1fad) | GenVM sends `User-Agent: reqwest` by default and honours a custom one |

## Probe 2 - `headers_probe_studio_next.py`

Contract [`0xd108d7bc64057015ca3e9d1230D845FceCaa7349`](https://explorer-studio-dev.genlayer.com/address/0xd108d7bc64057015ca3e9d1230D845FceCaa7349).

- [Exact capture](https://explorer-studio-dev.genlayer.com/tx/0xfade5dcf3044956f0716b837f33ec0bff62aa3a616bcb86eb084169f058b714a): response headers are exposed to the contract (lower-cased), including `memento-datetime: Sun, 15 Sep 2024 22:33:52 GMT` and `link: <https://tether.to/en/legal/>; rel="original", …`.
- [Inexact timestamp `20240915000000`](https://explorer-studio-dev.genlayer.com/tx/0x222b2f6cef930c96472a8aaeb08c51d601a7e6c2914e48ce5df15ced0057017e): the archive's 302 redirect is followed silently and the contract receives the *nearest* capture - but its `memento-datetime` still says 22:33:52, which is how TermsShift detects and refuses it.

## Why checks never re-read the archive

An earlier TermsShift deployment (`0xcE241a16543A06781472905e56B3E8c1F457f471`) re-fetched the archived baseline on every check. Its registrations - one archive fetch per validator - worked; the three checks right after them all failed in the leader with `genlayer.nondet.NondetException: SENDING_REQUEST` on the archive fetch, e.g. [`0x8545530d…`](https://explorer-studio-dev.genlayer.com/tx/0x8545530d8d5f3c505dce7b25447d38f8cafbeffae5b62cd32ddd2683eb32d676). The current design reads the archive once, at registration, stores the agreed baseline clauses on-chain, and retries any fetch up to three times.
