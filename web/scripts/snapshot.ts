// Captures the official radar exactly as the app reads it, into src/snapshot.json. The app shows that
// snapshot only until its live read arrives, or if the chain cannot be read, and always labels it with
// the time it was taken. Reads only; no account needed. Run before a release build:
//   npm run snapshot && npm run build      (vite-node, so the app's own ?raw imports resolve)
import { writeFileSync } from "node:fs";
import { RADAR, loadRadar } from "../src/lib/radar";

const data = await loadRadar(RADAR);
writeFileSync(new URL("../src/snapshot.json", import.meta.url), JSON.stringify(data, null, 1) + "\n");
console.log(`snapshot of ${RADAR}: ${data.statuses.length} issuers, ${data.allocations.length} allocations, taken ${data.loadedAt.toISOString()}`);
process.exit(0);
