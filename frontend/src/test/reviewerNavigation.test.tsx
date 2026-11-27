import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CasesPanel } from "../components/CasesPanel";
import { Sidebar } from "../components/Sidebar";
import type { LegalAiApi } from "../api";

describe("reviewer navigation", () => {
  it("starts with research chat as the primary action", () => {
    const onNew = vi.fn();
    const onCases = vi.fn();
    render(<Sidebar user={{ uid: "reviewer", displayName: "Krishna", mode: "demo" }}
      sessions={[]} activeSessionId={null} open={true} isReviewer={true}
      onSelect={vi.fn()} onNew={onNew} onCases={onCases} onSettings={vi.fn()}
      onLogout={vi.fn()} onClose={vi.fn()} onRemove={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "New research chat" }));
    expect(onNew).toHaveBeenCalledOnce();
    expect(onCases).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Reports" }));
    expect(onCases).toHaveBeenCalledOnce();
  });

  it("opens reports in the side panel and expands only on request", () => {
    const api = { listReviewCases: vi.fn().mockResolvedValue([]) } as unknown as LegalAiApi;
    render(<CasesPanel api={api} cases={[]} drafts={[]} isAdmin={true}
      onClose={vi.fn()} onRefresh={vi.fn().mockResolvedValue(undefined)}
      onOpenDraft={vi.fn()} onOpenSession={vi.fn()} />);

    const panel = screen.getByRole("dialog", { name: "Reports to review" });
    expect(panel).not.toHaveClass("cases-drawer--expanded");
    fireEvent.click(screen.getByRole("button", { name: "Open full view" }));
    expect(panel).toHaveClass("cases-drawer--expanded");
    fireEvent.click(screen.getByRole("button", { name: "Side view" }));
    expect(panel).not.toHaveClass("cases-drawer--expanded");
  });
});
