import type { Metadata } from "next";
import SignupClient from "./SignupClient";

export const metadata: Metadata = {
  title: "Sign Up — Zero Human Labs",
  description:
    "Create your API tenant in under 2 minutes. Start with a free one-time guided demo run, then upgrade for continued usage.",
  alternates: {
    canonical: "/signup",
  },
  openGraph: {
    url: "/signup",
  },
};

export default function SignupPage() {
  return <SignupClient />;
}
