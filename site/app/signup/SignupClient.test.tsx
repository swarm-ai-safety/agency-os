import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SignupClient from "./SignupClient";

const STORAGE_KEY = "zhl_dashboard_api_key";

function successResponse(apiKey = "zhl_test_key_abc123") {
  return new Response(
    JSON.stringify({ tenant_id: "t1", name: "Acme Labs", api_key: apiKey }),
    { status: 200, headers: { "Content-Type": "application/json" } }
  );
}

function errorResponse(detail = "Email already registered") {
  return new Response(JSON.stringify({ detail }), {
    status: 409,
    headers: { "Content-Type": "application/json" },
  });
}

describe("SignupClient auth persistence", () => {
  let locationHref: string;

  beforeEach(() => {
    sessionStorage.clear();
    locationHref = window.location.href;

    // Stub location.href setter to capture navigations without error
    Object.defineProperty(window, "location", {
      writable: true,
      value: { ...window.location, href: locationHref },
    });

    vi.stubGlobal(
      "fetch",
      vi.fn(async () => successResponse())
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    sessionStorage.clear();
  });

  async function submitSignup() {
    render(<SignupClient />);
    fireEvent.change(screen.getByPlaceholderText("Acme Labs"), {
      target: { value: "Test Co" },
    });
    fireEvent.change(screen.getByPlaceholderText("you@company.com"), {
      target: { value: "test@example.com" },
    });
    fireEvent.change(screen.getByPlaceholderText("At least 8 characters"), {
      target: { value: "password123" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Create Tenant/i }));
    await waitFor(() =>
      expect(screen.getByText("zhl_test_key_abc123")).toBeInTheDocument()
    );
  }

  it("stores API key in sessionStorage after successful signup", async () => {
    await submitSignup();

    expect(sessionStorage.getItem(STORAGE_KEY)).toBe("zhl_test_key_abc123");
  });

  it("does not store key on signup failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => errorResponse())
    );

    render(<SignupClient />);
    fireEvent.change(screen.getByPlaceholderText("Acme Labs"), {
      target: { value: "Test Co" },
    });
    fireEvent.change(screen.getByPlaceholderText("you@company.com"), {
      target: { value: "dup@example.com" },
    });
    fireEvent.change(screen.getByPlaceholderText("At least 8 characters"), {
      target: { value: "password123" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Create Tenant/i }));

    await waitFor(() =>
      expect(screen.getByText("Email already registered")).toBeInTheDocument()
    );
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("persists key to sessionStorage and navigates to /dashboard on Dashboard click", async () => {
    await submitSignup();

    // Clear storage to verify the openDashboard function re-sets it
    sessionStorage.removeItem(STORAGE_KEY);

    const dashboardLink = screen.getByRole("button", { name: "Dashboard" });
    fireEvent.click(dashboardLink);

    expect(sessionStorage.getItem(STORAGE_KEY)).toBe("zhl_test_key_abc123");
    expect(window.location.href).toBe("/dashboard");
  });

  it("does not expose API key in URL query parameters", async () => {
    await submitSignup();

    // After signup, location should not contain key in query params
    expect(window.location.href).not.toContain("key=");
    expect(window.location.href).not.toContain("api_key=");
    expect(window.location.href).not.toContain("zhl_test_key");

    // Click dashboard and verify same
    fireEvent.click(screen.getByRole("button", { name: "Dashboard" }));
    expect(window.location.href).toBe("/dashboard");
    expect(window.location.href).not.toContain("key=");
  });

  it("gracefully handles sessionStorage failure without breaking signup", async () => {
    // Make sessionStorage.setItem throw
    const originalSetItem = sessionStorage.setItem.bind(sessionStorage);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("QuotaExceededError");
    });

    vi.stubGlobal(
      "fetch",
      vi.fn(async () => successResponse())
    );

    render(<SignupClient />);
    fireEvent.change(screen.getByPlaceholderText("Acme Labs"), {
      target: { value: "Test Co" },
    });
    fireEvent.change(screen.getByPlaceholderText("you@company.com"), {
      target: { value: "test@example.com" },
    });
    fireEvent.change(screen.getByPlaceholderText("At least 8 characters"), {
      target: { value: "password123" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Create Tenant/i }));

    // Signup should still succeed even though sessionStorage failed
    await waitFor(() =>
      expect(screen.getByText("zhl_test_key_abc123")).toBeInTheDocument()
    );
    expect(screen.getByText(/Welcome, Acme Labs/)).toBeInTheDocument();
  });

  it("shows success page with copy button and dashboard CTA after signup", async () => {
    await submitSignup();

    expect(screen.getByText(/Welcome, Acme Labs/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Copy API key/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Dashboard" })).toBeInTheDocument();
  });

  it("sends correct payload to /api/auth/signup", async () => {
    const fetchMock = vi.fn(async () => successResponse());
    vi.stubGlobal("fetch", fetchMock);

    await submitSignup();

    expect(fetchMock).toHaveBeenCalledWith("/api/auth/signup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: "Test Co",
        email: "test@example.com",
        password: "password123",
      }),
    });
  });
});
