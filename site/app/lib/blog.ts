import fs from "fs";
import path from "path";
import matter from "gray-matter";
import { remark } from "remark";
import html from "remark-html";

const BLOG_DIR = path.join(process.cwd(), "content", "blog");

export interface BlogPost {
  slug: string;
  title: string;
  date: string;
  author: string;
  description: string;
  tags: string[];
  content: string;
}

export interface BlogPostMeta {
  slug: string;
  title: string;
  date: string;
  author: string;
  description: string;
  tags: string[];
}

export function getAllPostSlugs(): string[] {
  if (!fs.existsSync(BLOG_DIR)) return [];
  return fs
    .readdirSync(BLOG_DIR)
    .filter((f) => f.endsWith(".md"))
    .map((f) => {
      const { data } = matter(fs.readFileSync(path.join(BLOG_DIR, f), "utf-8"));
      return (data.slug as string) || f.replace(/\.md$/, "");
    });
}

export function getAllPosts(): BlogPostMeta[] {
  if (!fs.existsSync(BLOG_DIR)) return [];
  const files = fs.readdirSync(BLOG_DIR).filter((f) => f.endsWith(".md"));
  const posts = files.map((f) => {
    const raw = fs.readFileSync(path.join(BLOG_DIR, f), "utf-8");
    const { data } = matter(raw);
    return {
      slug: (data.slug as string) || f.replace(/\.md$/, ""),
      title: (data.title as string) || "Untitled",
      date: (data.date as string) || "",
      author: (data.author as string) || "",
      description: (data.description as string) || "",
      tags: (data.tags as string[]) || [],
    };
  });
  return posts.sort((a, b) => (a.date > b.date ? -1 : 1));
}

export async function getPostBySlug(slug: string): Promise<BlogPost | null> {
  if (!fs.existsSync(BLOG_DIR)) return null;
  const files = fs.readdirSync(BLOG_DIR).filter((f) => f.endsWith(".md"));
  for (const f of files) {
    const raw = fs.readFileSync(path.join(BLOG_DIR, f), "utf-8");
    const { data, content: md } = matter(raw);
    const postSlug = (data.slug as string) || f.replace(/\.md$/, "");
    if (postSlug === slug) {
      const result = await remark().use(html).process(md);
      return {
        slug: postSlug,
        title: (data.title as string) || "Untitled",
        date: (data.date as string) || "",
        author: (data.author as string) || "",
        description: (data.description as string) || "",
        tags: (data.tags as string[]) || [],
        content: result.toString(),
      };
    }
  }
  return null;
}
