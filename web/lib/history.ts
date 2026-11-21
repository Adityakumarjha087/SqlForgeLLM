// Recently asked questions, kept per browser in localStorage. Storage can be
// blocked or cleared at any time, so every access is guarded and the app works
// the same without it.

export interface HistoryEntry {
  dbId: string;
  question: string;
}

const KEY = "sqlforge-history";
export const HISTORY_LIMIT = 6;

export function loadHistory(): HistoryEntry[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter(
        (e): e is HistoryEntry =>
          typeof e?.dbId === "string" && typeof e?.question === "string" && e.question.length > 0
      )
      .slice(0, HISTORY_LIMIT);
  } catch {
    return [];
  }
}

/** Newest first; asking the same question on the same database again moves it to the top. */
export function addToHistory(history: HistoryEntry[], entry: HistoryEntry): HistoryEntry[] {
  const next = [
    entry,
    ...history.filter((e) => !(e.dbId === entry.dbId && e.question === entry.question)),
  ].slice(0, HISTORY_LIMIT);
  saveHistory(next);
  return next;
}

export function saveHistory(history: HistoryEntry[]): void {
  try {
    if (history.length) localStorage.setItem(KEY, JSON.stringify(history));
    else localStorage.removeItem(KEY);
  } catch {
    // Storage unavailable: history lasts for this page view only.
  }
}
