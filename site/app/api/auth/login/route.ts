import crypto from "node:crypto";

import { NextRequest, NextResponse } from "next/server";
import {
  resolveBackendApiBase,
  setSessionCookie,
} from "../session/route";

const OIDC_STATE_COOKIE = "agency_os_oidc_state";
const OIDC_RETURN_TO_COOKIE = "agency_os_oidc_return_to";

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

/**
 * POST: Server-side login proxy for email+password auth.
 * Forwards credentials to the backend, intercepts session_token,
 * sets it as an httpOnly cookie, and returns only safe fields.
 * The session token never reaches browser JS.
 */
export async function POST(request: NextRequest): Promise<NextResponse> {
  let body: { identifier?: string; password?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid JSON" }, { status: 400 });
  }

  const { identifier, password } = body;
  if (!identifier || !password) {
    return NextResponse.json(
      { detail: "Email and password are required" },
      { status: 400 }
    );
  }

  const backendBase = resolveBackendApiBase(request);
  const clientIp =
    request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ||
    "unknown";

  let upstream: Response;
  try {
    upstream = await fetch(`${backendBase}/api/v1/tenants/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Forwarded-For": clientIp,
      },
      body: JSON.stringify({ identifier, password }),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json(
      { detail: "Backend unavailable" },
      { status: 502 }
    );
  }

  const payload = (await upstream.json().catch(() => ({}))) as Record<
    string,
    unknown
  >;

  if (!upstream.ok) {
    return NextResponse.json(
      { detail: payload.detail || "Invalid credentials" },
      { status: upstream.status }
    );
  }

  const sessionToken = payload.session_token;
  const expiresIn = payload.session_expires_in;
  if (typeof sessionToken !== "string" || !sessionToken) {
    return NextResponse.json(
      { detail: "Login succeeded but no session was issued" },
      { status: 502 }
    );
  }

  const clientPayload = {
    tenant_id: payload.tenant_id,
    tenant_name: payload.tenant_name,
  };

  const response = NextResponse.json(clientPayload, { status: 200 });
  setSessionCookie(
    request,
    response,
    sessionToken,
    typeof expiresIn === "number" ? expiresIn : undefined
  );
  return response;
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

function normalizeReturnTo(rawReturnTo: string | null): string {
  if (!rawReturnTo || !rawReturnTo.startsWith("/")) {
    return "/dashboard";
  }
  return rawReturnTo;
}

function buildDashboardErrorRedirect(
  request: NextRequest,
  returnTo: string,
  authError: string
): NextResponse {
  const redirectUrl = new URL(returnTo, resolveExternalOrigin(request));
  redirectUrl.searchParams.set("auth_error", authError);
  return NextResponse.redirect(redirectUrl);
}

function buildRedirectUri(request: NextRequest): string {
  const configured = process.env.OIDC_REDIRECT_URI?.trim();
  if (configured) {
    return configured;
  }
  return `${resolveExternalOrigin(request)}/api/auth/callback`;
}

async function discoverIssuer(issuer: string): Promise<{ authorization_endpoint: string }> {
  const response = await fetch(
    `${issuer.replace(/\/$/, "")}/.well-known/openid-configuration`,
    { cache: "no-store" }
  );
  if (!response.ok) {
    throw new Error("OIDC discovery failed");
  }
  return (await response.json()) as { authorization_endpoint: string };
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  const issuer = process.env.OIDC_ISSUER_URL?.trim();
  const clientId = process.env.OIDC_CLIENT_ID?.trim();
  const returnTo = normalizeReturnTo(request.nextUrl.searchParams.get("returnTo"));
  if (!issuer || !clientId) {
    return buildDashboardErrorRedirect(request, returnTo, "oidc_unavailable");
  }

  const state = crypto.randomBytes(24).toString("hex");
  const redirectUri = buildRedirectUri(request);
  const scopes = process.env.OIDC_SCOPES?.trim() || "openid profile email";

  try {
    const discovery = await discoverIssuer(issuer);
    const authorizeUrl = new URL(discovery.authorization_endpoint);
    authorizeUrl.searchParams.set("response_type", "code");
    authorizeUrl.searchParams.set("client_id", clientId);
    authorizeUrl.searchParams.set("redirect_uri", redirectUri);
    authorizeUrl.searchParams.set("scope", scopes);
    authorizeUrl.searchParams.set("state", state);

    const response = NextResponse.redirect(authorizeUrl);
    const cookieDomain = resolveCookieDomain(request);
    const secure = isHttpsRequest(request);
    response.cookies.set(OIDC_STATE_COOKIE, state, {
      httpOnly: true,
      secure,
      sameSite: "lax",
      path: "/",
      ...(cookieDomain ? { domain: cookieDomain } : {}),
      maxAge: 10 * 60,
    });
    response.cookies.set(OIDC_RETURN_TO_COOKIE, returnTo, {
      httpOnly: true,
      secure,
      sameSite: "lax",
      path: "/",
      ...(cookieDomain ? { domain: cookieDomain } : {}),
      maxAge: 10 * 60,
    });
    return response;
  } catch {
    return buildDashboardErrorRedirect(request, returnTo, "oidc_init_failed");
  }
}
