import type { Metadata } from "next";
import { Suspense } from "react";

import WelcomeClient from "./WelcomeClient";

export const metadata: Metadata = {
  title: "Welcome — Zero Human Labs",
  description:
    "You're ready to make your first request. Copy your API key, run the quickstart curl command, and start saving on AI costs with smart LLM routing.",
  robots: {
    index: false,
    follow: false,
  },
  alternates: {
    canonical: "/welcome",
  },
  openGraph: {
    url: "/welcome",
  },
};

export default function WelcomePage() {
  return (
    <Suspense>
      <WelcomeClient />
    </Suspense>
  );
}
