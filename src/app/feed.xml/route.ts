/**
 * /feed.xml — RSS 2.0 feed of recent x402 ecosystem changes.
 *
 * Items: most recent newly-indexed services from the trends payload,
 * plus the current set of anonymized wash case studies. Rebuilds every
 * 10 minutes (server-side revalidation).
 */
import { fetchTrends } from "@/lib/trends";
import { fetchWashReport, prettyPatternType } from "@/lib/wash";

const SITE_URL = "https://x402.printmoneylab.com";
const FEED_TITLE = "x402watch updates";
const FEED_DESC = "Latest x402 ecosystem changes — daily new services and pattern findings.";

export const revalidate = 600;

function escapeXml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function rfc822(d: Date): string {
  return d.toUTCString();
}

type FeedItem = {
  title: string;
  link: string;
  description: string;
  pubDate: Date;
  guid: string;
};

export async function GET(): Promise<Response> {
  const items: FeedItem[] = [];

  // Recent new services from the trends endpoint.
  try {
    const trends = await fetchTrends();
    for (const s of trends.recent_new_services) {
      const url = `${SITE_URL}/services/${s.id}`;
      const priceStr =
        s.price_amount != null ? `$${s.price_amount.toFixed(4)} USDC` : "—";
      items.push({
        title: `New service: ${s.name || `#${s.id}`}`,
        link: url,
        description: `Category: ${s.category} · Chain: ${s.chain} · Price: ${priceStr}`,
        pubDate: new Date(s.first_seen),
        guid: url,
      });
    }
  } catch (err) {
    console.error("[feed] trends fetch failed:", err);
  }

  // Wash-report case studies: 5 hardcoded items but they evolve as
  // the methodology evolves, so they belong in the feed.
  try {
    const wash = await fetchWashReport();
    const updated = wash.stats.last_updated
      ? new Date(wash.stats.last_updated)
      : new Date();
    for (const cs of wash.case_studies) {
      items.push({
        title: `Pattern study — Service ${cs.anonymous_id}: ${prettyPatternType(cs.pattern_type)}`,
        link: `${SITE_URL}/wash-report#${cs.anonymous_id}`,
        description:
          `${cs.buyer_count} buyers · ${cs.wash_pct.toFixed(1)}% wash · ` +
          `confidence ${cs.confidence.toFixed(2)} · signals: ${cs.signals.join(", ")}`,
        pubDate: updated,
        guid: `${SITE_URL}/wash-report/case-${cs.anonymous_id}`,
      });
    }
  } catch (err) {
    console.error("[feed] wash-report fetch failed:", err);
  }

  // Newest first; tolerate invalid dates.
  items.sort((a, b) => {
    const ta = a.pubDate.getTime();
    const tb = b.pubDate.getTime();
    return (Number.isFinite(tb) ? tb : 0) - (Number.isFinite(ta) ? ta : 0);
  });

  const lastBuild = rfc822(new Date());
  const itemsXml = items
    .map((it) => {
      const pub = Number.isFinite(it.pubDate.getTime())
        ? rfc822(it.pubDate)
        : lastBuild;
      return [
        "<item>",
        `<title>${escapeXml(it.title)}</title>`,
        `<link>${escapeXml(it.link)}</link>`,
        `<description>${escapeXml(it.description)}</description>`,
        `<pubDate>${pub}</pubDate>`,
        `<guid isPermaLink="false">${escapeXml(it.guid)}</guid>`,
        "</item>",
      ].join("");
    })
    .join("\n");

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>${escapeXml(FEED_TITLE)}</title>
    <link>${SITE_URL}</link>
    <description>${escapeXml(FEED_DESC)}</description>
    <language>en-us</language>
    <lastBuildDate>${lastBuild}</lastBuildDate>
    <atom:link href="${SITE_URL}/feed.xml" rel="self" type="application/rss+xml" />
${itemsXml}
  </channel>
</rss>`;

  return new Response(xml, {
    headers: {
      "Content-Type": "application/rss+xml; charset=utf-8",
      "Cache-Control": "public, max-age=600, s-maxage=600",
    },
  });
}
