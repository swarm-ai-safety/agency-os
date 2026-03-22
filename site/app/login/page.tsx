import type { Metadata } from "next";
import LoginClient from "./LoginClient";

export const metadata: Metadata = {
  title: "Log In — Zero Human Labs",
  description:
    "Log in to your Zero Human Labs account to access your dashboard and API.",
  alternates: {
    canonical: "/login",
  },
  openGraph: {
    url: "/login",
  },
};

export default function LoginPage() {
  return <LoginClient />;
}
