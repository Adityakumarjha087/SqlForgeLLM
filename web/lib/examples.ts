import type { Column, Table } from "@/lib/schema";

// Starter questions built from the selected database's own tables, so every
// suggestion is answerable there: a count, a projection, an aggregate and a join.

const NUMERIC = /int|real|float|double|numeric|decimal|number/i;

function words(identifier: string): string {
  return identifier
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/_+/g, " ")
    .trim()
    .toLowerCase();
}

function isKeyLike(column: Column): boolean {
  const name = column.name;
  return (
    column.primaryKey ||
    column.references !== null ||
    /(^|_)id$/i.test(name) || // player_id, ID
    /[a-z]Id$/.test(name) || // MakeId
    /^.?id$/i.test(name) // oid, aid
  );
}

// Numeric but not something you'd average: years, dates, codes, sequence numbers.
const NOT_A_MEASURE = /year|date|code|zip|phone|(^|_)num(ber)?$|_no$/i;

export function exampleQuestions(tables: Table[], limit = 4): string[] {
  if (tables.length === 0) return [];
  const out: string[] = [];
  const first = tables[0];
  out.push(`How many rows are in the ${words(first.name)} table?`);

  for (const table of tables) {
    const name = table.columns.find((c) => /name|title/i.test(c.name) && !isKeyLike(c));
    if (name) {
      out.push(`List every ${words(name.name)} in the ${words(table.name)} table.`);
      break;
    }
  }
  for (const table of tables) {
    const measure = table.columns.find(
      (c) => NUMERIC.test(c.type) && !isKeyLike(c) && !NOT_A_MEASURE.test(c.name)
    );
    if (measure) {
      out.push(`What is the average ${words(measure.name)} in the ${words(table.name)} table?`);
      break;
    }
  }
  for (const table of tables) {
    const link = table.columns.find((c) => c.references && c.references.table !== table.name);
    if (link?.references) {
      out.push(`Show the ${words(link.references.table)} for each row of ${words(table.name)}.`);
      break;
    }
  }
  return [...new Set(out)].slice(0, limit);
}
