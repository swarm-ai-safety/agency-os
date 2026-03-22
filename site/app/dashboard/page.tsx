import type { Metadata } from "next";
import { Suspense } from "react";

import DashboardClient from "./DashboardClient";

export const metadata: Metadata = {
  title: "Usage Dashboard — Zero Human Labs",
  description:
    "View your gateway usage, costs, and savings from smart routing and caching.",
  robots: {
    index: false,
    follow: false,
  },
  alternates: {
    canonical: "/dashboard",
  },
  openGraph: {
    url: "/dashboard",
  },
};

export default function DashboardPage() {
  return (
    <Suspense>
      <DashboardClient />
    </Suspense>
  );
}
