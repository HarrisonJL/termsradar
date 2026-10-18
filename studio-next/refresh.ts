// Keeps the official radar's evidence fresh. The radar counts a TermsShift check older than a day as a
// stale check that allows nothing (it fails closed), so an unattended radar would show every issuer at 0%.
// This asks TermsShift for a fresh check of every issuer the official radar tracks: one consensus
// transaction each, in which every validator reads the issuer's live terms and the archived baseline.
// Checks are permissionless, so it signs with a throwaway testnet account created for this run and funded
// from Studio Next's faucet: no stored key, nothing to leak.
//
//   npx tsx refresh.ts [issuer ...]      (all issuers twice a day, from .github/workflows/refresh.yml)
import * as crypto from "crypto";
import * as fs from "fs";
import { createAccount, createClient, chains } from "genlayer-js";
import { fees, safeJson, waitDecided, EXPLORER } from "./lib";

const chain: any = (chains as any).studioDevnet;
const deployment = JSON.parse(fs.readFileSync(`${__dirname}/deployment.json`, "utf-8"));
const RADAR: string = deployment.radar.address;
const SHIFT: string = deployment.shift.address;
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function rpc(method: string, params: unknown[]) {
  const r = await fetch(chain.rpcUrls.default.http[0], {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
  });
  const j: any = await r.json();
  if (j.error) throw new Error(`${method}: ${j.error.message}`);
  return j.result;
}

async function main() {
  const account = createAccount(`0x${crypto.randomBytes(32).toString("hex")}` as `0x${string}`);
  const c: any = createClient({ chain, account });
  await rpc("sim_fundAccount", [account.address, 100000000000000000000]);
  console.log(`throwaway account ${account.address}, funded from the faucet`);

  // Studio Next allows 30 reads a minute: pace them.
  const view = async (address: string, fn: string, args: unknown[] = []) => {
    await sleep(2200);
    return JSON.parse(safeJson(await c.readContract({ address, functionName: fn, args })));
  };
  const issuers: string[] = (await view(RADAR, "list_tracked")).map((t: any) => t.watch_id);
  console.log(`official radar ${RADAR}: ${issuers.length} issuers`);
  const only = process.argv.slice(2); // optional: refresh just these issuers
  const todo = issuers.filter((m) => only.length === 0 || only.includes(m));

  const failed: string[] = [];
  for (const watch of todo) {
    try {
      const hash = await c.writeContract({ address: SHIFT, functionName: "check", args: [watch], fees: await fees(c) });
      const tx = await waitDecided(c, hash);
      const ok = String(tx.status) === "5" || String(tx.status) === "7";
      const posture = ok ? await view(RADAR, "get_status", [watch]) : null;
      console.log(`${watch}: status ${tx.status} ${tx.txExecutionResultName ?? ""} ${posture ? posture.posture : ""} ${EXPLORER}/tx/${hash}`);
      if (!ok || tx.txExecutionResultName !== "FINISHED_WITH_RETURN") failed.push(watch);
    } catch (e: any) {
      console.log(`${watch}: ${e?.shortMessage ?? e?.message ?? e}`);
      failed.push(watch);
    }
  }
  if (failed.length) {
    console.log(`not refreshed: ${failed.join(", ")}`);
    process.exit(1);
  }
  process.exit(0);
}

main().catch((e) => {
  console.error(e?.shortMessage ?? e?.message ?? e);
  process.exit(1);
});
