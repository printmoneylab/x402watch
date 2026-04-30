import { Hero } from "@/components/landing/Hero";
import { Stats, ProductLine } from "@/components/landing/Stats";
import { Differentiators } from "@/components/landing/Differentiators";
import { ChartGrid } from "@/components/landing/Charts";
import { Footer } from "@/components/landing/Footer";
import { fetchLandingPayload, FALLBACK } from "@/lib/stats";

export const revalidate = 60;

async function getPayload() {
  try {
    return await fetchLandingPayload();
  } catch (err) {
    console.error("[landing] live fetch failed, using fallback:", err);
    return FALLBACK;
  }
}

export default async function HomePage() {
  const payload = await getPayload();
  return (
    <>
      <Hero />
      <Stats stats={payload.stats} />
      <ProductLine />
      <Differentiators />
      <ChartGrid
        labels={payload.label_distribution}
        series={payload.category_volume_series}
        daily={payload.daily_new_services}
      />
      <Footer />
    </>
  );
}
