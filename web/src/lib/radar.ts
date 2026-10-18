import { view, type Signer } from "./genlayer";
import RADAR_CODE from "./terms_radar_studio_next.py?raw";
import SNAPSHOT from "../snapshot.json";

// The official radar (the deployment proven in CONTRACT.md) and the TermsShift oracle it reads.
export const RADAR = "0x5f5ce46A8096920B177914d119C1Af048C29BE71";
export const SHIFT = "0x0eF30bA1a5B015721A6Ca0989DA68E119bD11c69";

/** The audited contract source, byte-identical to contracts/terms_radar_studio_next.py (a test enforces it). */
export const RADAR_SOURCE: string = RADAR_CODE;
/** What a visitor's own desk is constructed with: the same oracle, a day's freshness, half the cap after a sign-off. */
export const DESK_ARGS = [SHIFT, 86400, 50] as const;

export type Posture =
  | "CLEAR" | "CHANGED" | "ADVERSE_ACKNOWLEDGED" | "ADVERSE_UNACKNOWLEDGED" | "UNDETERMINED" | "STALE" | "NO_CHECK" | "UNKNOWN_VERDICT";

export const POSTURE_NAME: Record<string, string> = {
  CLEAR: "Clear", CHANGED: "Changed, not adverse", ADVERSE_ACKNOWLEDGED: "Adverse, signed off", ADVERSE_UNACKNOWLEDGED: "Adverse, not signed off",
  UNDETERMINED: "Undetermined", STALE: "Stale check", NO_CHECK: "No check", UNKNOWN_VERDICT: "Unknown verdict",
};
export const POSTURE_TONE: Record<string, "ok" | "warn" | "bad" | "none" | "info"> = {
  CLEAR: "ok", CHANGED: "info", ADVERSE_ACKNOWLEDGED: "warn", ADVERSE_UNACKNOWLEDGED: "bad", UNDETERMINED: "none", STALE: "none", NO_CHECK: "none", UNKNOWN_VERDICT: "none",
};
export const POSTURE_RULE: Record<string, string> = {
  CLEAR: "TermsShift's latest check found the issuer's terms unchanged since the baseline.",
  CHANGED: "The terms changed, and every change was read in full and judged not adverse to holders.",
  ADVERSE_ACKNOWLEDGED: "A material adverse change that the owner has read and signed off on-chain, for exactly this wording.",
  ADVERSE_UNACKNOWLEDGED: "A material adverse change nobody has signed off. Nothing may be allocated until the owner reads it and signs.",
  UNDETERMINED: "The latest check could not settle every area. Nothing may be allocated.",
  STALE: "The latest check is older than this radar allows. Run a fresh one.",
  NO_CHECK: "TermsShift has never checked this issuer.",
};
export const LADDER_ORDER = ["CLEAR", "CHANGED", "ADVERSE_ACKNOWLEDGED", "ADVERSE_UNACKNOWLEDGED", "UNDETERMINED", "STALE", "NO_CHECK"];

export const AREAS = ["redemption", "suspension", "freezing", "reserves", "fees", "amendment"];

export type Config = {
  owner: string; shift_address: string; max_age_seconds: number; acknowledged_pct: number;
  tracked_count: number; acknowledgement_count: number; allocation_count: number;
};
export type Ack = {
  ack_id: number; watch_id: string; check_id: number; verdict: string; change_digest: string; note: string;
  acknowledged_by: string; acknowledged_at: string; current?: boolean;
};
export type Status = {
  watch_id: string; tracked: boolean; label: string; posture: Posture; allowed_pct: number; reason: string;
  cap: string; allocated: string; limit: string; available: string; check_id: number | null; verdict: string;
  checked_at: string; age_seconds: number | null; acknowledgement: Ack | null;
};
export type Allocation = {
  allocation_id: number; watch_id: string; amount: string; posture: string; allowed_pct: number; check_id: number;
  allocated_by: string; allocated_at: string;
};
export type Watch = { watch_id: string; label: string; live_url: string; baseline_timestamp: string; check_count: number };
export type Rules = { max_age_seconds: number; ladder: Record<string, number>; min_note_length: number };
export type RadarData = {
  address: string; config: Config; rules: Rules; statuses: Status[]; acks: Ack[]; allocations: Allocation[]; watches: Watch[]; loadedAt: Date;
  /** True for the read bundled with the site at build time (src/snapshot.json), never for a live or cached read. */
  snapshot?: boolean;
};

export const same = (a: string, b: string) => a.toLowerCase() === b.toLowerCase();
export const isOwner = (signer: Signer | null, data: RadarData | null) => !!signer && !!data && same(signer.address, data.config.owner);

// --- Reads ---------------------------------------------------------------------

const CACHE = "termsradar-cache-v1:";
type Cached = Omit<RadarData, "loadedAt"> & { loadedAt: string };
export function cachedRadar(address: string): RadarData | null {
  try {
    const c = JSON.parse(localStorage.getItem(CACHE + address.toLowerCase()) ?? "null") as Cached | null;
    return c ? { ...c, loadedAt: new Date(c.loadedAt) } : null;
  } catch { return null; }
}

/** The official radar as it was read when this site was built (scripts/snapshot.ts). */
export function snapshotRadar(address: string): RadarData | null {
  const s = SNAPSHOT as unknown as Cached;
  return same(address, s.address) ? { ...s, loadedAt: new Date(s.loadedAt), snapshot: true } : null;
}

