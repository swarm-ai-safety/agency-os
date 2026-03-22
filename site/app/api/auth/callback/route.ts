import { NextRequest, NextResponse } from "next/server";

const OIDC_STATE_COOKIE = "agency_os_oidc_state";
const OIDC_RETURN_TO_COOKIE = "agency_os_oidc_return_to";
const SESSION_COOKIE = "agency_os_session";

type OidcDiscovery = {
  token_endpoint: string;
  userinfo_endpoint: string;
};

type OidcTokenResponse = {
  access_token?: string;
};

type OidcUserInfo = {
  email?: string;
  sub?: string;
  iss?: string;
};

function resolveCookieDomain(request: NextRequest): string | undefined {
  const configured = process.env.OIDC_COOKIE_DOMAIN?.trim();
  if (configured) {
    return configured.replace(/^\./, "");
  }

  const forwardedHost = request.headers
    .get("x-forwarded-host")
    ?.split(",")[0]
    ?.trim();
  const host = forwardedHost || request.nextUrl.host;
  const hostname = host.split(":")[0]?.toLowerCase() || "";
  const isLocalHost =
    hostname === "localhost" ||
    hostname.endsWith(".localhost") ||
    hostname === "127.0.0.1" ||
    hostname === "[::1]";
  const isIpv4 = /^\d+\.\d+\.\d+\.\d+$/.test(hostname);
  if (!hostname || isLocalHost || isIpv4) {
    return undefined;
  }

  return hostname.startsWith("www.") ? hostname.slice(4) : hostname;
}

function isHttpsRequest(request: NextRequest): boolean {
  const forwardedProto = request.headers
    .get("x-forwarded-proto")
    ?.split(",")[0]
    ?.trim()
    .toLowerCase();
  if (forwardedProto) {
    return forwardedProto === "https";
  }
  return request.nextUrl.protocol === "https:";
}

function resolveExternalOrigin(request: NextRequest): string {
  const forwardedHost = request.headers
    .get("x-forwarded-host")
    ?.split(",")[0]
    ?.trim();
  if (!forwardedHost) {
    return request.nextUrl.origin;
  }

  const forwardedProto = request.headers
    .get("x-forwarded-proto")
    ?.split(",")[0]
    ?.trim();
  const proto = forwardedProto || request.nextUrl.protocol.replace(/:$/, "");
  return `${proto}://${forwardedHost}`;
}

function resolveBackendApiBases(request: NextRequest): string[] {
  const configured = process.env.AGENCY_OS_API_URL?.trim();
  if (configured) {
    return [configured];
  }
  const publicBase = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (publicBase) {
    return [publicBase];
  }

  const externalOrigin = resolveExternalOrigin(request);
  const candidates = [externalOrigin];
  const externalUrl = new URL(externalOrigin);
  const { protocol, hostname, port } = externalUrl;
  const isLocalHost =
    hostname === "localhost" ||
    hostname.endsWith(".localhost") ||
    hostname === "127.0.0.1" ||
    hostname === "[::1]";
  const canDeriveApiSubdomain =
    !isLocalHost &&
    !hostname.startsWith("api.") &&
    hostname.includes(".") &&
    !/^\d+\.\d+\.\d+\.\d+$/.test(hostname);

  if (canDeriveApiSubdomain) {
    const derived = `${protocol}//api.${hostname}${port ? `:${port}` : ""}`;
    candidates.push(derived);
  }

  return candidates;
}

function buildRedirectUri(request: NextRequest): string {
  const configured = process.env.OIDC_REDIRECT_URI?.trim();
  if (configured) {
    return configured;
  }
  return `${resolveExternalOrigin(request)}/api/auth/callback`;
}

