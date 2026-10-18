import { useCallback, useEffect, useState } from "react";
import { AccountPanel, Pill, Section, TxPanel } from "./components/ui";
import { addressLink, errorText, onThrottle, short, type Signer } from "./lib/genlayer";
import { duration, fmtTime } from "./lib/format";
import {
  AREAS, DESK_ARGS, LADDER_ORDER, POSTURE_NAME, POSTURE_RULE, POSTURE_TONE, RADAR, RADAR_SOURCE, SHIFT, amountProblem, boundAck,
  boundAllocation, boundCheck, boundTracked, fallbackRadar, deployedAddress, isOwner, loadCheck, loadRadar, noteProblem, same,
  saveDesk, savedDesk, shiftCheckCount, toUnits, type Check, type RadarData, type Status,
} from "./lib/radar";
import { useTransaction } from "./lib/useTransaction";

const n = (s: string | number) => Number(s).toLocaleString();
const ageMs = (iso: string) => Date.now() - new Date(iso).getTime();

function Bar({ s }: { s: Status }) {
  const cap = Number(s.cap) || 1;
  const limit = Math.min(Number(s.limit) / cap, 1) * 100;
  const used = Math.min(Number(s.allocated) / cap, 1) * 100;
  return (
    <div>
      <div className="bar" aria-hidden="true">
        <i className="limit" style={{ width: `${limit}%` }} />
        <i className="used" style={{ width: `${used}%` }} />
      </div>
      <div className="barlab">
        <span>{n(s.allocated)} allocated</span>
        <span>{n(s.available)} available now</span>
        <span>limit {n(s.limit)} of cap {n(s.cap)}</span>
      </div>
    </div>
  );
}

function IssuerCard({ s, selected, onSelect }: { s: Status; selected: boolean; onSelect: () => void }) {
  return (
    <button className="card issuer" aria-pressed={selected} onClick={onSelect}>
      <div className="row">
        <span className="name">{s.label || s.watch_id}</span>
        <Pill tone={POSTURE_TONE[s.posture] ?? "none"}>{POSTURE_NAME[s.posture] ?? s.posture}</Pill>
      </div>
      <div className="sm mono">{s.watch_id}</div>
      <div className="why">{s.checked_at ? `TermsShift: ${s.verdict}, checked ${duration(ageMs(s.checked_at))} ago.` : "TermsShift has not checked this issuer."}</div>
      <Bar s={s} />
    </button>
  );
}

