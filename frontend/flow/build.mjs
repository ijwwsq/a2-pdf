// Собирает конструктор в a2pdf/static/flow: один js и один css, без CDN.
import esbuild from "esbuild";
import fs from "node:fs";
import path from "node:path";

const out = path.resolve("../../a2pdf/static/flow");
fs.mkdirSync(out, { recursive: true });

await esbuild.build({
  entryPoints: ["entry.ts"],
  bundle: true,
  format: "iife",
  globalName: "A2Flow",
  target: "es2020",
  minify: true,
  legalComments: "eof",
  alias: { obsidian: "./obsidian-shim.ts" },
  outfile: path.join(out, "flow.js"),
  logLevel: "info",
});
fs.copyFileSync("vendor/styles.css", path.join(out, "flow.css"));
fs.copyFileSync("vendor/LICENSE", path.join(out, "LICENSE"));
