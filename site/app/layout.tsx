import type { Metadata } from "next";
import Script from "next/script";
import "./globals.css";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://zero-human-labs.com";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: "Zero Human Labs — Your Next Startup Doesn't Need Employees",
  description:
    "Launch autonomous AI companies from a single YAML file. Agents compete for tasks, govern themselves, and ship your product — backed by multi-agent simulation research.",
  alternates: {
    canonical: "/",
  },
  openGraph: {
    title: "Zero Human Labs — Your Next Startup Doesn't Need Employees",
    description:
      "Your next startup doesn't need employees. Launch an autonomous AI company from a single YAML file.",
    type: "website",
    url: "/",
    images: [
      {
        url: "/og-image.png",
        width: 1200,
        height: 630,
        alt: "Zero Human Labs",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Zero Human Labs — Your Next Startup Doesn't Need Employees",
    description:
      "Launch autonomous AI companies from a single YAML file.",
    images: ["/og-image.png"],
  },
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "any" },
      { url: "/favicon-16x16.png", sizes: "16x16", type: "image/png" },
      { url: "/favicon-32x32.png", sizes: "32x32", type: "image/png" },
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180" }],
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head />
      <body className="antialiased">
        <Script
          id="organization-jsonld"
          type="application/ld+json"
          strategy="afterInteractive"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify({
              "@context": "https://schema.org",
              "@type": "Organization",
              name: "Zero Human Labs",
              url: SITE_URL,
              logo: `${SITE_URL}/favicon-32x32.png`,
            }),
          }}
        />
        <Script
          id="software-jsonld"
          type="application/ld+json"
          strategy="afterInteractive"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify({
              "@context": "https://schema.org",
              "@type": "SoftwareApplication",
              name: "Agency OS",
              applicationCategory: "DeveloperApplication",
              operatingSystem: "Web",
              url: SITE_URL,
              offers: {
                "@type": "Offer",
                price: "0",
                priceCurrency: "USD",
              },
              provider: {
                "@type": "Organization",
                name: "Zero Human Labs",
              },
            }),
          }}
        />
        {children}
        {process.env.NEXT_PUBLIC_PLAUSIBLE_DOMAIN && (
          <Script
            defer
            data-domain={process.env.NEXT_PUBLIC_PLAUSIBLE_DOMAIN}
            src="https://plausible.io/js/script.tagged-events.js"
            strategy="afterInteractive"
          />
        )}
      </body>
    </html>
  );
}
