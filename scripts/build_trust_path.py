"""
Writes TRUST_PATH.md: the end-to-end path from an issuer's published terms to an allocation, with line references
into the vendored dependency and transaction hashes taken from studio-next/live_proof.json and the dependency's own
CONTRACT.md, so nothing here is transcribed by hand.   python3 scripts/build_trust_path.py
"""
import json
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parent.parent
X = "https://explorer-studio-dev.genlayer.com"
DEP = "dependencies/termsshift/contracts/terms_shift_studio_next.py"
RAD = "contracts/terms_radar_studio_next.py"
L = json.loads((REPO / "studio-next" / "live_proof.json").read_text())
D = json.loads((REPO / "studio-next" / "deployment.json").read_text())
dep_src = (REPO / DEP).read_text().splitlines()
rad_src = (REPO / RAD).read_text().splitlines()


def line(src, pattern, nth=0):
    hits = [i + 1 for i, s in enumerate(src) if re.search(pattern, s)]
    assert len(hits) > nth, f"pattern not found: {pattern}"
    return hits[nth]


def ref(path, n): return f"[`{path.split('/')[-1]}:{n}`]({path}#L{n})"
def tx(h): return f"[`{h[:10]}…`]({X}/tx/{h})"
def votes(v): return f"{v.count('AGREE')} agree" + (f", {v.count('DISAGREE')} disagree" if v.count("DISAGREE") else "")


ln = {
    "fetch": line(dep_src, r"gl\.nondet\.web\.get"),
    "facts": line(dep_src, r"^def _check_facts"),
    "digest": line(dep_src, r"^def _digest"),
    "read": line(dep_src, r"^def _read_area"),
    "prompt": line(dep_src, r"gl\.nondet\.exec_prompt"),
    "grounded": line(dep_src, r"^def _grounded"),
    "label": line(dep_src, r"^def _area_label"),
    "decide": line(dep_src, r"^def _decide"),
    "check": line(dep_src, r"def check\(self, watch_id"),
    "leader": line(dep_src, r"def leader_fn", 1),
    "validator": line(dep_src, r"def validator_fn", 1),
    "nondet": line(dep_src, r"gl\.vm\.run_nondet", 1),
    "record": line(dep_src, r"record\.facts_json"),
    "latest": line(dep_src, r"def latest_check"),
    "list": line(dep_src, r"def list_watches"),
    "r_latest": line(rad_src, r"\.view\(\)\.latest_check"),
    "r_list": line(rad_src, r"\.view\(\)\.list_watches"),
    "r_digest": line(rad_src, r"^def _change_digest"),
    "r_posture": line(rad_src, r"^def _posture"),
    "r_ack": line(rad_src, r"def acknowledge\(self"),
    "r_alloc": line(rad_src, r"def allocate\(self"),
}
dep_md = (REPO / "dependencies" / "termsshift" / "CONTRACT.md").read_text()
regs = {m.group(1): (m.group(2), m.group(3)) for m in re.finditer(r"^\| `([a-z0-9-]+)` \|.*?\[register\]\(([^)]+)\).*?\[check\]\(([^)]+)\)", dep_md, re.M)}
assert regs, "no registration rows found in the vendored CONTRACT.md"
checks = [e for e in L if e["id"].startswith("check-")] + [e for e in L if e["id"] == "recheck-tether"]

o = []
w = o.append
w("# Trust path: from an issuer's published terms to an allocation\n")
w("A reviewer's first question about this project is fair: **where in this repository does anything non-deterministic happen?** "
  "It does not happen in the radar, and that is on purpose. `contracts/terms_radar.py` is a deterministic policy: it has no web access and no LLM, "
  "so it can never be a second, unaudited source of truth about an issuer. Everything that reads the real world, uses a model, and reaches validator consensus "
  "is in **TermsShift**, the contract the radar reads. Its **exact deployed source is included in this repository** under "
  "[`dependencies/termsshift/`](dependencies/termsshift/), so the whole path can be reviewed here, end to end.\n")
