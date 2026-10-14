# Dependencies

TermsRadar depends on exactly one contract, and its complete source is included here so the whole trust path can be reviewed inside this repository (see [`TRUST_PATH.md`](../TRUST_PATH.md)).

| | |
|---|---|
| Contract | **TermsShift** |
| What it does for the radar | Every validator fetches an issuer's live terms and an archived baseline, plain code parses and diffs six clause areas, an LLM reads only the changed wording (a finding counts only with a verbatim quote), and the validators must reach consensus. TermsRadar reads the resulting record with a cross-contract view call. |
| Upstream | [github.com/HarrisonJL/termsshift](https://github.com/HarrisonJL/termsshift), commit `537fa84d557ef0d65aeeec401a233948477e7628` |
| Included as | [`termsshift/`](termsshift/): every tracked file of that commit, none edited (contracts, tests, scripts, live-proof tooling, its README and CONTRACT.md, its MIT licence) |
| Deployed at | [`0x0eF30bA1a5B015721A6Ca0989DA68E119bD11c69`](https://explorer-studio-dev.genlayer.com/address/0x0eF30bA1a5B015721A6Ca0989DA68E119bD11c69), deploy tx [`0xea52e074…`](https://explorer-studio-dev.genlayer.com/tx/0xea52e074f80bd1d8faa55c78c9d15020f3ef48e47228d1a5e804a6e34f6d3c72) |
| Deployed file | `termsshift/contracts/terms_shift_studio_next.py`, SHA-256 `72dcd10612b9b43c3e8bb667274467591cebb17b3f22d20f294c6ab36da7f1c3`, byte-identical to the code on-chain |

## Verifying

```bash
# offline: the included file is the one recorded above, and the radar's assumptions about it hold
.venv/bin/pytest tests/test_trust_path.py -q

# against the chain: fetch the code deployed at that address and compare it with the included file
cd studio-next && npm ci && npx tsx verify_dependency.ts

# the dependency's own tests (44; it first downloads its pinned archive captures, checked by SHA-256)
cd dependencies/termsshift && python3 scripts/fetch_fixtures.py && ../../.venv/bin/pytest tests -q
```

TermsShift is MIT-licensed and was published earlier as a project of its own; including it here changes nothing about its licence.
