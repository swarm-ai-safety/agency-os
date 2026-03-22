import { render, screen } from "@testing-library/react";
import Hero from "../Hero";

describe("Hero", () => {
  it("renders the primary headline and CTA", () => {
    render(<Hero />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Your agents are"
    );
    expect(
      screen.getByRole("link", { name: "Deploy Governed Agents" })
    ).toBeInTheDocument();
  });
});
