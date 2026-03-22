const CANONICAL_HOST = "zero-human-labs.com";

const REDIRECT_HOSTS = new Set([
  "zerohumanlabs.com",
  "www.zerohumanlabs.com",
  "www.zero-human-labs.com",
]);

function firstHeaderValue(value: string | null): string {
  if (!value) {
    return "";
  }
  return value.split(",")[0]?.trim() ?? "";
}

function normalizeHost(value: string): string {
  return value.split(":")[0]?.trim().toLowerCase() ?? "";
}

export function resolveCanonicalRedirect(
  url: URL,
  headers: Headers,
): URL | null {
  const forwardedHost = firstHeaderValue(headers.get("x-forwarded-host"));
  const hostHeader = firstHeaderValue(headers.get("host"));
  const candidateHost = forwardedHost || hostHeader || url.host;
  const hostname = normalizeHost(candidateHost);

  if (!REDIRECT_HOSTS.has(hostname)) {
    return null;
  }

  const forwardedProto = firstHeaderValue(headers.get("x-forwarded-proto"));
  const protocol = forwardedProto || url.protocol.replace(":", "") || "https";

  return new URL(`${protocol}://${CANONICAL_HOST}${url.pathname}${url.search}`);
}
