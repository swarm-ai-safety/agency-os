const DISCORD_HOSTS = new Set(["discord.gg", "www.discord.gg", "discord.com", "www.discord.com"]);

export type CommunityCtaConfig = {
  href: string;
  label: string;
  body: string;
  isLiveDiscord: boolean;
};

function parseDiscordInviteCode(rawUrl: string): string | null {
  let parsed: URL;
  try {
    parsed = new URL(rawUrl);
  } catch {
    return null;
  }

  if (!DISCORD_HOSTS.has(parsed.hostname)) {
    return null;
  }

  if (parsed.hostname.endsWith("discord.gg")) {
    const code = parsed.pathname.replace(/^\/+/, "").split("/")[0];
    return code || null;
  }

  const parts = parsed.pathname.split("/").filter(Boolean);
  if (parts.length >= 2 && parts[0] === "invite") {
    return parts[1] || null;
  }

  return null;
}

export function getCommunityCtaConfig(inviteUrl = process.env.NEXT_PUBLIC_DISCORD_INVITE_URL): CommunityCtaConfig {
  const normalizedInvite = inviteUrl?.trim() ?? "";
  const inviteCode = normalizedInvite ? parseDiscordInviteCode(normalizedInvite) : null;
  const hasValidInviteFormat = Boolean(inviteCode);

  if (hasValidInviteFormat) {
    return {
      href: normalizedInvite,
      label: "Join Discord ->",
      body:
        "Join founders running zero-human companies on Discord. Share configs, debug governance settings, and show what you've shipped.",
      isLiveDiscord: true,
    };
  }

  return {
    href: "/signup?source=community",
    label: "Join Community Waitlist ->",
    body:
      "The founder Discord is opening soon. Join the waitlist for the launch invite, builder sessions, and early community updates.",
    isLiveDiscord: false,
  };
}
