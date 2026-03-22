import { NextRequest } from "next/server";

import { GET } from "./route";

describe("GET /api/auth/callback", () => {
  const originalEnv = process.env;

  afterEach(() => {
    process.env = originalEnv;
    vi.unstubAllGlobals();
  });

  it("retries session exchange against api subdomain when same-origin backend fails", async () => {
    process.env = {
      ...originalEnv,
      OIDC_ISSUER_URL: "https://issuer.example",
      OIDC_CLIENT_ID: "client-id",
      OIDC_CLIENT_SECRET: "client-secret",
      OIDC_BRIDGE_SECRET: "bridge-secret",
      AGENCY_OS_API_URL: "",
      NEXT_PUBLIC_API_URL: "",
    };

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            token_endpoint: "https://issuer.example/token",
            userinfo_endpoint: "https://issuer.example/userinfo",
          }),
          { status: 200 }
        )
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ access_token: "access-token" }), { status: 200 })
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ email: "user@example.com", sub: "oidc-subject-1" }),
          { status: 200 }
        )
      )
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "not found" }), { status: 404 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ session_token: "session-token-1" }), { status: 200 })
      );

    vi.stubGlobal("fetch", fetchMock);

    const request = new NextRequest(
      "https://zero-human-labs.com/api/auth/callback?code=abc123&state=expected-state",
      {
        headers: {
          cookie:
            "agency_os_oidc_state=expected-state; agency_os_oidc_return_to=/dashboard",
        },
      }
    );
    const response = await GET(request);

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("https://zero-human-labs.com/dashboard");
    expect(fetchMock).toHaveBeenCalledTimes(5);
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "https://zero-human-labs.com/api/v1/auth/oidc/session",
      expect.any(Object)
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      5,
      "https://api.zero-human-labs.com/api/v1/auth/oidc/session",
      expect.any(Object)
    );
  });

  it("does not derive api subdomain fallback for localhost", async () => {
    process.env = {
      ...originalEnv,
      OIDC_ISSUER_URL: "https://issuer.example",
      OIDC_CLIENT_ID: "client-id",
      OIDC_CLIENT_SECRET: "client-secret",
      OIDC_BRIDGE_SECRET: "bridge-secret",
      AGENCY_OS_API_URL: "",
      NEXT_PUBLIC_API_URL: "",
    };

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            token_endpoint: "https://issuer.example/token",
            userinfo_endpoint: "https://issuer.example/userinfo",
          }),
          { status: 200 }
        )
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ access_token: "access-token" }), { status: 200 })
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ email: "user@example.com", sub: "oidc-subject-1" }),
          { status: 200 }
        )
      )
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "not found" }), { status: 404 }));

    vi.stubGlobal("fetch", fetchMock);

    const request = new NextRequest(
      "http://localhost:3000/api/auth/callback?code=abc123&state=expected-state",
      {
        headers: {
          cookie:
            "agency_os_oidc_state=expected-state; agency_os_oidc_return_to=/dashboard",
        },
      }
    );
    const response = await GET(request);

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(
      "http://localhost:3000/dashboard?auth_error=oidc_failed"
    );
    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "http://localhost:3000/api/v1/auth/oidc/session",
      expect.any(Object)
    );
  });

  it("uses forwarded host when redirecting callback errors", async () => {
    process.env = {
      ...originalEnv,
      OIDC_ISSUER_URL: "https://issuer.example",
      OIDC_CLIENT_ID: "",
      OIDC_CLIENT_SECRET: "",
      OIDC_BRIDGE_SECRET: "",
    };

    const request = new NextRequest("http://site:3000/api/auth/callback?code=abc123", {
      headers: {
        "x-forwarded-proto": "https",
        "x-forwarded-host": "zero-human-labs.com",
      },
    });
    const response = await GET(request);

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(
      "https://zero-human-labs.com/dashboard?auth_error=misconfigured"
    );
  });
});
