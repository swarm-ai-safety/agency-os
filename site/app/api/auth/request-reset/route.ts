import { NextRequest, NextResponse } from "next/server";
import { resolveBackendApiBase } from "../session/route";

export async function POST(request: NextRequest): Promise<NextResponse> {
  let body: { email?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid JSON" }, { status: 400 });
  }

  if (!body.email) {
    return NextResponse.json(
      { detail: "Email is required" },
      { status: 400 }
    );
  }

  const backendBase = resolveBackendApiBase(request);
  const clientIp =
    request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "unknown";

  let upstream: Response;
  try {
    upstream = await fetch(
      `${backendBase}/api/v1/tenants/request-password-reset`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Forwarded-For": clientIp,
        },
        body: JSON.stringify({ email: body.email }),
        cache: "no-store",
      }
    );
  } catch {
    return NextResponse.json(
      { detail: "Backend unavailable" },
      { status: 502 }
    );
  }

  const payload = await upstream.json().catch(() => ({}));
  return NextResponse.json(payload, { status: upstream.status });
}
