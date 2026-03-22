#!/usr/bin/env node

function extractInviteCode(rawUrl) {
  let parsed;
  try {
    parsed = new URL(rawUrl);
  } catch {
    return null;
  }

  const host = parsed.hostname.toLowerCase();
  if (host === "discord.gg" || host === "www.discord.gg") {
    return parsed.pathname.replace(/^\/+/, "").split("/")[0] || null;
  }

  if (host === "discord.com" || host === "www.discord.com") {
    const parts = parsed.pathname.split("/").filter(Boolean);
    if (parts.length >= 2 && parts[0] === "invite") {
      return parts[1] || null;
    }
  }

  return null;
}

const inviteUrl = process.env.NEXT_PUBLIC_DISCORD_INVITE_URL?.trim() ?? "";
if (!inviteUrl) {
  console.log("[discord-invite-check] No NEXT_PUBLIC_DISCORD_INVITE_URL set; homepage CTA remains waitlist.");
  process.exit(0);
}

const inviteCode = extractInviteCode(inviteUrl);
if (!inviteCode) {
  console.error("[discord-invite-check] Invalid Discord invite URL format:", inviteUrl);
  process.exit(1);
}

const endpoint = `https://discord.com/api/v9/invites/${encodeURIComponent(inviteCode)}?with_counts=true`;
const response = await fetch(endpoint);
const payload = await response.json().catch(() => ({}));

if (!response.ok || payload?.code === 10006) {
  console.error("[discord-invite-check] Discord invite is invalid or expired:", inviteUrl);
  console.error("[discord-invite-check] API response:", JSON.stringify(payload));
  process.exit(1);
}

console.log("[discord-invite-check] Invite validated:", inviteUrl);
