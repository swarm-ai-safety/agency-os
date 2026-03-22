import type { Metadata } from "next";
import ResetPasswordClient from "./ResetPasswordClient";

export const metadata: Metadata = {
  title: "Set New Password — Zero Human Labs",
  description: "Set a new password for your Zero Human Labs account.",
  alternates: { canonical: "/reset-password" },
  openGraph: { url: "/reset-password" },
};

export default function ResetPasswordPage() {
  return <ResetPasswordClient />;
}
