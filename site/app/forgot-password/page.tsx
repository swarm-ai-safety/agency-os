import type { Metadata } from "next";
import ForgotPasswordClient from "./ForgotPasswordClient";

export const metadata: Metadata = {
  title: "Reset Password — Zero Human Labs",
  description: "Request a password reset link for your Zero Human Labs account.",
  alternates: { canonical: "/forgot-password" },
  openGraph: { url: "/forgot-password" },
};

export default function ForgotPasswordPage() {
  return <ForgotPasswordClient />;
}
