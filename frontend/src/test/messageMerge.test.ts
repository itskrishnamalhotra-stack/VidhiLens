import { describe, expect, it } from "vitest";
import { collapseOptimisticDuplicates, mergeMessages } from "../messageMerge";
import type { Message } from "../types";

const user: Message = {
  id: "user-1",
  role: "user",
  text: "Hello ji kya haal hai",
  created_at: "2026-09-28T19:10:00Z",
};

const assistant: Message = {
  id: "assistant-1",
  role: "assistant",
  text: "Haal chal raha hai!",
  created_at: "2026-09-28T19:10:01Z",
};

describe("mergeMessages", () => {
  it("replaces the optimistic message and keeps one canonical user bubble", () => {
    const optimistic: Message = { ...user, id: "local-1" };
    const current = [user, optimistic];

    expect(mergeMessages(current, [user, assistant], [optimistic.id])).toEqual([
      user,
      assistant,
    ]);
  });

  it("is idempotent when the session refresh already returned the full turn", () => {
    expect(mergeMessages([user, assistant], [user, assistant])).toEqual([
      user,
      assistant,
    ]);
  });

  it("hides a stranded optimistic copy after its canonical server message arrives", () => {
    const optimistic: Message = {
      ...user,
      id: "local-stranded",
      created_at: "2026-09-28T19:10:00Z",
    };
    const canonical = {
      ...user,
      created_at: "2026-09-28T19:10:04Z",
    };

    expect(collapseOptimisticDuplicates([optimistic, canonical, assistant])).toEqual([
      canonical,
      assistant,
    ]);
  });

  it("keeps intentionally repeated messages when both have server IDs", () => {
    const repeated = {
      ...user,
      id: "user-2",
      created_at: "2026-09-28T19:10:05Z",
    };

    expect(collapseOptimisticDuplicates([user, repeated, assistant])).toEqual([
      user,
      repeated,
      assistant,
    ]);
  });
});
