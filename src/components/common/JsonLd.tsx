/**
 * Renders one or more Schema.org JSON-LD blocks as inline <script> tags.
 *
 * Server component — no client JS needed. JSON.stringify is safe because
 * builders in src/lib/jsonld.ts produce primitive-only objects; if you
 * ever feed user-provided strings through, prefer escaping `<` to avoid
 * breaking out of the script context.
 */
export function JsonLd({ data }: { data: object | object[] }) {
  const items = Array.isArray(data) ? data : [data];
  return (
    <>
      {items.map((item, i) => (
        <script
          key={i}
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify(item).replace(/</g, "\\u003c"),
          }}
        />
      ))}
    </>
  );
}
