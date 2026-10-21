import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { renderRoute } from "@/test/renderRoute";

const field = (name: string) => screen.getByLabelText(name, { exact: true });

describe("Model config", () => {
  it("selects OpenAI, sets its model and key, and saves", async () => {
    renderRoute("/admin/model");
    expect(await screen.findByRole("heading", { level: 1, name: "Model config" })).toBeInTheDocument();
    expect(screen.getByText("gemini-3.8-flash", { selector: ".font-mono" })).toBeInTheDocument(); // in use

    await userEvent.click(screen.getByRole("radio", { name: /OpenAI/ }));
    const openai = screen.getByRole("region", { name: "OpenAI settings" });
    await userEvent.type(within(openai).getByLabelText("Model"), "gpt-6-sol");
    await userEvent.type(within(openai).getByLabelText("API key"), "sk-test-abcdefgh9876");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("Saved. New questions use gpt-6-sol.")).toBeInTheDocument();
    // The key is now write-only: only its hint is shown.
    expect(within(openai).getByText("…9876")).toBeInTheDocument();
    expect(within(openai).queryByLabelText("API key", { selector: "input" })).not.toBeInTheDocument();
    expect(JSON.stringify(localStorage)).toContain("sk-test-abcdefgh9876"); // mock backend stored it

    await userEvent.click(screen.getByRole("button", { name: "Test saved connection" }));
    expect(await screen.findByText(/gpt-6-sol would be checked/)).toBeInTheDocument();
  });

  it("removes a saved key only after confirming with save", async () => {
    renderRoute("/admin/model");
    const gemini = await screen.findByRole("region", { name: "Google Gemini settings" });
    await userEvent.type(within(gemini).getByLabelText("API key"), "gemini-key-000011112222");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await within(gemini).findByText("…2222");

    await userEvent.click(within(gemini).getByRole("button", { name: "Remove" }));
    expect(within(gemini).getByText("Will be removed when you save")).toBeInTheDocument();
    await userEvent.click(within(gemini).getByRole("button", { name: "Undo" }));
    expect(within(gemini).getByText("…2222")).toBeInTheDocument();

    await userEvent.click(within(gemini).getByRole("button", { name: "Remove" }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText(/^Saved\./);
    expect(within(gemini).getByLabelText("API key")).toHaveAttribute("placeholder", "Not set");
  });
});

describe("Okta", () => {
  it("tests the connection and saves the settings", async () => {
    renderRoute("/admin/okta");
    expect(await screen.findByRole("heading", { level: 1, name: "Okta" })).toBeInTheDocument();
    expect(screen.getByText(/QueryMind is still open without login/)).toBeInTheDocument();

    await userEvent.type(field("Org URL"), "https://acme.okta.com");
    expect(screen.getByText("https://acme.okta.com/oauth2/default")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Test connection" }));
    expect(await screen.findByText("https://acme.okta.com/oauth2/default/v1/token")).toBeInTheDocument();

    await userEvent.type(field("Client ID"), "0oa1abc");
    await userEvent.type(field("Client secret"), "okta-secret-5678");
    await userEvent.type(field("Admin group"), "QueryMind Admins");
    await userEvent.click(screen.getByRole("switch", { name: "Enable Okta sign-in" }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("Okta settings saved.")).toBeInTheDocument();
    expect(screen.getByText("…5678")).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Enable Okta sign-in" })).toHaveAttribute("aria-checked", "true");
  });
});

describe("admin navigation", () => {
  it("has Okta SSO and no Examples tab", async () => {
    renderRoute("/admin");
    const nav = (await screen.findAllByRole("navigation"))[0]!;
    expect(within(nav).getByRole("link", { name: "Okta SSO" })).toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "Examples" })).not.toBeInTheDocument();
  });
});
