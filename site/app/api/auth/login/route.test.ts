import { NextRequest } from "next/server";

import { GET } from "./route";

describe("GET /api/auth/login", () => {
  const originalEnv = process.env;

  afterEach(() => {
    process.env = originalEnv;
  });

  it("redirects to dashboard with auth_error when OIDC is not configured", async () => {
    process.env = {
      ...originalEnv,
      OIDC_ISSUER_URL: "",
      OIDC_CLIENT_ID: "",
    };

    const request = new NextRequest(
      "https://zero-human-labs.com/api/auth/login?returnTo=/dashboard"
    );
    const response = await GET(request);

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(
      "https://zero-human-labs.com/dashboard?auth_error=oidc_unavailable"
    );
  });

  it("ignores unsafe returnTo values", async () => {
    process.env = {
      ...originalEnv,
      OIDC_ISSUER_URL: "",
      OIDC_CLIENT_ID: "",
    };

    const request = new NextRequest(
      "https://zero-human-labs.com/api/auth/login?returnTo=https://attacker.example"
    );
    const response = await GET(request);

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(
      "https://zero-human-labs.com/dashboard?auth_error=oidc_unavailable"
    );
  });

  it("builds dashboard redirects from forwarded host headers", async () => {
    process.env = {
      ...originalEnv,
      OIDC_ISSUER_URL: "",
      OIDC_CLIENT_ID: "",
    };

    const request = new NextRequest(
      "http://site:3000/api/auth/login?returnTo=/dashboard",
      {
        headers: {
          "x-forwarded-proto": "https",
          "x-forwarded-host": "zero-human-labs.com",
        },
      }
    );
    const response = await GET(request);

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(
      "https://zero-human-labs.com/dashboard?auth_error=oidc_unavailable"
    );
  });
});
