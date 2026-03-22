import { describe, expect, it } from "vitest";

import { resolveCanonicalRedirect } from "./canonical-host";

function buildHeaders(
  values: Record<string, string | undefined>,
): Headers {
  const headers = new Headers();
  for (const [key, value] of Object.entries(values)) {
    if (value) {
      headers.set(key, value);
    }
  }
  return headers;
}

describe("resolveCanonicalRedirect", () => {
  it("redirects legacy hostnames to canonical host", () => {
    const target = resolveCanonicalRedirect(
      new URL("https://zerohumanlabs.com/quickstart?ref=google"),
      buildHeaders({
        host: "zerohumanlabs.com",
      }),
    );

    expect(target?.toString()).toBe(
      "https://zero-human-labs.com/quickstart?ref=google",
    );
  });

  it("uses forwarded host and protocol when present", () => {
    const target = resolveCanonicalRedirect(
      new URL("http://internal:3000/templates?foo=bar"),
      buildHeaders({
        "x-forwarded-host": "www.zerohumanlabs.com",
        "x-forwarded-proto": "https",
      }),
    );

    expect(target?.toString()).toBe("https://zero-human-labs.com/templates?foo=bar");
  });

  it("returns null for canonical host", () => {
    const target = resolveCanonicalRedirect(
      new URL("https://zero-human-labs.com/signup"),
      buildHeaders({
        host: "zero-human-labs.com",
      }),
    );

    expect(target).toBeNull();
  });

  it("returns null for localhost", () => {
    const target = resolveCanonicalRedirect(
      new URL("http://localhost:3000/"),
      buildHeaders({
        host: "localhost:3000",
      }),
    );

    expect(target).toBeNull();
  });
});
