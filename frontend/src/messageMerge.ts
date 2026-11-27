import type { Message } from "./types";

/**
 * Merge canonical server messages into the visible conversation without
 * duplicating a message that may already have arrived through a session load.
 */
export function mergeMessages(
  current: Message[],
  incoming: Message[],
  removeIds: Iterable<string> = [],
) {
  const removed = new Set(removeIds);
  const byId = new Map<string, Message>();

  for (const message of current) {
    if (!removed.has(message.id)) byId.set(message.id, message);
  }
  for (const message of incoming) byId.set(message.id, message);

  return Array.from(byId.values());
}

/**
 * A slow session refresh can briefly leave the optimistic bubble beside the
 * canonical server copy. Hide only that local copy. Repeated messages that
 * were both saved by the server remain visible as separate turns.
 */
export function collapseOptimisticDuplicates(messages: Message[]) {
  const canonicalUsers = messages.filter(
    (message) => message.role === "user" && !message.id.startsWith("local-"),
  );

  return messages.filter((message) => {
    if (message.role !== "user" || !message.id.startsWith("local-")) return true;
    const localTime = Date.parse(message.created_at);
    return !canonicalUsers.some((canonical) => {
      const serverTime = Date.parse(canonical.created_at);
      return canonical.text.trim() === message.text.trim()
        && Number.isFinite(localTime)
        && Number.isFinite(serverTime)
        && serverTime >= localTime
        && serverTime - localTime <= 60_000;
    });
  });
}
