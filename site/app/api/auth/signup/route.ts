import { NextRequest, NextResponse } from "next/server";
import {
  resolveBackendApiBase,
  setSessionCookie,
} from "../session/route";

/**
 * Server-side signup proxy.  Forwards name/email/password to the
 * backend, intercepts session_token, sets it as an httpOnly cookie,
 * and returns only safe fields (including api_key) to the client.
 * The session token never reaches browser JS.
 */
export async function POST(request: NextRequest): Promise<NextResponse> {
  let body: { name?: string; email?: string; password?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid JSON" }, { status: 400 });
  }

  const { name, email, password } = body;
  if (!name || !password) {
    return NextResponse.json(
      { detail: "Name and password are required" },
      { status: 400 }
    );
  }

  const backendBase = resolveBackendApiBase(request);
  const clientIp =
    request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ||
    "unknown";

  let upstream: Response;
  try {
    upstream = await fetch(`${backendBase}/api/v1/tenants`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Forwarded-For": clientIp,
      },
      body: JSON.stringify({ name, email, password }),
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
      { detail: payload.detail },
      { status: upstream.status }
    );
  }

  const sessionToken = payload.session_token;
  const expiresIn = payload.session_expires_in;

  // Return api_key (shown once to user) but strip session_token
  const clientPayload = {
    tenant_id: payload.tenant_id,
    name: payload.name,
    api_key: payload.api_key,
  };

  const response = NextResponse.json(clientPayload, { status: 200 });

  if (typeof sessionToken === "string" && sessionToken) {
    setSessionCookie(
      request,
      response,
      sessionToken,
      typeof expiresIn === "number" ? expiresIn : undefined
    );
  }

  return response;
}
