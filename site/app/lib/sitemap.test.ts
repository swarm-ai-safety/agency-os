import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const sitemapPath = path.join(process.cwd(), "public", "sitemap.xml");

describe("public sitemap", () => {
  it("uses the canonical production domain", () => {
    const sitemap = fs.readFileSync(sitemapPath, "utf8");
    expect(sitemap).toContain("https://zero-human-labs.com/");
    expect(sitemap).not.toContain("https://zerohumanlabs.com/");
  });

  it("does not include non-public dashboard routes", () => {
    const sitemap = fs.readFileSync(sitemapPath, "utf8");
    expect(sitemap).not.toContain("/dashboard");
    expect(sitemap).not.toContain("/welcome");
  });
});
