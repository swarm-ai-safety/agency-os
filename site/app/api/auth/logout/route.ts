import { NextRequest, NextResponse } from "next/server";

const SESSION_COOKIE = "agency_os_session";

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

export async function GET(request: NextRequest): Promise<NextResponse> {
  const returnTo = request.nextUrl.searchParams.get("returnTo") || "/dashboard";
  const response = NextResponse.redirect(new URL(returnTo, request.url));
  response.cookies.delete(SESSION_COOKIE);
  const cookieDomain = resolveCookieDomain(request);
  if (cookieDomain) {
    response.cookies.set(SESSION_COOKIE, "", {
      path: "/",
      domain: cookieDomain,
      maxAge: 0,
    });
  }
  return response;
}
