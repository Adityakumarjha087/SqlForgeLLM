import type { ReactElement } from "react";

// Hand-rolled SQL tokenizer: five token classes are plenty for display, and it
// keeps the bundle free of a highlighting library.
const KEYWORDS = new Set(
  (
    "select from where group by having order limit offset join inner left right " +
    "outer cross on as and or not in exists between like is null distinct union " +
    "except intersect case when then else end asc desc with insert update delete " +
    "cast"
  ).split(" ")
);
const FUNCTIONS = new Set(
  "count sum avg min max abs round length upper lower coalesce substr".split(" ")
);

const TOKEN_RE =
  /('(?:[^']|'')*')|("(?:[^"]|"")*")|(\b\d+(?:\.\d+)?\b)|([A-Za-z_][A-Za-z0-9_]*)|(\S)|(\s+)/g;

export function highlightSql(sql: string): ReactElement[] {
  const parts: ReactElement[] = [];
  let match: RegExpExecArray | null;
  let i = 0;
  while ((match = TOKEN_RE.exec(sql)) !== null) {
    const [text, str, quotedIdent, num, word] = match;
    let cls = "";
    if (str) cls = "tok-str";
    else if (quotedIdent) cls = "tok-ident";
    else if (num) cls = "tok-num";
    else if (word) {
      const lower = word.toLowerCase();
      if (KEYWORDS.has(lower)) cls = "tok-kw";
      else if (FUNCTIONS.has(lower)) cls = "tok-fn";
    }
    parts.push(
      cls ? (
        <span key={i++} className={cls}>
          {text}
        </span>
      ) : (
        <span key={i++}>{text}</span>
      )
    );
  }
  return parts;
}