function AreaTable({ check }: { check: Check }) {
  return (
    <div className="tablewrap">
      <table className="list areas">
        <thead><tr><th>Area</th><th>What TermsShift found</th><th>The reader's quote (verified word for word)</th></tr></thead>
        <tbody>
          {AREAS.map((a) => {
            const label = check.labels?.[a] ?? "—";
            const r = check.readings?.[a];
            const f = check.facts?.areas?.[a];
            const tone = label === "ADVERSE" ? "bad" : label === "UNCHANGED" ? "ok" : label === "NEUTRAL" ? "info" : "none";
            return (
              <tr key={a}>
                <td><b>{a}</b></td>
                <td><Pill tone={tone}>{label}</Pill>{f && f.status !== "UNCHANGED" && <div className="sm">{f.status === "CHANGED" ? "wording changed" : f.status}</div>}</td>
                <td>{r?.evidence ? <q>{r.evidence.length > 280 ? r.evidence.slice(0, 280) + "…" : r.evidence}</q> : <span className="sm">{label === "UNCHANGED" ? "Nothing changed here." : label === "NEUTRAL" ? "The reader saw the whole change and judged it not adverse." : label === "UNDETERMINED" ? "The change was too long for the reader to see in full, so it is not judged." : "No quote."}</span>}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function App() {
  const [signer, setSigner] = useState<Signer | null>(null);
  const [desk, setDesk] = useState(savedDesk);
  const [target, setTarget] = useState<"official" | "desk">("official");
  const address = target === "desk" && desk ? desk.address : RADAR;
  const [data, setData] = useState<RadarData | null>(() => fallbackRadar(RADAR));
  const [stale, setStale] = useState(() => fallbackRadar(RADAR) !== null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [waitSec, setWaitSec] = useState(0);
  useEffect(() => onThrottle(setWaitSec), []);
  const tx = useTransaction();
  const busy = tx.state.stage === "submitting" || tx.state.stage === "waiting";

  const refresh = useCallback(async () => {
    setLoading(true); setError("");
    try { setData(await loadRadar(address)); setStale(false); } catch (e) { setError(errorText(e)); } finally { setLoading(false); }
  }, [address]);
  useEffect(() => { const f = fallbackRadar(address); setData(f); setStale(f !== null); void refresh(); }, [address, refresh]);
  const [, tick] = useState(0);
  useEffect(() => { const t = setInterval(() => tick((x) => x + 1), 30000); return () => clearInterval(t); }, []);

  const owner = isOwner(signer, data);
  const statuses = data?.statuses ?? [];
  const [selected, setSelected] = useState("");
  const sel = statuses.find((s) => s.watch_id === selected) ?? statuses[0] ?? null;

  const [check, setCheck] = useState<Check | null>(null);
  const [checkError, setCheckError] = useState("");
  useEffect(() => {
    setCheck(null); setCheckError("");
    if (!sel) return;
    let live = true;
    loadCheck(sel.watch_id).then((c) => { if (live) setCheck(c); }).catch((e) => { if (live) setCheckError(errorText(e)); });
    return () => { live = false; };
  }, [sel?.watch_id, sel?.check_id]); // eslint-disable-line react-hooks/exhaustive-deps

  // --- Writes ---------------------------------------------------------------------------
  async function runCheck(watchId: string) {
    if (!signer) return;
    const label = `Check ${watchId}`;
    tx.starting(label);
    let before: number;
    try { before = await shiftCheckCount(); } catch (e) { return tx.fail(label, e); }
    const ok = await tx.run(signer, SHIFT, "check", [watchId], label, "TermsShift refused the check.", () => boundCheck(before, signer, watchId));
    if (ok) { setSelected(watchId); setCheck(ok); void refresh(); }
  }

  const [note, setNote] = useState("");
  async function acknowledge(watchId: string) {
    if (!signer || !data || noteProblem(note)) return;
    const label = `Sign off ${watchId}`;
    const before = data.config.acknowledgement_count;
    const ok = await tx.run(signer, address, "acknowledge", [watchId, note.trim()], label,
      "there is nothing to sign off here, or the note is too short.", () => boundAck(address, before, signer, watchId));
    if (ok) { setNote(""); void refresh(); }
  }

  const [amount, setAmount] = useState("");
  async function allocate(watchId: string) {
    if (!signer || !data || amountProblem(amount)) return;
    const label = `Allocate to ${watchId}`;
    const before = data.config.allocation_count;
    const ok = await tx.run(signer, address, "allocate", [watchId, toUnits(amount)], label,
      "the radar refuses this allocation.", () => boundAllocation(address, before, signer, watchId));
    if (ok) { setAmount(""); void refresh(); }
  }

  const [trackId, setTrackId] = useState("");
  const [cap, setCap] = useState("1000000");
  const untracked = (data?.watches ?? []).filter((w) => !statuses.some((s) => s.watch_id === w.watch_id));
  const trackPick = untracked.find((w) => w.watch_id === trackId) ?? untracked[0];
  async function track() {
    if (!signer || !trackPick || amountProblem(cap)) return;
    const label = `Track ${trackPick.watch_id}`;
    const ok = await tx.run(signer, address, "track", [trackPick.watch_id, toUnits(cap)], label,
      "this issuer is already tracked, or TermsShift does not know it.", () => boundTracked(address, trackPick.watch_id));
    if (ok) { setSelected(trackPick.watch_id); void refresh(); }
  }

  async function createDesk() {
    if (!signer) return;
    const ok = await tx.deploy(signer, RADAR_SOURCE, [...DESK_ARGS], "Create my desk", "the deployment was rejected.",
      async (t) => ({ address: deployedAddress(t) }));
    if (ok) { const d = { address: ok.address as string, owner: signer.address }; saveDesk(d); setDesk(d); setTarget("desk"); }
  }
  function forgetDesk() { saveDesk(null); setDesk(null); setTarget("official"); }

  const cfg = data?.config;
  const maxAge = cfg ? Number(cfg.max_age_seconds) : 86400;

  return (
    <main>
      <div className="top">
        <div>
          <h1>Terms Radar</h1>
          <p className="sub">A treasury rule for stablecoin issuers' terms. How much may be allocated to an issuer depends on what a committee of validators found in its live terms, and a material adverse change allows nothing until a person has read it and signed it off on-chain.</p>
        </div>
        <div className="meta">GenLayer Studio Next (chain 61997)<br />
          Radar <a className="mono" href={addressLink(address)} target="_blank" rel="noreferrer">{short(address)}</a>{" "}
          · reads TermsShift <a className="mono" href={addressLink(SHIFT)} target="_blank" rel="noreferrer">{short(SHIFT)}</a><br />
          {data
            ? stale || error
              ? `${data.snapshot ? "Showing a snapshot of the chain taken" : "Showing the last read, from"} ${data.loadedAt.toLocaleString()}${loading ? " · reading the chain now…" : ""}`
              : `Read live from the chain at ${data.loadedAt.toLocaleTimeString()}`
            : loading ? "Reading the chain…" : ""}{" "}
          <button className="link" onClick={() => void refresh()} disabled={loading}>Refresh</button>
          {loading && waitSec > 0 && <><br />Pacing reads to the public RPC's 30-a-minute limit (about {waitSec}s)…</>}</div>
      </div>

      <AccountPanel signer={signer} onSigner={setSigner} />

      <div className="panel desk">
        <div>
          <b>Which radar</b>
          <div className="sm">
            {target === "official"
              ? <>The official radar, owned by <a className="mono" href={addressLink(data?.config.owner ?? RADAR)} target="_blank" rel="noreferrer">{short(data?.config.owner ?? RADAR)}</a>, the treasury that deployed it. Anyone can read it and ask TermsShift for a fresh check. Signing off and allocating are owner-only, as they would be for a real treasury.</>
              : <>Your own desk: the same audited contract, deployed from your account{desk && !same(desk.owner, signer?.address ?? "") ? <>, which belongs to <span className="mono">{short(desk.owner)}</span> (sign in with that account to act on it)</> : ""}. You are its owner, so you can track issuers, sign changes off and allocate.</>}
          </div>
        </div>
        <div className="actions">
          <button className={target === "official" ? "" : "secondary"} aria-pressed={target === "official"} onClick={() => setTarget("official")}>Official radar</button>
          {desk
            ? <>
                <button className={target === "desk" ? "" : "secondary"} aria-pressed={target === "desk"} onClick={() => setTarget("desk")}>My desk</button>
                <button className="secondary" onClick={forgetDesk}>Forget my desk</button>
              </>
            : <button className="secondary" disabled={!signer || busy} onClick={() => void createDesk()}
                      title={signer ? "" : "Sign in above to deploy"}>Create my desk</button>}
        </div>
      </div>

      <TxPanel state={tx.state} onReset={tx.reset}>
        {(b) =>
          b?.address ? <div className="result">Your desk is live at <a className="mono" href={addressLink(b.address)} target="_blank" rel="noreferrer">{short(b.address)}</a>. Track an issuer below, run a check, then try a sign-off and an allocation.</div>
          : b?.ack_id !== undefined ? <div className="result"><b>Signed off</b> as sign-off #{b.ack_id} against TermsShift check {b.check_id}: <q>{b.note}</q></div>
          : b?.allocation_id !== undefined ? <div className="result"><b>{n(b.amount)}</b> allocated to <span className="mono">{b.watch_id}</span> under <b>{POSTURE_NAME[b.posture] ?? b.posture}</b> ({b.allowed_pct}% of the cap), relying on TermsShift check {b.check_id}.</div>
          : b?.verdict ? <div className="result"><b>TermsShift check {b.check_id}</b> recorded for <span className="mono">{b.watch_id}</span>: <Pill tone={b.verdict === "MATERIAL_ADVERSE_CHANGE" ? "bad" : b.verdict === "UNCHANGED" ? "ok" : "info"}>{b.verdict}</Pill> The radar now reads this check.</div>
          : <div className="result"><span className="mono">{b?.watch_id}</span> is now tracked with a cap of {n(b?.cap ?? 0)}.</div>}
      </TxPanel>

      {cfg && (
        <div className="stats">
          <div className="stat"><b>{cfg.tracked_count}</b><span>issuers tracked</span></div>
          <div className="stat"><b>{cfg.acknowledgement_count}</b><span>sign-offs on-chain</span></div>
          <div className="stat"><b>{cfg.allocation_count}</b><span>allocations made</span></div>
          <div className="stat"><b>{duration(maxAge * 1000)}</b><span>oldest check the radar accepts</span></div>
          <div className="stat"><b>{cfg.acknowledged_pct}%</b><span>of the cap after a sign-off</span></div>
        </div>
      )}

      <Section title="How a posture is decided">
        <div className="panel">
          <div className="tablewrap">
            <table className="list ladder">
              <thead><tr><th>Posture</th><th>May be allocated</th><th>When</th></tr></thead>
              <tbody>
                {LADDER_ORDER.map((p) => (
                  <tr key={p}>
                    <td><Pill tone={POSTURE_TONE[p]}>{POSTURE_NAME[p]}</Pill></td>
                    <td><b>{data?.rules.ladder[p] ?? "—"}%</b> of the cap</td>
                    <td>{p === "STALE" ? `The latest check is older than ${duration(maxAge * 1000)}, or dated in the future.` : POSTURE_RULE[p]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="sm">A sign-off is bound to the exact wording that changed: the radar records a digest of which areas changed and of the changed wording, as TermsShift's validators agreed it. A later check that finds the same change keeps the sign-off; one that finds different wording does not, and needs a new one. The percentages are read from the contract.</p>
        </div>
      </Section>

      <Section title="Issuers" aside={<span className="sm">live from the radar, which reads TermsShift's latest check at this moment</span>}>
        {error && <div className="err">Couldn't read the chain: {error}{data && <> · The figures below are {data.snapshot ? "a snapshot taken when this site was built" : "this browser's last read"}, from {data.loadedAt.toLocaleString()}, not live. Studio Next is a shared test network: try Refresh in a minute.</>}</div>}
        {!data && !error && <p className="sub">Reading the chain…</p>}
        {data && statuses.length === 0 && <p className="sub">No issuers tracked yet. {owner ? "Track one below." : target === "desk" ? "Sign in as this desk's owner to track one." : ""}</p>}
        <div className="issuers">
          {statuses.map((s) => <IssuerCard key={s.watch_id} s={s} selected={s.watch_id === sel?.watch_id} onSelect={() => setSelected(s.watch_id)} />)}
        </div>
      </Section>

      {sel && (
        <Section title="One issuer in detail">
          <div className="panel">
            <div className="row">
              <div>
                <div className="name">{sel.label || sel.watch_id}</div>
                <div className="sm">{POSTURE_RULE[sel.posture] ?? sel.reason}</div>
                {check?.facts && (
                  <div className="sm" style={{ marginTop: 4 }}>
                    Baseline terms last updated <b>{check.facts.baseline_last_updated || "unknown"}</b> (archive capture {check.facts.baseline_capture || "?"}) · live terms last updated <b>{check.facts.live_last_updated || "unknown"}</b> · check {check.check_id} by <a className="mono" href={addressLink(check.submitted_by)} target="_blank" rel="noreferrer">{short(check.submitted_by)}</a>, {fmtTime(check.checked_at)}
                  </div>
                )}
              </div>
              <Pill tone={POSTURE_TONE[sel.posture] ?? "none"}>{POSTURE_NAME[sel.posture] ?? sel.posture} · {sel.allowed_pct}%</Pill>
            </div>
            <Bar s={sel} />
            {["STALE", "NO_CHECK", "UNDETERMINED"].includes(sel.posture) && (
              <div className="notice">{sel.posture === "UNDETERMINED"
                ? "TermsShift's latest check could not settle every area, so the radar counts this issuer as 0%."
                : `TermsShift has no check fresher than ${duration(maxAge * 1000)}, so the radar counts this issuer as 0%.`} Ask TermsShift for a fresh check below: it takes about a minute and anyone can do it.</div>
            )}
            {checkError && <div className="err">Couldn't read TermsShift's check: {checkError}</div>}
            {!check && !checkError && sel.check_id !== null && <p className="sub">Reading TermsShift's check…</p>}
            {check && check.verdict !== "NONE" && <div style={{ marginTop: 12 }}><AreaTable check={check} /></div>}
            <div className="actions" style={{ marginTop: 12 }}>
              <button disabled={!signer || busy} onClick={() => void runCheck(sel.watch_id)} title={signer ? "" : "Sign in above to send a transaction"}>Ask TermsShift for a fresh check</button>
              <span className="sm">One transaction: every validator reads the issuer's live terms and the archived baseline; usually a minute or two. Anyone can do this.</span>
            </div>
          </div>

          {sel.acknowledgement && (
            <div className="panel">
              <b>Sign-off #{sel.acknowledgement.ack_id}</b>{" "}
              <Pill tone={sel.acknowledgement.current ? "warn" : "none"}>{sel.acknowledgement.current ? "applies to the current wording" : "does not apply to the current wording"}</Pill>
              <div className="sm">by <a className="mono" href={addressLink(sel.acknowledgement.acknowledged_by)} target="_blank" rel="noreferrer">{short(sel.acknowledgement.acknowledged_by)}</a>, {fmtTime(sel.acknowledgement.acknowledged_at)}, against TermsShift check {sel.acknowledgement.check_id} · digest <span className="mono">{sel.acknowledgement.change_digest.slice(0, 16)}…</span></div>
              <p className="why"><q>{sel.acknowledgement.note}</q></p>
            </div>
          )}

          <div className="two">
            <div className="panel form">
              <b>Sign the change off</b>
              <div className="sm">Only for an issuer whose latest check found a change. Say what you read and what you decided ({20}-{400} characters).</div>
              <label>Note<textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} maxLength={400} placeholder="Read the redemption and freezing changes; accepted at half the cap pending legal review." /></label>
              <div className="actions">
                <button disabled={!signer || busy || !owner || !!noteProblem(note) || !["CHANGED_NOT_ADVERSE", "MATERIAL_ADVERSE_CHANGE"].includes(sel.verdict)}
                        onClick={() => void acknowledge(sel.watch_id)}>Sign off</button>
                {note && noteProblem(note) && <span className="sm">{noteProblem(note)}</span>}
                {!["CHANGED_NOT_ADVERSE", "MATERIAL_ADVERSE_CHANGE"].includes(sel.verdict) && <span className="sm">TermsShift's latest check is {sel.verdict}: nothing to sign off.</span>}
              </div>
            </div>
            <div className="panel form">
              <b>Allocate</b>
              <div className="sm">{sel.allowed_pct > 0 ? <>Up to <b>{n(sel.available)}</b> may be allocated now.</> : <>Nothing may be allocated: {sel.reason}.</>} The radar reads TermsShift's check again at the moment of the call.</div>
              <label>Amount<input inputMode="numeric" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="250000" /></label>
              <div className="actions">
                <button disabled={!signer || busy || !owner || !!amountProblem(amount)} onClick={() => void allocate(sel.watch_id)}>Allocate</button>
                {amount && amountProblem(amount) && <span className="sm">{amountProblem(amount)}</span>}
                {amount && !amountProblem(amount) && toUnits(amount) > BigInt(sel.available) && <span className="sm">More than is available: the contract will refuse it, and the refusal is a recorded outcome.</span>}
              </div>
            </div>
          </div>
          {!owner && (
            <p className="sm">{signer ? "Signing off and allocating are owner-only on this radar." : "Sign in to act."} {target === "official" ? <>Create <b>your own desk</b> above to try them for real: it deploys this same contract from your account.</> : "Sign in with the account that created this desk."}</p>
          )}
        </Section>
      )}

      {owner && (
        <Section title="Track an issuer">
          <div className="panel form">
            <div className="sm">Choose one of TermsShift's watches and set the most that may ever be allocated against it. Allocations are a share of this cap, set by the posture above.</div>
            {untracked.length === 0 ? <p className="sub">Every TermsShift watch is already tracked here.</p> : (
              <div className="formrow">
                <label>Issuer<select value={trackPick?.watch_id ?? ""} onChange={(e) => setTrackId(e.target.value)}>
                  {untracked.map((w) => <option key={w.watch_id} value={w.watch_id}>{w.watch_id} · {w.label}</option>)}</select></label>
                <label>Cap<input inputMode="numeric" value={cap} onChange={(e) => setCap(e.target.value)} /></label>
              </div>
            )}
            <div className="actions">
              <button disabled={!signer || busy || !trackPick || !!amountProblem(cap)} onClick={() => void track()}>Track</button>
              {amountProblem(cap) && <span className="sm">{amountProblem(cap)}</span>}
            </div>
          </div>
        </Section>
      )}

      <Section title="Ledger" aside={<span className="sm">sign-offs and allocations, newest first</span>}>
        {data && (
          <div className="tablewrap">
            <table className="list">
              <thead><tr><th>Sign-off</th><th>Issuer</th><th>Against check</th><th>When</th><th>Note</th></tr></thead>
              <tbody>
                {data.acks.map((a) => (
                  <tr key={a.ack_id}><td className="num">#{a.ack_id}</td><td className="mono">{a.watch_id}</td><td className="num">{a.check_id}</td><td>{fmtTime(a.acknowledged_at)}</td><td>{a.note}</td></tr>
                ))}
                {data.acks.length === 0 && <tr><td colSpan={5}>No sign-offs yet.</td></tr>}
              </tbody>
            </table>
          </div>
        )}
        {data && (
          <div className="tablewrap" style={{ marginTop: 12 }}>
            <table className="list">
              <thead><tr><th>Allocation</th><th>Issuer</th><th>Amount</th><th>Posture then</th><th>Allowed</th><th>Check</th><th>When</th></tr></thead>
              <tbody>
                {data.allocations.map((a) => (
                  <tr key={a.allocation_id}>
                    <td className="num">#{a.allocation_id}</td><td className="mono">{a.watch_id}</td><td>{n(a.amount)}</td>
                    <td>{POSTURE_NAME[a.posture] ?? a.posture}</td><td>{a.allowed_pct}%</td><td className="num">{a.check_id}</td><td>{fmtTime(a.allocated_at)}</td>
                  </tr>
                ))}
                {data.allocations.length === 0 && <tr><td colSpan={7}>No allocations yet.</td></tr>}
              </tbody>
            </table>
          </div>
        )}
        <p className="sm">A refused call (for example an allocation above the limit, or against an unsigned adverse change) is a decided transaction that records nothing; every refusal with the radar's reason is in the repository's CONTRACT.md.</p>
      </Section>

      <footer>
        <p>The radar reflects what TermsShift's validators agreed an issuer's published terms say compared with an archived version, in six clause areas. It is not legal advice and does not assess the issuer's reserves, solvency or conduct. Source, tests and every transaction: <a href="https://github.com/HarrisonJL/termsradar" target="_blank" rel="noreferrer">github.com/HarrisonJL/termsradar</a>.</p>
      </footer>
    </main>
  );
}
