import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { getHookScriptSource, getScriptSource, getZipScriptSource } from "single-file-cli/lib/single-file-script.js";

const outputDir = resolve(process.argv[2] || ".singlefile-cache");
await mkdir(outputDir, { recursive: true });
const files = { hook: resolve(outputDir, "hook.js"), main: resolve(outputDir, "main.js"), zip: resolve(outputDir, "zip.js") };
await Promise.all([
  writeFile(files.hook, getHookScriptSource(), "utf8"),
  writeFile(files.main, await getScriptSource({}), "utf8"),
  writeFile(files.zip, getZipScriptSource(), "utf8"),
]);
process.stdout.write(JSON.stringify(files));
