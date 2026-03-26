import { build } from "esbuild";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

await build({
  entryPoints: [path.join(__dirname, "src", "main.tsx")],
  bundle: true,
  format: "esm",
  target: "es2020",
  jsx: "automatic",
  outfile: path.join(__dirname, "..", "app", "static", "app.js"),
  sourcemap: false,
  loader: {
    ".css": "css"
  }
});
