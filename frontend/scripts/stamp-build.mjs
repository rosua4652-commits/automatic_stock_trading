import { readFileSync, writeFileSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const uiBuild = readFileSync(join(root, "src", "uiBuild.ts"), "utf8");
const m = uiBuild.match(/UI_BUILD\s*=\s*"([^"]+)"/);
const id = m ? m[1] : "unknown";
writeFileSync(join(root, "dist", ".aidi-ui-build"), id, "utf8");
console.log("stamped", id);
