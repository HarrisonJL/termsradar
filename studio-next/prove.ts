// Reproducible live proof for TermsRadar. Every step's tx hash, result, votes and the
// contract's recorded output are appended to live_proof.json - the source for CONTRACT.md's
// tables. Steps already in live_proof.json are skipped and each run stops at a time budget,
// so a stall costs nothing: run the same command again.
//
//   npx tsx prove.ts <termsradar> <termsshift> <phase>
//   phases: setup | check | ladder | read
import * as fs from "fs";
import { client, readClient, write, safeJson } from "./lib";

const WATCHES: [string, string][] = [
  ["circle-since-2026", "Circle's USDC terms against the version captured on 2 October 2026: unchanged"],
  ["circle-since-2024", "Circle's USDC terms against October 2024: two areas changed (blacklisting became blocklisting), read as not adverse"],
  ["tether-since-2023", "Tether's terms against December 2023: all six areas changed, five judged adverse"],
];
const CAP = 1_000_000n;
const NOTE = "Reviewed Tether's change against Dec 2023: redemption minimums, no segregation of reserves, wide suspension and freezing rights. Accepted at half the cap.";

type Step = { id: string; kind: "track" | "refused-track" | "ack" | "allocate" | "recheck" | "status"; args: any[]; note: string };

function load(): any[] {
  return fs.existsSync("live_proof.json") ? JSON.parse(fs.readFileSync("live_proof.json", "utf-8")) : [];
}
function log(entry: Record<string, unknown>) {
  const all = load();
  all.push(entry);
  fs.writeFileSync("live_proof.json", JSON.stringify(all, null, 1));
}
const done = (id: string) => load().some((e) => e.id === id);

