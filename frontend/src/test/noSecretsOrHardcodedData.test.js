import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SRC_DIR = path.dirname(fileURLToPath(import.meta.url)) + "/..";

function collectFiles(dir, exts, exclude = ["test"]) {
  let results = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (exclude.includes(entry.name)) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      results = results.concat(collectFiles(full, exts, exclude));
    } else if (exts.some((ext) => entry.name.endsWith(ext))) {
      results.push(full);
    }
  }
  return results;
}

describe("no secrets in frontend source", () => {
  const files = collectFiles(SRC_DIR, [".js", ".jsx"]);

  it("never references GEMINI_API_KEY as a usable value (only safety-documentation prose may mention the name)", () => {
    // Bans actual usage patterns (reading it from env, assigning it,
    // sending it in a request) -- not the bare word, which legitimately
    // appears in this project's own "we never touch this" documentation
    // comments (see api/client.js's docstring).
    const forbidden = [
      "import.meta.env.GEMINI_API_KEY",
      "GEMINI_API_KEY =",
      "GEMINI_API_KEY:",
      "GEMINI_API_KEY}",
      "process.env.GEMINI_API_KEY",
    ];
    for (const file of files) {
      const content = fs.readFileSync(file, "utf-8");
      for (const pattern of forbidden) {
        expect(content, `${file} references forbidden pattern ${pattern}`).not.toContain(pattern);
      }
    }
  });

  it("never references a database URL or credential-shaped env var", () => {
    const forbidden = ["DATABASE_URL", "DB_PASSWORD", "POSTGRES_PASSWORD"];
    for (const file of files) {
      const content = fs.readFileSync(file, "utf-8");
      for (const pattern of forbidden) {
        expect(content, `${file} references ${pattern}`).not.toContain(pattern);
      }
    }
  });

  it("only exposes VITE_-prefixed environment variables", () => {
    for (const file of files) {
      const content = fs.readFileSync(file, "utf-8");
      const matches = content.match(/import\.meta\.env\.(\w+)/g) || [];
      for (const m of matches) {
        const varName = m.replace("import.meta.env.", "");
        expect(varName.startsWith("VITE_"), `${file} reads non-VITE_ env var ${varName}`).toBe(true);
      }
    }
  });
});

describe("no hardcoded fraud/risk results used as production data", () => {
  // Only scan page/component source, not test fixtures or config/styling
  // maps (severity.js's ACTION_STYLES intentionally lists every enum
  // value to style it -- that's a style lookup table, not fabricated
  // investigation data).
  const productionDirs = ["pages", "components", "context"].map((d) => path.join(SRC_DIR, d));
  const files = productionDirs.flatMap((d) => collectFiles(d, [".jsx", ".js"]));

  it("never defines a literal object shaped like a fabricated InvestigationResult", () => {
    for (const file of files) {
      const content = fs.readFileSync(file, "utf-8");
      // A hardcoded fake result would combine a classification AND a
      // confidence number as sibling literal keys in the same file.
      const hasClassificationLiteral = /classification:\s*["']/.test(content);
      const hasConfidenceLiteral = /confidence:\s*0\.\d/.test(content);
      expect(
        hasClassificationLiteral && hasConfidenceLiteral,
        `${file} appears to hardcode a fabricated investigation result`
      ).toBe(false);
    }
  });

  it("data pages fetch from the api/ layer rather than defining local cluster/risk data", () => {
    const dashboardSrc = fs.readFileSync(path.join(SRC_DIR, "pages/DashboardPage.jsx"), "utf-8");
    const clustersSrc = fs.readFileSync(path.join(SRC_DIR, "pages/ClustersPage.jsx"), "utf-8");
    expect(dashboardSrc).toMatch(/from "..\/api\//);
    expect(clustersSrc).toMatch(/from "..\/api\//);
  });
});
