import { build } from "esbuild";
import { copyFile, mkdir } from "node:fs/promises";

await mkdir("dist/server", { recursive: true });
await mkdir("dist/.openai", { recursive: true });
await build({
  entryPoints: ["worker/entry.js"],
  outfile: "dist/server/index.js",
  bundle: true,
  format: "esm",
  target: "es2022",
  external: ["./kernel.wasm"],
  loader: { ".zip": "binary" },
  legalComments: "inline",
  minify: true,
});
await copyFile("worker/kernel.wasm", "dist/server/kernel.wasm");
await copyFile(".openai/hosting.json", "dist/.openai/hosting.json");
