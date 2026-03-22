import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Nav from "./Nav";

describe("Nav", () => {
  it("opens and closes mobile navigation", async () => {
    const user = userEvent.setup();
    render(<Nav />);

    const menuButton = screen.getByRole("button", { name: "Open menu" });
    await user.click(menuButton);

    expect(screen.getByRole("button", { name: "Close menu" })).toBeInTheDocument();
    expect(screen.getByText("Navigate")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Close mobile navigation" }));

    expect(screen.getByRole("button", { name: "Open menu" })).toBeInTheDocument();
    expect(screen.queryByText("Navigate")).not.toBeInTheDocument();
  });
});
