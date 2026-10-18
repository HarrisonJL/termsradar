import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { MAX_NOTE, MIN_NOTE, RADAR, RADAR_SOURCE, amountProblem, deployedAddress, fallbackRadar, isOwner, noteProblem, same, snapshotRadar, toUnits } from "./radar";

// The desk a visitor creates must run exactly the code the official radar runs.
const DEPLOYED_SHA256 = "ac50a737edd42187fbef6112472b47b81db829a4fd3552b07aa75ad9a12f9838";
const sha = (s: string) => createHash("sha256").update(s).digest("hex");

describe("the contract the app deploys", () => {
  it("is byte-identical to the code on-chain at the official radar (CONTRACT.md)", () => {
    expect(sha(RADAR_SOURCE)).toBe(DEPLOYED_SHA256);
  });
  it("is byte-identical to contracts/terms_radar_studio_next.py when this app is built inside the repository", () => {
    const repoCopy = new URL("../../../contracts/terms_radar_studio_next.py", import.meta.url);
    if (!existsSync(repoCopy)) return; // built from web/ alone (e.g. a hosting root): the hash above is the check
    expect(readFileSync(repoCopy, "utf-8")).toBe(RADAR_SOURCE);
  });
});

describe("input checks mirror the contract", () => {
  it("a sign-off note is 20-400 characters once trimmed", () => {
    expect(noteProblem("x".repeat(MIN_NOTE - 1))).not.toBe("");
    expect(noteProblem("x".repeat(MIN_NOTE))).toBe("");
    expect(noteProblem("x".repeat(MAX_NOTE))).toBe("");
    expect(noteProblem("x".repeat(MAX_NOTE + 1))).not.toBe("");
    expect(noteProblem("   " + "x".repeat(MIN_NOTE - 1) + "   ")).not.toBe("");
  });
  it("an amount is a positive whole number, and may be capped by what is available", () => {
    for (const bad of ["", "0", "-5", "1.5", "abc", "1e6", " "]) expect(amountProblem(bad)).not.toBe("");
    expect(amountProblem("250,000")).toBe("");
    expect(amountProblem("100", 100n)).toBe("");
    expect(amountProblem("101", 100n)).not.toBe("");
    expect(toUnits("1,500,000")).toBe(1500000n);
  });
  it("u256 arguments are BigInt, never strings or numbers", () => {
    expect(typeof toUnits("5")).toBe("bigint");
  });
});

describe("owner and address handling", () => {
  it("compares addresses without regard to case", () => {
    expect(same("0xAbC", "0xaBc")).toBe(true);
    expect(same("0xAbC", "0xabd")).toBe(false);
  });
  it("is the owner only when the signer is the radar's owner", () => {
    const data: any = { config: { owner: "0x5cdb5699bc1038e115A973bb91A646f7E98C075b" } };
    expect(isOwner({ kind: "temporary", address: "0x5CDB5699BC1038E115A973BB91A646F7E98C075B" }, data)).toBe(true);
    expect(isOwner({ kind: "temporary", address: "0x0000000000000000000000000000000000000001" }, data)).toBe(false);
    expect(isOwner(null, data)).toBe(false);
    expect(isOwner({ kind: "wallet", address: "0x5cdb5699bc1038e115A973bb91A646f7E98C075b" }, null)).toBe(false);
  });
  it("reads a deployed contract's address from the transaction, or refuses to guess", () => {
    const a = "0x31c89cA668Cf19E1dA583f983d77d4848b25522B";
    expect(deployedAddress({ to_address: a })).toBe(a);
    expect(deployedAddress({ recipient: a })).toBe(a);
    expect(() => deployedAddress({})).toThrow();
    expect(() => deployedAddress({ to_address: "0x123" })).toThrow();
  });
});

describe("the outage fallback", () => {
  it("is a snapshot of the official radar, labelled as one, with its own time", () => {
    const s = snapshotRadar(RADAR)!;
    expect(s.snapshot).toBe(true);
    expect(same(s.address, RADAR)).toBe(true);
    expect(s.loadedAt.getTime()).not.toBeNaN();
    expect(s.statuses.length).toBeGreaterThan(0);
  });
  it("is never shown for someone else's desk", () => {
    expect(snapshotRadar("0x0000000000000000000000000000000000000001")).toBeNull();
    expect(fallbackRadar("0x0000000000000000000000000000000000000001")).toBeNull(); // no cache in tests either
  });
  it("gives way to this browser's own read when that is newer", () => {
    const store = new Map<string, string>();
    (globalThis as any).localStorage = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => store.set(k, v), removeItem: (k: string) => store.delete(k) };
    try {
      const snap = snapshotRadar(RADAR)!;
      const newer = { ...snap, snapshot: undefined, loadedAt: new Date(snap.loadedAt.getTime() + 60_000).toISOString() };
      store.set("termsradar-cache-v1:" + RADAR.toLowerCase(), JSON.stringify(newer));
      expect(fallbackRadar(RADAR)!.snapshot).toBeUndefined();
      const older = { ...newer, loadedAt: new Date(snap.loadedAt.getTime() - 60_000).toISOString() };
      store.set("termsradar-cache-v1:" + RADAR.toLowerCase(), JSON.stringify(older));
      expect(fallbackRadar(RADAR)!.snapshot).toBe(true);
    } finally { delete (globalThis as any).localStorage; }
  });
});
