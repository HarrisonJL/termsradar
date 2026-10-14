// Reproducible live proof for TermsShift + TreasuryPolicy. Every step's tx
// hash, result and the contract's recorded output are appended to
// live_proof.json - the source for CONTRACT.md's tables.
//
//   npx tsx prove.ts <termsshift address> <treasurypolicy address> <step>
//   steps: register | check | refuse | allocate | read   (optional 4th arg: one watch_id)
import * as fs from "fs";
import { client, readClient, write, safeJson } from "./lib";

const CIRCLE = "https://www.circle.com/legal/usdc-terms";
const TETHER = "https://tether.to/en/legal/";
const WATCHES: [string, string, string, string][] = [
  ["circle-since-2024", CIRCLE, "20241103153936", "Circle USDC Terms vs the version in force Oct 2024"],
  ["circle-since-2026", CIRCLE, "20261002182005", "Circle USDC Terms vs the version captured 2 Oct 2026"],
  ["tether-since-2023", TETHER, "20240915223352", "Tether Terms vs the version in force Dec 2023"],
];

function log(entry: Record<string, unknown>) {
  const all = fs.existsSync("live_proof.json") ? JSON.parse(fs.readFileSync("live_proof.json", "utf-8")) : [];
  all.push(entry);
  fs.writeFileSync("live_proof.json", JSON.stringify(all, null, 1));
}

async function main() {
  const [ts, tp, step, only] = process.argv.slice(2);
  const watches = WATCHES.filter(([id]) => !only || id === only);
  const c = client();
  const r = readClient();
  const votes = (tx: any) => tx.last_round?.validator_votes_name ?? [];

  if (step === "register") {
    for (const [id, live, stamp, label] of watches) {
      const { hash, tx } = await write(c, ts, "register_watch", [id, live, stamp, label]);
      const w = JSON.parse(safeJson(await r.readContract({ address: ts, functionName: "get_watch", args: [id] })));
      log({ step: "register", watch_id: id, tx: hash, result: tx.txExecutionResultName, votes: votes(tx), watch: w });
      console.log(`  ${id}: baseline last updated ${w.baseline_last_updated}, areas ${safeJson(w.baseline_area_sentences)}`);
    }
  } else if (step === "check") {
    for (const [id] of watches) {
      const { hash, tx } = await write(c, ts, "check", [id]);
      const chk = JSON.parse(safeJson(await r.readContract({ address: ts, functionName: "latest_check", args: [id] })));
      log({ step: "check", watch_id: id, tx: hash, result: tx.txExecutionResultName, votes: votes(tx), check: chk });
      console.log(`  ${id}: ${chk.verdict} ${safeJson(chk.reasons)} labels=${safeJson(chk.labels)}`);
      for (const [area, rd] of Object.entries<any>(chk.readings ?? {})) {
        console.log(`     ${area}: ${safeJson(rd)}`);
      }
    }
  } else if (step === "refuse") {
    // A timestamp the archive has no exact capture for: it would silently
    // serve the nearest capture - a different document. Must be refused.
    const { hash, tx } = await write(c, ts, "register_watch", ["tether-inexact", TETHER, "20240915000000", "inexact capture"]);
    log({ step: "refuse", watch_id: "tether-inexact", tx: hash, result: tx.txExecutionResultName, votes: votes(tx) });
  } else if (step === "allocate") {
    for (const [id, amount] of [["circle-since-2024", 1000000], ["tether-since-2023", 1000000], ["circle-since-2026", 250000]] as [string, number][]) {
      const { hash, tx } = await write(c, tp, "allocate", [id, amount]);
      const total = await r.readContract({ address: tp, functionName: "total_for", args: [id] });
      log({ step: "allocate", watch_id: id, amount, tx: hash, result: tx.txExecutionResultName, votes: votes(tx), total_after: String(total) });
      console.log(`  allocate(${id}, ${amount}) -> ${tx.txExecutionResultName}, total now ${total}`);
    }
  } else if (step === "read") {
    for (const [id] of WATCHES) {
      for (const maxAge of [86400, 1]) {
        const safe = await r.readContract({ address: ts, functionName: "is_safe", args: [id, maxAge] });
        console.log(`  is_safe(${id}, ${maxAge}) = ${safe}`);
        log({ step: "read", call: `is_safe(${id}, ${maxAge})`, value: safe });
      }
    }
    console.log("  TreasuryPolicy config:", safeJson(await r.readContract({ address: tp, functionName: "get_config", args: [] })));
  }
  process.exit(0);
}

main().catch((e) => {
  console.error(e?.shortMessage ?? e?.message ?? e);
  process.exit(1);
});
