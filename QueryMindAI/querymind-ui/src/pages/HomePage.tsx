import { useLoaderData } from "react-router-dom";
import { getExamples } from "@/api/catalog";
import { FeatureLinks } from "@/features/home/components/FeatureLinks";
import { HomeHero } from "@/features/home/components/HomeHero";
import { PinnedQuestionCards } from "@/features/home/components/PinnedQuestionCards";
import { RecentQueries } from "@/features/home/components/RecentQueries";
import { usePinnedQuestions } from "@/features/pinned/store";

export async function loader() {
  return { examples: await getExamples() };
}

export function HomePage() {
  const { examples } = useLoaderData<typeof loader>();
  const pinned = usePinnedQuestions(examples);

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-10">
      <HomeHero />
      <section aria-labelledby="pinned-heading">
        <h2 id="pinned-heading" className="text-sm font-semibold">
          Pinned questions
        </h2>
        <PinnedQuestionCards pinned={pinned} />
      </section>
      <FeatureLinks />
      <RecentQueries pinned={pinned} />
    </div>
  );
}
