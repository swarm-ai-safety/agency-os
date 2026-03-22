import { describe, expect, it } from "vitest";
import { getCommunityCtaConfig } from "./community-cta";

describe("community CTA config", () => {
  it("falls back to waitlist when no invite is configured", () => {
    const cta = getCommunityCtaConfig(undefined);

    expect(cta.isLiveDiscord).toBe(false);
    expect(cta.href).toBe("/signup?source=community");
    expect(cta.label).toBe("Join Community Waitlist ->");
  });

  it("falls back to waitlist when invite format is invalid", () => {
    const cta = getCommunityCtaConfig("https://example.com/community");

    expect(cta.isLiveDiscord).toBe(false);
    expect(cta.href).toBe("/signup?source=community");
  });

  it("enables live Discord CTA for a valid invite URL", () => {
    const cta = getCommunityCtaConfig("https://discord.gg/agency-os");

    expect(cta.isLiveDiscord).toBe(true);
    expect(cta.href).toBe("https://discord.gg/agency-os");
    expect(cta.label).toBe("Join Discord ->");
  });
});