function revertMessage(tx: any): string {
  const found: string[] = [];
  const walk = (o: any) => {
    if (typeof o === "string") {
      const m = o.match(/(already tracked|[^\n"]*refused: [^\n"]*|nothing to acknowledge[^\n"]*|the note must say[^\n"]*|only the owner[^\n"]*|amount must[^\n"]*|cap must[^\n"]*)/);
      if (m) found.push(m[0]);
    } else if (o && typeof o === "object") Object.values(o).forEach(walk);
  };
  walk(tx);
  return found[0] ?? "";
}

async function main() {
  const [radar, shift, phase] = process.argv.slice(2);
  const c = client();
  const r = readClient();
  const votes = (tx: any) => tx.last_round?.validator_votes_name ?? [];
  const started = Date.now();
  const outOfTime = () => Date.now() - started > 330_000;
  const view = async (address: string, fn: string, args: unknown[] = []) => {
    await new Promise((res) => setTimeout(res, 2200));
    return JSON.parse(safeJson(await r.readContract({ address, functionName: fn, args })));
  };
  const stop = () => console.log("  (time budget reached - run this phase again to continue)");
  const status = async (id: string) => {
    const s = await view(radar, "get_status", [id]);
    console.log(`     ${id}: ${s.posture} ${s.allowed_pct}% available ${s.available}${s.acknowledgement ? " | signed off, current=" + s.acknowledgement.current : ""}`);
    return s;
  };

  const run = async (s: Step) => {
    if (s.kind === "recheck") {
      const { hash, tx } = await write(c, shift, "check", s.args);
      const chk = await view(shift, "latest_check", s.args);
      const st = await status(s.args[0]);
      log({ id: s.id, step: "recheck", args: s.args, note: s.note, tx: hash, result: tx.txExecutionResultName, votes: votes(tx),
            check: { check_id: chk.check_id, verdict: chk.verdict, checked_at: chk.checked_at, labels: chk.labels }, status: st });
      return;
    }
    const call = s.kind === "track" || s.kind === "refused-track" ? "track" : s.kind === "ack" ? "acknowledge" : "allocate";
    const args = call === "track" ? [s.args[0], BigInt(s.args[1])] : call === "allocate" ? [s.args[0], BigInt(s.args[1])] : s.args;
    const { hash, tx } = await write(c, radar, call, args);
    const message = tx.txExecutionResultName === "FINISHED_WITH_ERROR" ? revertMessage(tx) : "";
    const st = await view(radar, "get_status", [s.args[0]]);
    log({ id: s.id, step: call, args: s.args.map(String), note: s.note, tx: hash, result: tx.txExecutionResultName, votes: votes(tx), revert: message, status: st });
    console.log(`  ${call}(${s.args.map(String).join(", ").slice(0, 60)}) -> ${tx.txExecutionResultName} ${message}`);
  };

  let steps: Step[] = [];
  if (phase === "setup") {
    steps = WATCHES.map(([id, note]) => ({ id: "track-" + id, kind: "track" as const, args: [id, CAP.toString()], note: "tracking: " + note }));
    steps.push(
      { id: "refuse-track-twice", kind: "refused-track", args: ["tether-since-2023", CAP.toString()], note: "an issuer tracked twice" },
      { id: "refuse-track-unknown", kind: "refused-track", args: ["no-such-watch", CAP.toString()], note: "a watch TermsShift has never heard of" },
      { id: "refuse-ack-clear", kind: "ack", args: ["circle-since-2026", NOTE], note: "acknowledging an issuer whose terms have not changed" },
      { id: "refuse-ack-short", kind: "ack", args: ["tether-since-2023", "ok"], note: "a sign-off with no real note" },
    );
  } else if (phase === "check") {
    steps = WATCHES.map(([id, note]) => ({ id: "check-" + id, kind: "recheck" as const, args: [id], note: "TermsShift reads the issuer's live terms (fresh, so the radar's age limit holds): " + note }));
  } else if (phase === "ladder") {
    steps = [
      { id: "alloc-clear", kind: "allocate", args: ["circle-since-2026", "900000"], note: "unchanged terms: 100% of the cap is available" },
      { id: "alloc-clear-over", kind: "allocate", args: ["circle-since-2026", "200000"], note: "100,000 is left of the cap: refused" },
      { id: "alloc-changed", kind: "allocate", args: ["circle-since-2024", "500000"], note: "changed but read in full as not adverse: still 100%" },
      { id: "alloc-adverse-unsigned", kind: "allocate", args: ["tether-since-2023", "100000"], note: "a material adverse change nobody has signed off: nothing is allowed" },
      { id: "ack-tether", kind: "ack", args: ["tether-since-2023", NOTE], note: "the owner reads the change and signs it off on-chain, with a note" },
      { id: "alloc-adverse-signed", kind: "allocate", args: ["tether-since-2023", "400000"], note: "signed off: 50% of the cap (500,000) is available" },
      { id: "alloc-adverse-over", kind: "allocate", args: ["tether-since-2023", "200000"], note: "400,000 is used, 100,000 left: refused" },
      { id: "recheck-tether", kind: "recheck", args: ["tether-since-2023"], note: "TermsShift checks Tether again: the same wording, so the sign-off still holds" },
      { id: "alloc-after-recheck", kind: "allocate", args: ["tether-since-2023", "100000"], note: "after the re-check the sign-off still applies: the last 100,000 is allowed" },
    ];
  } else if (phase === "read") {
    const out: Record<string, any> = {};
    for (const [id] of WATCHES) out[id] = await status(id);
    const acks = await view(radar, "get_acknowledgements", [0, 20]);
    const allocations = await view(radar, "get_allocations", [0, 20]);
    const config = await view(radar, "get_config");
    if (!done("read")) log({ id: "read", step: "read", status: out, acknowledgements: acks, allocations, config });
    return process.exit(0);
  }
  for (const s of steps) {
    if (done(s.id)) continue;
    if (outOfTime()) return stop();
    await run(s);
  }
  process.exit(0);
}

main().catch((e) => {
  console.error(e?.shortMessage ?? e?.message ?? e);
  process.exit(1);
});
