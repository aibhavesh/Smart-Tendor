import { HeroCopy } from "@/components/landing/HeroCopy";
import { HeroVisual } from "@/components/landing/HeroVisual";
import { LandingSections } from "@/components/landing/LandingSections";
import { Navbar } from "@/components/landing/Navbar";

export default function LandingPage() {
  return (
    <div className="relative flex-1 overflow-x-clip bg-canvas">
      {/*
       * Ambient aura. Pure CSS radial spotlights — no asset, no network request, so
       * there is nothing here that can fail to load and nothing holding LCP.
       */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -top-[10%] left-[8%] w-[560px] h-[560px] rounded-full bg-sky-soft/20 blur-aura-lg" />
        <div className="absolute top-[18%] -right-[6%] w-[620px] h-[620px] rounded-full bg-sky-vivid/20 blur-aura-lg" />
        <div className="absolute bottom-[4%] left-[28%] w-[480px] h-[480px] rounded-full bg-sky-soft/20 blur-aura-sm" />
      </div>

      <Navbar />

      <main
        id="home"
        className="relative w-full max-w-[1280px] mx-auto px-6 sm:px-12 lg:px-20 pt-[80px] md:pt-[80px]"
      >
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-12 items-center min-h-[calc(100vh-80px)]">
          <div className="lg:col-span-5">
            <HeroCopy />
          </div>
          <div className="lg:col-span-7">
            <HeroVisual />
          </div>
        </div>

        <LandingSections />
      </main>
    </div>
  );
}
