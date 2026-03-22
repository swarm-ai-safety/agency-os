import { NextRequest, NextResponse } from "next/server";

const SESSION_COOKIE = "agency_os_session";

/**
 * Allowed dashboard proxy path prefixes.  The catch-all route forwards
 * requests to the backend API, so we must restrict which paths are
 * reachable to prevent path-traversal / SSRF attacks.
 */
const ALLOWED_PREFIXES = [
  "orgs/",
  "tenants/",
];

function isPathAllowed(segments: string[]): boolean {
  // Reject path traversal attempts
  if (segments.some((s) => s === ".." || s === "." || s === "")) {
    return false;
  }
  const joined = segments.join("/");
  return ALLOWED_PREFIXES.some((prefix) => joined.startsWith(prefix));
}

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

async function proxy(request: NextRequest, path: string[]): Promise<NextResponse> {
  const sessionToken = request.cookies.get(SESSION_COOKIE)?.value;
  if (!sessionToken) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  }

  if (!isPathAllowed(path)) {
    return NextResponse.json({ detail: "Not found" }, { status: 404 });
  }

  const backendBase = resolveBackendApiBase(request);
  const target = new URL(`${backendBase}/api/v1/${path.join("/")}`);
  target.search = request.nextUrl.search;

  const headers = new Headers();
  headers.set("Authorization", `Bearer ${sessionToken}`);
  const contentType = request.headers.get("content-type");
  if (contentType) {
    headers.set("Content-Type", contentType);
  }

  const method = request.method.toUpperCase();
  const body = method === "GET" || method === "HEAD" ? undefined : await request.text();

  const upstream = await fetch(target, {
    method,
    headers,
    body,
    cache: "no-store",
  });

  const payload = await upstream.text();
  const responseHeaders = new Headers();
  const upstreamType = upstream.headers.get("content-type");
  if (upstreamType) {
    responseHeaders.set("content-type", upstreamType);
  }

  return new NextResponse(payload, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
): Promise<NextResponse> {
  return proxy(request, (await context.params).path);
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
): Promise<NextResponse> {
  return proxy(request, (await context.params).path);
}

export async function PATCH(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
): Promise<NextResponse> {
  return proxy(request, (await context.params).path);
}

export async function PUT(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
): Promise<NextResponse> {
  return proxy(request, (await context.params).path);
}

export async function DELETE(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
): Promise<NextResponse> {
  return proxy(request, (await context.params).path);
}
