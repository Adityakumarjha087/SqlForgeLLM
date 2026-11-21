// Parse the schema text the API serves (the same text the model sees in its
// prompt) into tables and columns for the schema browser. Two input shapes, both
// one table per line:
//   CREATE TABLE "t" ( "a" int, "b" text, PRIMARY KEY ("a"), FOREIGN KEY ("b") REFERENCES "u"("c") );
//   t(a int, b text)            <- compact fallback for very large schemas
// Anything unrecognised is skipped; callers fall back to the raw text when no
// table parses.

export interface ForeignKey {
  table: string;
  column: string;
}

export interface Column {
  name: string;
  type: string;
  primaryKey: boolean;
  references: ForeignKey | null;
}

export interface Table {
  name: string;
  columns: Column[];
}

const IDENT = String.raw`(?:"(?:[^"]|"")*"|'(?:[^']|'')*'|\x60[^\x60]*\x60|\[[^\]]*\]|[A-Za-z_][\w$]*)`;
const CREATE_RE = new RegExp(String.raw`^\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(${IDENT})\s*\(`, "i");
const COMPACT_RE = new RegExp(String.raw`^\s*(${IDENT})\s*\(`);
const CONSTRAINT_RE = /^(?:CONSTRAINT\s+\S+\s+)?(PRIMARY\s+KEY|FOREIGN\s+KEY|UNIQUE|CHECK)\b/i;
const REFERENCES_RE = new RegExp(String.raw`REFERENCES\s+(${IDENT})\s*(?:\(\s*(${IDENT})\s*\))?`, "i");

function unquote(name: string): string {
  const s = name.trim();
  const q = s[0];
  if (s.length > 1 && (q === '"' || q === "'" || q === "`") && s.endsWith(q)) {
    return s.slice(1, -1).replaceAll(q + q, q);
  }
  if (s.startsWith("[") && s.endsWith("]")) return s.slice(1, -1);
  return s;
}

function identList(text: string): string[] {
  return splitTopLevel(text).map(unquote);
}

/** Split on commas that are not inside parentheses or quotes. */
function splitTopLevel(body: string): string[] {
  const parts: string[] = [];
  let depth = 0;
  let quote: string | null = null;
  let current = "";
  for (const ch of body) {
    if (quote) {
      if (ch === quote) quote = null;
    } else if (ch === '"' || ch === "'" || ch === "`") {
      quote = ch;
    } else if (ch === "(") {
      depth++;
    } else if (ch === ")") {
      depth--;
    } else if (ch === "," && depth === 0) {
      parts.push(current.trim());
      current = "";
      continue;
    }
    current += ch;
  }
  if (current.trim()) parts.push(current.trim());
  return parts;
}

/** The text between the opening paren at `start` and its matching close. */
function parenBody(line: string, start: number): string | null {
  let depth = 0;
  let quote: string | null = null;
  for (let i = start; i < line.length; i++) {
    const ch = line[i];
    if (quote) {
      if (ch === quote) quote = null;
    } else if (ch === '"' || ch === "'" || ch === "`") {
      quote = ch;
    } else if (ch === "(") {
      depth++;
    } else if (ch === ")" && --depth === 0) {
      return line.slice(start + 1, i);
    }
  }
  return null;
}

function parseColumn(def: string): Column | null {
  const match = def.match(new RegExp(String.raw`^(${IDENT})\s*(.*)$`, "s"));
  if (!match) return null;
  const rest = match[2];
  const type = rest.match(/^([A-Za-z]+(?:\s*\([^)]*\))?)/)?.[1] ?? "";
  const ref = rest.match(REFERENCES_RE);
  return {
    name: unquote(match[1]),
    type: /^(PRIMARY|NOT|NULL|UNIQUE|DEFAULT|REFERENCES|CHECK)$/i.test(type) ? "" : type,
    primaryKey: /\bPRIMARY\s+KEY\b/i.test(rest),
    references: ref ? { table: unquote(ref[1]), column: ref[2] ? unquote(ref[2]) : "" } : null,
  };
}

function applyConstraint(def: string, columns: Column[]): void {
  const byName = new Map(columns.map((c) => [c.name.toLowerCase(), c]));
  const open = def.indexOf("(");
  const keys = open >= 0 ? parenBody(def, open) : null;
  if (!keys) return;
  const names = identList(keys);
  if (/^(?:CONSTRAINT\s+\S+\s+)?PRIMARY\s+KEY/i.test(def)) {
    for (const n of names) {
      const col = byName.get(n.toLowerCase());
      if (col) col.primaryKey = true;
    }
  } else if (/^(?:CONSTRAINT\s+\S+\s+)?FOREIGN\s+KEY/i.test(def)) {
    const ref = def.match(REFERENCES_RE);
    const col = byName.get(names[0]?.toLowerCase() ?? "");
    if (ref && col) col.references = { table: unquote(ref[1]), column: ref[2] ? unquote(ref[2]) : "" };
  }
}

function parseLine(line: string): Table | null {
  const head = line.match(CREATE_RE) ?? line.match(COMPACT_RE);
  if (!head) return null;
  const body = parenBody(line, head[0].length - 1);
  if (body === null) return null;
  const columns: Column[] = [];
  const constraints: string[] = [];
  for (const def of splitTopLevel(body)) {
    if (CONSTRAINT_RE.test(def)) constraints.push(def);
    else {
      const col = parseColumn(def);
      if (col) columns.push(col);
    }
  }
  for (const def of constraints) applyConstraint(def, columns);
  return columns.length ? { name: unquote(head[1]), columns } : null;
}

export function parseSchema(text: string): Table[] {
  return text
    .split("\n")
    .map(parseLine)
    .filter((t): t is Table => t !== null);
}
