/**
 * Schema.org JSON-LD helpers — one builder per page type.
 *
 * Each helper returns a plain object that can be passed straight into the
 * <JsonLd> component (which serializes + emits a script tag). Pages that
 * have multiple schemas pass an array of objects.
 */

export const SITE_URL = "https://x402.printmoneylab.com";
export const API_BASE = "https://api.x402.printmoneylab.com/api/v1";
const CC0 = "https://creativecommons.org/publicdomain/zero/1.0/";
const ORG = {
  "@type": "Organization",
  name: "x402watch",
  url: SITE_URL,
  parentOrganization: {
    "@type": "Organization",
    name: "PrintMoneyLab",
    url: "https://printmoneylab.com",
  },
};

export function websiteSchema() {
  return {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: "x402watch",
    url: SITE_URL,
    description:
      "Wash-filtered intelligence layer for the x402 ecosystem.",
    publisher: ORG,
    potentialAction: {
      "@type": "SearchAction",
      target: {
        "@type": "EntryPoint",
        urlTemplate: `${SITE_URL}/services?search={query}`,
      },
      "query-input": "required name=query",
    },
  };
}

export function organizationSchema() {
  return {
    "@context": "https://schema.org",
    ...ORG,
    sameAs: [
      "https://github.com/printmoneylab/x402watch",
      "https://twitter.com/printmoneylab",
    ],
  };
}

type DatasetOpts = {
  name: string;
  description: string;
  url: string;
  apiUrl?: string;
  /** Optional ISO-8601 last-updated string. */
  dateModified?: string;
};

export function datasetSchema(opts: DatasetOpts) {
  return {
    "@context": "https://schema.org",
    "@type": "Dataset",
    name: opts.name,
    description: opts.description,
    url: opts.url,
    creator: ORG,
    publisher: ORG,
    license: CC0,
    isAccessibleForFree: true,
    keywords: [
      "x402",
      "agentic web",
      "wash detection",
      "blockchain",
      "USDC",
    ],
    ...(opts.dateModified ? { dateModified: opts.dateModified } : {}),
    ...(opts.apiUrl
      ? {
          distribution: [
            {
              "@type": "DataDownload",
              contentUrl: opts.apiUrl,
              encodingFormat: "application/json",
            },
          ],
        }
      : {}),
  };
}

type ServiceOpts = {
  id: number | string;
  name: string;
  description: string | null;
  category: string;
  priceUsd: number | null;
  url: string;
};

export function serviceSchema(opts: ServiceOpts) {
  return {
    "@context": "https://schema.org",
    "@type": "Service",
    name: opts.name || `x402 service #${opts.id}`,
    ...(opts.description ? { description: opts.description } : {}),
    serviceType: opts.category,
    url: opts.url,
    provider: { "@type": "Organization", name: "x402 service operator" },
    ...(opts.priceUsd != null
      ? {
          offers: {
            "@type": "Offer",
            price: opts.priceUsd,
            priceCurrency: "USDC",
            availability: "https://schema.org/InStock",
          },
        }
      : {}),
  };
}

type ArticleOpts = {
  headline: string;
  description: string;
  url: string;
  datePublished: string;
  dateModified?: string;
};

export function articleSchema(opts: ArticleOpts) {
  return {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: opts.headline,
    description: opts.description,
    url: opts.url,
    author: ORG,
    publisher: ORG,
    datePublished: opts.datePublished,
    dateModified: opts.dateModified ?? opts.datePublished,
    isAccessibleForFree: true,
    license: CC0,
  };
}
