import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { renderRoute } from "@/test/renderRoute";

async function openPage() {
  renderRoute("/admin/guardrails");
  expect(await screen.findByRole("heading", { level: 1, name: "Guardrails" })).toBeInTheDocument();
}

const keywords = () => screen.getByRole("list", { name: "Blocked SQL keywords" });
const columns = () => screen.getByRole("list", { name: "Restricted columns" });

describe("Guardrails", () => {
  beforeEach(() => localStorage.clear());

  it("loads the policy, with the baseline locked", async () => {
    await openPage();
    expect(screen.getByText("Built-in defaults; not saved yet.", { exact: false })).toBeInTheDocument();
    expect(screen.getAllByText("Always on")).toHaveLength(4);
    // Locked rules have no switch; the sensitive-data rule can be switched off.
    expect(screen.queryByRole("switch", { name: "Deleting data" })).not.toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Passwords and payment card data" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(within(keywords()).getByText("DELETE").parentElement).toHaveTextContent("DELETE");
    expect(within(keywords()).queryByRole("button", { name: "Remove DELETE" })).not.toBeInTheDocument();
    expect(within(keywords()).getByRole("button", { name: "Remove SET" })).toBeInTheDocument();
    expect(within(columns()).getByText("users.password_hash")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled(); // nothing changed yet
  });

  it("edits and saves the policy through the API", async () => {
    await openPage();
    await userEvent.click(screen.getByRole("switch", { name: "Passwords and payment card data" }));
    await userEvent.type(screen.getByLabelText("Add to blocked sql keywords"), "sleep{Enter}");
    expect(within(keywords()).getByText("SLEEP")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Add to restricted columns"), "bad name{Enter}");
    expect(screen.getByText("Use column or table.column (letters, digits and _).")).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText("Add to restricted columns"));
    await userEvent.type(screen.getByLabelText("Add to restricted columns"), "Users.Phone{Enter}");
    expect(within(columns()).getByText("users.phone")).toBeInTheDocument();
    await userEvent.clear(screen.getByRole("spinbutton", { name: /Max rows per query/ }));
    await userEvent.type(screen.getByRole("spinbutton", { name: /Max rows per query/ }), "250");

    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Guardrails saved. New questions use them now.")).toBeInTheDocument();
    expect(screen.getByText(/^Every question .* Last saved/)).toBeInTheDocument();
    const stored = JSON.parse(localStorage.getItem("querymind-mock-guardrails")!);
    expect(stored.blocked_sql_keywords).toContain("SLEEP");
    expect(stored.restricted_columns).toEqual(["users.password_hash", "users.phone"]);
    expect(stored.max_rows).toBe(250);
    expect(stored.question_rules.find((rule: { id: string }) => rule.id === "sensitive-data").enabled).toBe(false);
  });

  it("adds a custom rule and tests questions and SQL against unsaved changes", async () => {
    await openPage();
    await userEvent.click(screen.getByRole("button", { name: "Add rule" }));
    const editor = screen.getByRole("group", { name: "Custom rule settings" });
    await userEvent.clear(within(editor).getByLabelText("Message shown to the user"));
    await userEvent.type(within(editor).getByLabelText("Message shown to the user"), "Salaries are private.");
    await userEvent.type(within(editor).getByLabelText("Patterns"), "\\bsalar");

    await userEvent.type(screen.getByLabelText("Question"), "average salary by team");
    await userEvent.click(screen.getByRole("button", { name: "Check" }));
    expect(await screen.findByText('Question refused by "custom-rule": Salaries are private.')).toBeInTheDocument();

    await userEvent.clear(screen.getByLabelText("Question"));
    await userEvent.type(screen.getByLabelText("SQL"), "SELECT email, password_hash FROM users");
    await userEvent.click(screen.getByRole("button", { name: "Check" }));
    expect(await screen.findByText("SQL refused: column password_hash is restricted.")).toBeInTheDocument();

    await userEvent.click(within(columns()).getByRole("button", { name: "Remove users.password_hash" }));
    await userEvent.click(screen.getByRole("button", { name: "Check" }));
    expect(await screen.findByText("SQL allowed to run.")).toBeInTheDocument();
  });

  it("shows the server's refusal when the baseline would be weakened, and restores defaults", async () => {
    await openPage();
    await userEvent.click(screen.getByRole("button", { name: "Edit Deleting data" }));
    await userEvent.clear(
      within(screen.getByRole("group", { name: "Deleting data settings" })).getByLabelText("Patterns"),
    );
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText(/built-in patterns of 'delete-data' cannot be removed/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Discard changes" }));
    await userEvent.click(within(keywords()).getByRole("button", { name: "Remove SET" }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText("Guardrails saved. New questions use them now.");
    expect(within(keywords()).queryByText("SET")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Restore defaults" }));
    await userEvent.click(screen.getByRole("button", { name: "Restore" }));
    expect(await screen.findByText("Built-in guardrails restored.")).toBeInTheDocument();
    expect(within(keywords()).getByText("SET")).toBeInTheDocument();
  });
});
