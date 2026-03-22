import { NextRequest, NextResponse } from "next/server";

const SESSION_COOKIE = "agency_os_session";

function resolveBackendApiBase(request: NextRequest): string {
  const configured = process.env.AGENCY_OS_API_URL?.trim();
  if (configured) {
    return configured;
  }
  const publicBase = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (publicBase) {
    return publicBase;
  }
  return request.nextUrl.origin;
}

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

const MAX_SESSION_SECONDS = 30 * 24 * 60 * 60;

/**
 * Set the session cookie from a backend response that contains
 * session_token + session_expires_in.  Strips the token from the
 * JSON body returned to the client so it never reaches JS.
 */
export function setSessionCookie(
  request: NextRequest,
  clientResponse: NextResponse,
  sessionToken: string,
  expiresIn?: number
): void {
  const maxAge =
    typeof expiresIn === "number" && expiresIn > 0
      ? Math.min(expiresIn, MAX_SESSION_SECONDS)
      : 8 * 60 * 60;

  const cookieDomain = resolveCookieDomain(request);
  const secure = isHttpsRequest(request);

  clientResponse.cookies.set(SESSION_COOKIE, sessionToken, {
    httpOnly: true,
    secure,
    sameSite: "lax",
    path: "/",
    ...(cookieDomain ? { domain: cookieDomain } : {}),
    maxAge,
  });
}

export { resolveBackendApiBase };

/**
 * DELETE: clear the session cookie (logout).
 */
export async function DELETE(request: NextRequest): Promise<NextResponse> {
  const cookieDomain = resolveCookieDomain(request);
  const response = NextResponse.json({ ok: true });
  const deleteOptions: Record<string, unknown> = { path: "/", maxAge: 0 };
  if (cookieDomain) {
    deleteOptions.domain = cookieDomain;
  }
  response.cookies.set(SESSION_COOKIE, "", deleteOptions);
  return response;
}
