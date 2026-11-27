import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, LegalAiApi } from "../api";

describe("LegalAiApi", () => {
  afterEach(() => vi.restoreAllMocks());

  it("keeps authentication separate from message text", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
      user_message: { id: "u1", role: "user", text: "My phone was stolen", created_at: "2026-09-27T00:00:00Z" },
      assistant_message: { id: "a1", role: "assistant", text: "Possible provision", created_at: "2026-09-27T00:00:01Z" },
      analysis_id: "ana1",
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    const api = new LegalAiApi("https://example.test", async () => ({
      Authorization: "Bearer temporary-secret",
      "X-LegalAI-Demo-User": "krishna",
    }));

    await api.sendMessage("ses1", "My phone was stolen");

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("https://example.test/sessions/ses1/messages");
    expect(options?.headers).toMatchObject({ Authorization: "Bearer temporary-secret" });
    expect(JSON.parse(String(options?.body))).toEqual({ text: "My phone was stolen", start_new_incident: false });
    expect(String(options?.body)).not.toContain("temporary-secret");
  });

  it("surfaces the backend detail on rejected draft transitions", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
      detail: "Legally relevant edits must be reanalyzed first",
    }), { status: 409, headers: { "Content-Type": "application/json" } }));
    const api = new LegalAiApi("https://example.test", async () => ({ Authorization: "Bearer x" }));

    await expect(api.confirmDraft("drf1", 2)).rejects.toMatchObject({
      status: 409,
      message: "Legally relevant edits must be reanalyzed first",
    } satisfies Partial<ApiError>);
  });

  it("explains which fact is missing when edited draft facts no longer match", () => {
    const error = new ApiError(409, {
      message: "Edited facts no longer support a complaint draft",
      analysis: { uncertain_sections: [{ missing_facts: "Was the phone taken without consent?" }] },
    });
    expect(error.message).toContain("Edited facts no longer support a complaint draft");
    expect(error.message).toContain("If you know, clarify: Was the phone taken without consent?");
  });
});
