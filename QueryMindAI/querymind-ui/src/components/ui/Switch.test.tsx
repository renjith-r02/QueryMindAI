import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SwitchField } from "@/components/ui/Switch";

describe("SwitchField", () => {
  it("exposes switch state and toggles on click", async () => {
    const onChange = vi.fn();
    render(<SwitchField label="Explanation mode" detail="Show a breakdown." checked={false} onChange={onChange} />);

    const control = screen.getByRole("switch", { name: "Explanation mode" });
    expect(control).toHaveAttribute("aria-checked", "false");

    await userEvent.click(control);
    expect(onChange).toHaveBeenCalledWith(true);
  });
});
