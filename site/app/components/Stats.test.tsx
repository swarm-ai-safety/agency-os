import { render, screen } from "@testing-library/react";
import Stats from "./Stats";

describe("Stats", () => {
  it("renders baseline reliability metrics", () => {
    render(<Stats />);

    expect(screen.getByText("$0")).toBeInTheDocument();
    expect(screen.getByText("Payroll")).toBeInTheDocument();
    expect(screen.getByText("100%")).toBeInTheDocument();
    expect(screen.getByText("Governance Coverage")).toBeInTheDocument();
    expect(screen.getByText("146")).toBeInTheDocument();
    expect(screen.getByText("Sim Runs")).toBeInTheDocument();
  });
});
