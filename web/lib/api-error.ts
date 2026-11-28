// FastAPI answers with {"detail": "..."} for errors we raise ourselves, but with
// {"detail": [{"msg": "...", ...}]} when request validation fails. Showing the
// raw array would print "[object Object]", so both shapes become plain text.

export function apiErrorMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((d) => (typeof (d as { msg?: unknown })?.msg === "string" ? (d as { msg: string }).msg : ""))
      .filter(Boolean)
      // Pydantic prefixes custom validator errors with "Value error, ".
      .map((m) => m.replace(/^Value error, /, ""));
    if (messages.length) return messages.join("; ");
  }
  return `API error ${status}`;
}