/** What to show before a live read arrives, or if the chain cannot be read: this browser's last read, or the build's snapshot, whichever is newer. */
export function fallbackRadar(address: string): RadarData | null {
  const cached = cachedRadar(address), snap = snapshotRadar(address);
  return cached && (!snap || cached.loadedAt >= snap.loadedAt) ? cached : snap;
}

export async function loadRadar(address: string): Promise<RadarData> {
  const [config, rules, tracked, acks, allocations, watches] = await Promise.all([
    view(address, "get_config") as Promise<Config>,
    view(address, "get_rules") as Promise<Rules>,
    view(address, "list_tracked") as Promise<Array<{ watch_id: string }>>,
    view(address, "get_acknowledgements", [0, 10]) as Promise<Ack[]>,
    view(address, "get_allocations", [0, 10]) as Promise<Allocation[]>,
    view(SHIFT, "list_watches") as Promise<Watch[]>,
  ]);
  const statuses: Status[] = [];
  for (const t of tracked) statuses.push((await view(address, "get_status", [t.watch_id])) as Status);
  const data: RadarData = { address, config, rules, statuses, acks, allocations, watches, loadedAt: new Date() };
  try { localStorage.setItem(CACHE + address.toLowerCase(), JSON.stringify(data)); } catch { /* the cache is optional */ }
  return data;
}

/** TermsShift's latest check of one issuer: per-area labels, the reader's verbatim quotes, the changed wording. */
export type AreaFacts = { status: string; old_preview?: string; new_preview?: string; truncated?: boolean | string };
export type Check = {
  check_id: number; watch_id: string; verdict: string; checked_at: string; submitted_by: string; reasons: string[];
  labels: Record<string, string>;
  readings: Record<string, { adverse: boolean; evidence: string | null; grounded: boolean }>;
  facts: { areas: Record<string, AreaFacts>; baseline_last_updated?: string; live_last_updated?: string; baseline_capture?: string; as_of?: string };
};
export const loadCheck = (watchId: string): Promise<Check> => view(SHIFT, "latest_check", [watchId]);

// --- Desk storage: a visitor's own radar, deployed from their own account ----------------

const DESK = "termsradar-desk";
export function savedDesk(): { address: string; owner: string } | null {
  try {
    const d = JSON.parse(localStorage.getItem(DESK) ?? "null");
    return d && /^0x[0-9a-fA-F]{40}$/.test(d.address) ? d : null;
  } catch { return null; }
}
export function saveDesk(d: { address: string; owner: string } | null): void {
  try { d ? localStorage.setItem(DESK, JSON.stringify(d)) : localStorage.removeItem(DESK); } catch { /* ignore */ }
}

/** The address a deploy transaction created. */
export function deployedAddress(tx: any): string {
  const a = tx?.to_address ?? tx?.recipient ?? tx?.data?.contract_address ?? tx?.txData?.contract_address;
  if (typeof a !== "string" || !/^0x[0-9a-fA-F]{40}$/.test(a)) throw new Error("the transaction did not report a contract address");
  return a;
}

// --- Validation, mirroring the contract so a refused call is not paid for --------------

export const MIN_NOTE = 20, MAX_NOTE = 400;
export function noteProblem(note: string): string {
  const n = note.trim().length;
  return n >= MIN_NOTE && n <= MAX_NOTE ? "" : `The note must say what was decided: ${MIN_NOTE}-${MAX_NOTE} characters (now ${n}).`;
}
export function amountProblem(raw: string, max?: bigint): string {
  if (!/^[1-9][0-9]{0,30}$/.test(raw.trim().replace(/,/g, ""))) return "Enter a positive whole number.";
  if (max !== undefined && BigInt(raw.trim().replace(/,/g, "")) > max) return `More than the ${max.toLocaleString()} available.`;
  return "";
}
export const toUnits = (raw: string): bigint => BigInt(raw.trim().replace(/,/g, ""));

// --- Binding a write to the record THIS transaction created --------------------------------
// Each compares contract state before and after, and the sender: never "the latest record".

export async function shiftCheckCount(): Promise<number> {
  return Number((await view(SHIFT, "get_state")).check_count);
}
export async function boundCheck(before: number, signer: Signer, watchId: string): Promise<Check> {
  const c = await loadCheck(watchId);
  if (!(Number(c.check_id) >= before)) throw new Error("no new check was recorded for this issuer");
  if (!same(c.submitted_by ?? "", signer.address)) throw new Error("the newest check was submitted by someone else");
  return c;
}
export async function boundAck(radar: string, before: number, signer: Signer, watchId: string): Promise<Ack> {
  const acks = (await view(radar, "get_acknowledgements", [0, 5])) as Ack[];
  const a = acks.find((x) => x.ack_id >= before && x.watch_id === watchId && same(x.acknowledged_by, signer.address));
  if (!a) throw new Error("no new sign-off by this account was found");
  return a;
}
export async function boundAllocation(radar: string, before: number, signer: Signer, watchId: string): Promise<Allocation> {
  const list = (await view(radar, "get_allocations", [0, 5])) as Allocation[];
  const a = list.find((x) => x.allocation_id >= before && x.watch_id === watchId && same(x.allocated_by, signer.address));
  if (!a) throw new Error("no new allocation by this account was found");
  return a;
}
export async function boundTracked(radar: string, watchId: string): Promise<{ watch_id: string; cap: string }> {
  const list = (await view(radar, "list_tracked")) as Array<{ watch_id: string; cap: string }>;
  const t = list.find((x) => x.watch_id === watchId);
  if (!t) throw new Error("the issuer is not tracked");
  return t;
}
