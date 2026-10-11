import { describe, expect, it } from "vitest";
import { classify } from "./lifecycle";
import { errorText } from "./genlayer";

// The guarantees a reviewer checks first: only ACCEPTED / FINALIZED are success,
// and a call the contract rejected is never shown as one, whatever the consensus status says.
describe("classify", () => {
  it("accepts ACCEPTED (5) and FINALIZED (7)", () => {
    expect(classify({ status: 5 }, "x").ok).toBe(true);
    expect(classify({ status: "7" }, "x").ok).toBe(true);
  });

  it.each([[6, "UNDETERMINED"], [8, "CANCELED"], [12, "VALIDATORS_TIMEOUT"], [13, "LEADER_TIMEOUT"], [1, "PENDING"]])(
    "does not accept status %s (%s)", (status) => {
      const out = classify({ status }, "x");
      expect(out.ok).toBe(false);
      if (!out.ok) expect(out.kind).toBe("consensus");
    });

  it("a contract rejection is a rejection even when consensus accepted it", () => {
    const tx = { status: 5, txExecutionResultName: "FINISHED_WITH_ERROR", result: "already tracked" };
    const out = classify(tx, "fallback hint");
    expect(out.ok).toBe(false);
    if (!out.ok) {
      expect(out.kind).toBe("rejected");
      expect(out.message).toContain("already tracked");
    }
  });

  // The exact refusals the live proof recorded (CONTRACT.md), kept whole including their percentages and punctuation.
  it.each([
    "'circle-since-2026' refused: CLEAR allows 100% of the cap 1000000, of which 100000 is left",
    "'tether-since-2023' refused: ADVERSE_UNACKNOWLEDGED - a material adverse change nobody has signed off: read it, then acknowledge it",
    "nothing to acknowledge: TermsShift's latest check of 'circle-since-2026' is UNCHANGED",
    "the note must say what was decided, 20-400 characters",
    "'no-such-watch' refused: TermsShift has no such watch",
    "only the owner can allocate",
  ])("keeps the radar's own refusal whole: %s", (reason) => {
    const out = classify({ status: 5, txExecutionResultName: "FINISHED_WITH_ERROR", result: reason }, "hint");
    expect(out.ok).toBe(false);
    if (!out.ok) expect(out.message).toContain(reason);
  });

  it("falls back to the hint when the revert text is not found", () => {
    const out = classify({ status: 7, txExecutionResultName: "FINISHED_WITH_ERROR" }, "the contract refused it");
    expect(out.ok).toBe(false);
    if (!out.ok) expect(out.message).toContain("the contract refused it");
  });
});

describe("errorText", () => {
  it("surfaces a 429 buried in viem's cause chain instead of 'unknown RPC error'", () => {
    const err = Object.assign(new Error("An unknown RPC error occurred."), {
      name: "UnknownRpcError", details: "Rate limit exceeded: 30 requests per minute",
      cause: { code: -32029, message: "Rate limit exceeded: 30 requests per minute" },
    });
    const text = errorText(err);
    expect(text).toMatch(/Rate limit exceeded/);
    expect(text).not.toMatch(/unknown RPC error/);
  });

  it("falls back to the plain message", () => {
    expect(errorText(new Error("boom"))).toBe("boom");
  });
});
