import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Footer from "./Footer";

describe("Footer", () => {
  it("renders the current year and footer links", () => {
    render(<Footer />);

    expect(screen.getByText("GitHub")).toBeInTheDocument();
    expect(screen.getByText("Research")).toBeInTheDocument();
    expect(
      screen.getByText(new RegExp(String(new Date().getFullYear()))),
    ).toBeInTheDocument();
  });
});
