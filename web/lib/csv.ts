// RFC 4180 CSV for a query result: fields with commas, quotes or newlines are
// quoted (inner quotes doubled), NULL becomes an empty field, lines end in CRLF.

// Text starting with one of these is run as a formula by spreadsheet apps
// (CSV injection), so it gets a leading apostrophe. Only strings: a negative
// number stays a number.
const FORMULA_START = /^[=+\-@\t\r]/;

function field(value: unknown): string {
  if (value === null || value === undefined) return "";
  let text = String(value);
  if (typeof value === "string" && FORMULA_START.test(text)) text = `'${text}`;
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function toCsv(columns: string[], rows: unknown[][]): string {
  return [columns, ...rows].map((row) => row.map(field).join(",")).join("\r\n") + "\r\n";
}

export function downloadCsv(filename: string, columns: string[], rows: unknown[][]): void {
  // The BOM makes Excel read the file as UTF-8 instead of the system code page.
  const blob = new Blob(["﻿", toCsv(columns, rows)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
