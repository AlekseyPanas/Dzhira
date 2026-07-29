// Build config: Bun.build bundles src/client.tsx -> dist/client.js, the SCSS plugin collects every
// imported .scss into one dist/styles.css, and index.html is copied into dist/ so FastAPI can serve
// the folder as a self-contained static bundle. The Python launcher runs this via `bun run build`.
// (Mirrors eventCamera/frontend/build.ts and SadkoTrans/admin_dash/build.ts.)

import type { BunPlugin } from "bun";
import * as path from "path";
import * as fs from "fs/promises";
import * as sass from "sass";

const root = process.cwd();
const scssFiles = new Set<string>();

const scssCollector: BunPlugin = {
    name: "SASS Loader",
    setup(build) {
        build.onLoad({ filter: /\.scss$/ }, async (args) => {
            scssFiles.add(args.path);                    // cache the path; CSS is emitted below
            return { contents: "", loader: "text" };
        });
    },
};

const buildCombinedCss = async () => {
    if (scssFiles.size === 0) return;
    const combined = [...scssFiles]
        .map((filePath) => `@use "${path.relative(root, filePath).split(path.sep).join("/")}";`)
        .join("\n");
    const result = sass.compileString(combined, { loadPaths: ["."], style: "compressed" });
    await fs.writeFile(path.join("dist", "styles.css"), result.css);
    console.log("styles.css generated");
};

const result = await Bun.build({
    entrypoints: ["src/client.tsx"],
    outdir: "dist",
    minify: true,
    plugins: [scssCollector],
});
if (!result.success) {
    for (const log of result.logs) console.error(log);
    process.exit(1);
}
await buildCombinedCss();
await fs.copyFile("index.html", path.join("dist", "index.html"));
console.log("frontend built -> dist/");
