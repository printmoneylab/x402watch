import type { MetadataRoute } from "next";
import { fetchCategories } from "@/lib/categories";

const SITE_URL = "https://x402.printmoneylab.com";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const lastModified = new Date();

  const base: MetadataRoute.Sitemap = [
    {
      url: `${SITE_URL}/`,
      lastModified,
      changeFrequency: "hourly",
      priority: 1.0,
    },
    {
      url: `${SITE_URL}/categories`,
      lastModified,
      changeFrequency: "hourly",
      priority: 0.9,
    },
    {
      url: `${SITE_URL}/services`,
      lastModified,
      changeFrequency: "hourly",
      priority: 0.9,
    },
    {
      url: `${SITE_URL}/trends`,
      lastModified,
      changeFrequency: "daily",
      priority: 0.8,
    },
    {
      url: `${SITE_URL}/wash-report`,
      lastModified,
      changeFrequency: "daily",
      priority: 0.9,
    },
    {
      url: `${SITE_URL}/docs/methodology`,
      lastModified,
      changeFrequency: "monthly",
      priority: 0.8,
    },
    {
      url: `${SITE_URL}/api`,
      lastModified,
      changeFrequency: "weekly",
      priority: 0.8,
    },
    {
      url: `${SITE_URL}/pricing`,
      lastModified,
      changeFrequency: "weekly",
      priority: 0.7,
    },
  ];

  // Append per-category detail pages (best-effort; degrade silently if API down)
  try {
    const list = await fetchCategories();
    for (const c of list.categories) {
      base.push({
        url: `${SITE_URL}/categories/${encodeURIComponent(c.category)}`,
        lastModified,
        changeFrequency: "daily",
        priority: 0.7,
      });
    }
  } catch (err) {
    console.warn("[sitemap] categories fetch failed; emitting only base entries", err);
  }

  return base;
}
