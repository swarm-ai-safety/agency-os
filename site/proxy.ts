import { NextRequest, NextResponse } from "next/server";

import { resolveCanonicalRedirect } from "@/app/lib/canonical-host";

export function proxy(request: NextRequest): NextResponse {
  const redirectUrl = resolveCanonicalRedirect(request.nextUrl, request.headers);
  if (redirectUrl) {
    return NextResponse.redirect(redirectUrl, 308);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/:path*"],
};