async function discoverIssuer(issuer: string): Promise<OidcDiscovery> {
  const response = await fetch(
    `${issuer.replace(/\/$/, "")}/.well-known/openid-configuration`,
    { cache: "no-store" }
  );
  if (!response.ok) {
    throw new Error("OIDC discovery failed");
  }
  return (await response.json()) as OidcDiscovery;
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  const externalOrigin = resolveExternalOrigin(request);
  const issuer = process.env.OIDC_ISSUER_URL?.trim();
  const clientId = process.env.OIDC_CLIENT_ID?.trim();
  const clientSecret = process.env.OIDC_CLIENT_SECRET?.trim();
  const bridgeSecret = process.env.OIDC_BRIDGE_SECRET?.trim();

  if (!issuer || !clientId || !clientSecret || !bridgeSecret) {
    return NextResponse.redirect(
      new URL("/dashboard?auth_error=misconfigured", externalOrigin)
    );
  }

  const code = request.nextUrl.searchParams.get("code") || "";
  const state = request.nextUrl.searchParams.get("state") || "";
  const expectedState = request.cookies.get(OIDC_STATE_COOKIE)?.value || "";
  const returnTo = request.cookies.get(OIDC_RETURN_TO_COOKIE)?.value || "/dashboard";

  if (!code || !state || !expectedState || state !== expectedState) {
    return NextResponse.redirect(
      new URL("/dashboard?auth_error=state_mismatch", externalOrigin)
    );
  }

  try {
    const discovery = await discoverIssuer(issuer);
    const redirectUri = buildRedirectUri(request);

    const tokenResponse = await fetch(discovery.token_endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: new URLSearchParams({
        grant_type: "authorization_code",
        code,
        client_id: clientId,
        client_secret: clientSecret,
        redirect_uri: redirectUri,
      }),
      cache: "no-store",
    });

    if (!tokenResponse.ok) {
      throw new Error("Token exchange failed");
    }

    const tokenPayload = (await tokenResponse.json()) as OidcTokenResponse;
    if (!tokenPayload.access_token) {
      throw new Error("Missing access token");
    }

    const userResponse = await fetch(discovery.userinfo_endpoint, {
      headers: {
        Authorization: `Bearer ${tokenPayload.access_token}`,
      },
      cache: "no-store",
    });

    if (!userResponse.ok) {
      throw new Error("Userinfo fetch failed");
    }

    const user = (await userResponse.json()) as OidcUserInfo;
    if (!user.email || !user.sub) {
      throw new Error("OIDC response missing required claims");
    }

    const backendCandidates = resolveBackendApiBases(request);
    let sessionToken: string | null = null;

    for (const backendBase of backendCandidates) {
      try {
        const sessionResponse = await fetch(`${backendBase}/api/v1/auth/oidc/session`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-OIDC-Bridge-Secret": bridgeSecret,
          },
          body: JSON.stringify({
            email: user.email,
            subject: user.sub,
            issuer: user.iss || issuer,
          }),
          cache: "no-store",
        });

        const sessionPayload = (await sessionResponse.json().catch(() => null)) as
          | { session_token?: string }
          | null;

        if (sessionResponse.ok && sessionPayload?.session_token) {
          sessionToken = sessionPayload.session_token;
          break;
        }
      } catch {
        // Keep trying alternate backend candidates before failing the sign-in flow.
      }
    }

    if (!sessionToken) {
      throw new Error("Session creation failed");
    }

    const response = NextResponse.redirect(new URL(returnTo, externalOrigin));
    const cookieDomain = resolveCookieDomain(request);
    const secure = isHttpsRequest(request);
    response.cookies.set(SESSION_COOKIE, sessionToken, {
      httpOnly: true,
      secure,
      sameSite: "lax",
      path: "/",
      ...(cookieDomain ? { domain: cookieDomain } : {}),
      maxAge: 8 * 60 * 60,
    });
    response.cookies.delete(OIDC_STATE_COOKIE);
    response.cookies.delete(OIDC_RETURN_TO_COOKIE);
    const deleteOptions = cookieDomain
      ? { path: "/", domain: cookieDomain, maxAge: 0 }
      : { path: "/", maxAge: 0 };
    response.cookies.set(OIDC_STATE_COOKIE, "", deleteOptions);
    response.cookies.set(OIDC_RETURN_TO_COOKIE, "", deleteOptions);
    return response;
  } catch {
    return NextResponse.redirect(new URL("/dashboard?auth_error=oidc_failed", externalOrigin));
  }
}
