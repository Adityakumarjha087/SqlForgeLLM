// The last database the user picked, kept per browser in localStorage so a
// reload does not jump back to the first entry. Storage can be blocked or
// cleared at any time, so every access is guarded.

const KEY = "sqlforge-database";

export function loadDatabase(): string {
  try {
    return localStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
}

export function saveDatabase(dbId: string): void {
  try {
    localStorage.setItem(KEY, dbId);
  } catch {
    // Storage unavailable: the choice lasts for this page view only.
  }
}

/** The remembered database if the API still lists it, otherwise the first one. */
export function initialDatabase(databases: string[], remembered: string): string {
  return databases.includes(remembered) ? remembered : (databases[0] ?? "");
}
