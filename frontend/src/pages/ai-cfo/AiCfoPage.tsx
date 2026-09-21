import { PillarPage } from "@/app/PillarPage";

const META = {
  title: "AI CFO",
  blurb:
    "A grounded AI CFO that only explains numbers your engines already computed — never invents one.",
};

export function AiCfoPage() {
  return <PillarPage meta={META} />;
}
