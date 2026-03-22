import Nav from "./components/Nav";
import Hero from "./components/Hero";
import Stats from "./components/Stats";
import DifferentiationCallout from "./components/DifferentiationCallout";
import Problem from "./components/Problem";
import CompetitiveComparison from "./components/CompetitiveComparison";
import Platform from "./components/Platform";
import Pricing from "./components/Pricing";
import Templates from "./components/Templates";
import Research from "./components/Research";
import Claims from "./components/Claims";
import CaseStudy from "./components/CaseStudy";
import Community from "./components/Community";
import Waitlist from "./components/Waitlist";
import Footer from "./components/Footer";

export default function Home() {
  return (
    <>
      <Nav />
      <main>
        <Hero />
        <Stats />
        <DifferentiationCallout />
        <Problem />
        <CompetitiveComparison />
        <Platform />
        <Pricing />
        <Templates />
        <Research />
        <Claims />
        <CaseStudy />
        <Community />
        <Waitlist />
      </main>
      <Footer />
    </>
  );
}