w("## The path\n")
w("```")
w("issuer's live terms page          archived baseline (Internet Archive)")
w("            \\                         /      every validator fetches both itself")
w(f"             v                       v       {DEP}:{ln['fetch']}")
w("   TermsShift.check(watch)")
w(f"   - plain code parses six clause areas, diffs against the baseline, hashes the changed wording (excerpt_digest)   :{ln['facts']}, :{ln['digest']}")
w(f"   - an LLM reads ONLY the changed wording; 'adverse' counts only with a verbatim quote found in it                :{ln['read']}, :{ln['prompt']}, :{ln['grounded']}")
w(f"   - consensus: gl.vm.run_nondet; validators must agree EXACTLY on the facts and on the verdict, and every")
w(f"     'adverse' finding must be adverse to the validator's own reader                                              :{ln['leader']}-{ln['nondet']}")
w(f"   - the verdict is recomputed from the agreed facts and readings, never taken from the leader                    :{ln['decide']}, :{ln['record']}")
w("            |")
w(f"            v   stored record: verdict, checked_at, per-area facts incl. excerpt_digest                           :{ln['latest']} (latest_check)")
w("            |")
w("            v   cross-contract VIEW read, at the moment of every call (nothing is cached)")
w(f"   TermsRadar ({RAD})")
w(f"   - reads the record                                                                                            :{ln['r_latest']}")
w(f"   - posture = pure function of the record (CLEAR / CHANGED / ADVERSE_* / UNDETERMINED / STALE / NO_CHECK)       :{ln['r_posture']}")
w(f"   - a sign-off is bound to a digest of what changed (built from TermsShift's excerpt_digest)                    :{ln['r_digest']}, :{ln['r_ack']}")
w(f"   - allocate() refuses unless the posture allows it, reading the record again                                   :{ln['r_alloc']}")
w("```\n")
w("Line numbers are for the files as committed here; `tests/test_trust_path.py` regenerates this document and fails if it has gone stale.\n")
w("## What each stage does, and where it is reviewable\n")
w("| Stage | Non-deterministic? | Who must agree | Code | Tests |\n|---|---|---|---|---|")
w(f"| Fetch the live page and the archived baseline | yes (web) | every validator fetches itself; exact agreement on the facts (via `facts_digest`) | {ref(DEP, ln['fetch'])} | [`dependencies/termsshift/tests/`](dependencies/termsshift/tests/) (44 tests on real captures) |")
w(f"| Parse the six areas and diff | no (plain code) | exact, as above | {ref(DEP, ln['facts'])} | same |")
w(f"| Judge whether a change is adverse | yes (LLM) | the leader's verdict and every adverse area must match each validator's own reader; the quote must be verbatim in each validator's own copy | {ref(DEP, ln['read'])}, {ref(DEP, ln['grounded'])} | consensus-boundary tests in the same suite |")
w(f"| Decide the verdict | no | recomputed after consensus | {ref(DEP, ln['decide'])} | same |")
w(f"| Read the record and set a posture | no (pure) | n/a: a function of one record | {ref(RAD, ln['r_posture'])} | [`tests/test_terms_radar.py`](tests/test_terms_radar.py) on real check records |")
w(f"| Bind a sign-off to the changed wording | no (pure) | n/a | {ref(RAD, ln['r_digest'])} | same, plus mutation checks |\n")
w("## Evidence that it ran: the live transactions\n")
w("Registration of each watch (TermsShift reads the archived baseline and stores its clauses), from the dependency's own live proof ([`dependencies/termsshift/CONTRACT.md`](dependencies/termsshift/CONTRACT.md)):\n")
w("| Watch | Registration | First check |\n|---|---|---|")
for k, (r_url, c_url) in regs.items():
    w(f"| `{k}` | [{r_url.split('/tx/')[1][:10]}…]({r_url}) | [{c_url.split('/tx/')[1][:10]}…]({c_url}) |")
w("\nChecks run during this project's live proof, each a TermsShift transaction that its validators decided before the radar read it ([`CONTRACT.md`](CONTRACT.md), section 2):\n")
w("| Check | Tx | Validators | TermsShift's verdict | Areas it found changed |\n|---|---|---|---|---|")
for e in checks:
    c = e["check"]
    changed = ", ".join(f"{k}: {v}" for k, v in c["labels"].items() if v != "UNCHANGED") or "none"
    w(f"| `{e['args'][0]}` (check {c['check_id']}) | {tx(e['tx'])} | {votes(e['votes'])} | **{c['verdict']}** | {changed} |")
w("")
w("## Identity of the dependency\n")
w("| | |\n|---|---|")
w(f"| TermsShift (deployed) | [`{D['shift']['address']}`]({X}/address/{D['shift']['address']}), deploy tx {tx(D['shift']['deploy_tx'])} |")
w("| Vendored from | [github.com/HarrisonJL/termsshift](https://github.com/HarrisonJL/termsshift), every tracked file at the commit recorded in [`dependencies/README.md`](dependencies/README.md) |")
w("| Deployed file | `dependencies/termsshift/contracts/terms_shift_studio_next.py`, byte-identical to the code on-chain (SHA-256 in `dependencies/README.md`; checked by `tests/test_trust_path.py` and by `studio-next/verify_dependency.ts` against the chain) |\n")
w("## How to review it\n")
w("```bash")
w("# 1. the radar's tests, and the checks that tie it to the vendored dependency")
w(".venv/bin/pytest tests -q")
w("# 2. the dependency's own tests (it needs its pinned archive captures first)")
w("cd dependencies/termsshift && python3 scripts/fetch_fixtures.py && ../../.venv/bin/pytest tests -q")
w("# 3. the vendored code is what is deployed")
w("cd studio-next && npm ci && npx tsx verify_dependency.ts")
w("```")
TEXT = "\n".join(o) + "\n"
if __name__ == "__main__":
    (REPO / "TRUST_PATH.md").write_text(TEXT)
    print("wrote TRUST_PATH.md,", len(o), "lines")
