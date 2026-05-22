import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FeedbackFormButton } from "./FeedbackFormButton";

describe("FeedbackFormButton", () => {
  it("renders disabled when no form URL is configured", () => {
    render(<FeedbackFormButton formUrl="" />);

    const button = screen.getByRole("button", { name: "Formulário em breve" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-disabled", "true");
    expect(button).toHaveAttribute("title", "Formulário em breve");
  });

  it("renders as an external link when a form URL is configured", () => {
    render(<FeedbackFormButton formUrl="https://example.com/formulario" />);

    const link = screen.getByRole("link", { name: "Abrir formulário" });
    expect(link).toHaveAttribute("href", "https://example.com/formulario");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer");
  });
});
