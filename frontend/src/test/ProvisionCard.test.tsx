import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProvisionCard } from "../components/ProvisionCard";

describe("ProvisionCard", () => {
  it("reveals verified text and the official source on request", () => {
    render(<ProvisionCard provision={{
      provision_id: "BNS_303",
      title: "Theft",
      legal_status: "in_force",
      verified_text: "Verified legal text for the provision.",
      source_url: "https://www.indiacode.nic.in/example.pdf",
      source_pdf_page: 92,
    }} />);

    expect(screen.queryByText("Verified legal text for the provision.")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("Verified legal text for the provision.")).toBeVisible();
    expect(screen.getByRole("link", { name: /official source/i })).toHaveAttribute("href", "https://www.indiacode.nic.in/example.pdf");
  });
});
