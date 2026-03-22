import fs from "fs";
import path from "path";
import matter from "gray-matter";
import { remark } from "remark";
import html from "remark-html";

const DOCS_DIR = path.join(process.cwd(), "..", "docs");

export interface DocMeta {
  slug: string[];
  title: string;
  description: string;
  category: string;
}

export interface Doc extends DocMeta {
  content: string;
}

export interface DocNavGroup {
  label: string;
  items: DocMeta[];
}

/** Map directory names and slugs to human-readable labels */
const CATEGORY_LABELS: Record<string, string> = {
  policy: "Policy",
  product: "Product",
};

const TITLE_OVERRIDES: Record<string, string> = {
  "api-reference": "API Reference",
  "database-migrations": "Database Migrations",
  "disaster-recovery": "Disaster Recovery",
  "governance-research-mapping": "Governance Research Mapping",
  "labeling-guide": "Labeling Guide",
  "project-organization": "Project Organization",
  "sub-issues-guide": "Sub-Issues Guide",
  "sub-issues-process": "Sub-Issues Process",
  "testing-best-practices": "Testing Best Practices",
  "agent-system-patterns": "Agent System Patterns",
  "agent-worktree-isolation": "Agent Worktree Isolation",
  "ai-first-ats-option-template": "AI-First ATS Option Template",
  "llm-api-commercialization": "LLM API Commercialization",
  "agency-integration-prd": "Agency Integration PRD",
  agents: "Agents",
  deployment: "Deployment",
  operations: "Operations",
  pricing: "Pricing",
};

function extractTitle(filePath: string, slug: string): string {
  const raw = fs.readFileSync(filePath, "utf-8");
  const { data, content } = matter(raw);
  if (data.title) return data.title as string;
  // Extract first H1 from content
  const h1Match = content.match(/^#\s+(.+)$/m);
  if (h1Match) return h1Match[1];
  return TITLE_OVERRIDES[slug] || slug.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function collectDocs(dir: string, slugPrefix: string[] = []): DocMeta[] {
  if (!fs.existsSync(dir)) return [];
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  const docs: DocMeta[] = [];

  for (const entry of entries) {
    if (entry.isDirectory()) {
      docs.push(...collectDocs(path.join(dir, entry.name), [...slugPrefix, entry.name]));
    } else if (entry.name.endsWith(".md")) {
      const baseName = entry.name.replace(/\.md$/, "");
      const slug = [...slugPrefix, baseName];
      const category = slugPrefix.length > 0
        ? CATEGORY_LABELS[slugPrefix[0]] || slugPrefix[0]
        : "General";
      docs.push({
        slug,
        title: extractTitle(path.join(dir, entry.name), baseName),
        description: "",
        category,
      });
    }
  }

  return docs;
}

export function getAllDocSlugs(): string[][] {
  return collectDocs(DOCS_DIR).map((d) => d.slug);
}

export function getAllDocs(): DocMeta[] {
  return collectDocs(DOCS_DIR).sort((a, b) => a.title.localeCompare(b.title));
}

export function getDocNavGroups(): DocNavGroup[] {
  const docs = getAllDocs();
  const groups: Record<string, DocMeta[]> = {};

  for (const doc of docs) {
    const cat = doc.category;
    if (!groups[cat]) groups[cat] = [];
    groups[cat].push(doc);
  }

  // Sort: General first, then alphabetical
  const sortedKeys = Object.keys(groups).sort((a, b) => {
    if (a === "General") return -1;
    if (b === "General") return 1;
    return a.localeCompare(b);
  });

  return sortedKeys.map((key) => ({
    label: key,
    items: groups[key].sort((a, b) => a.title.localeCompare(b.title)),
  }));
}

export async function getDocBySlug(slug: string[]): Promise<Doc | null> {
  const filePath = path.join(DOCS_DIR, ...slug) + ".md";
  if (!fs.existsSync(filePath)) return null;

  const raw = fs.readFileSync(filePath, "utf-8");
  const { data, content: md } = matter(raw);
  const baseName = slug[slug.length - 1];
  const category = slug.length > 1
    ? CATEGORY_LABELS[slug[0]] || slug[0]
    : "General";

  const result = await remark().use(html).process(md);

  return {
    slug,
    title: (data.title as string) || md.match(/^#\s+(.+)$/m)?.[1] || TITLE_OVERRIDES[baseName] || baseName,
    description: (data.description as string) || "",
    category,
    content: result.toString(),
  };
}
