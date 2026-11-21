"use client";

import { useMemo, useState } from "react";
import { parseSchema, type Table } from "@/lib/schema";

type View = "tables" | "ddl";

function matches(table: Table, needle: string): { table: boolean; columns: Set<string> } {
  const columns = new Set(
    table.columns.filter((c) => c.name.toLowerCase().includes(needle)).map((c) => c.name)
  );
  return { table: table.name.toLowerCase().includes(needle), columns };
}

/** Tables and columns of the selected database, with the raw prompt DDL one click away. */
export function SchemaBrowser({ schema }: { schema: string }) {
  const tables = useMemo(() => parseSchema(schema), [schema]);
  const [view, setView] = useState<View>("tables");
  const [filter, setFilter] = useState("");

  if (!schema) return <div className="schema-empty">Loading schema…</div>;

  const needle = filter.trim().toLowerCase();
  const visible = tables
    .map((table) => ({ table, hit: needle ? matches(table, needle) : null }))
    .filter(({ hit }) => !hit || hit.table || hit.columns.size > 0);
  const showDdl = view === "ddl" || tables.length === 0;
  const columnCount = tables.reduce((n, t) => n + t.columns.length, 0);

  return (
    <div className="schema-browser">
      <div className="schema-toolbar">
        <span className="schema-count">
          {tables.length
            ? `${tables.length} tables · ${columnCount} columns`
            : "Raw schema"}
        </span>
        {tables.length > 0 && (
          <div className="segmented" role="tablist" aria-label="Schema view">
            {(["tables", "ddl"] as const).map((v) => (
              <button
                key={v}
                role="tab"
                aria-selected={view === v}
                className={view === v ? "active" : ""}
                onClick={() => setView(v)}
              >
                {v === "tables" ? "Tables" : "DDL"}
              </button>
            ))}
          </div>
        )}
      </div>

      {showDdl ? (
        <pre className="schema-ddl" title="Exactly what the model sees in its prompt">
          {schema}
        </pre>
      ) : (
        <>
          <input
            type="search"
            className="schema-filter"
            placeholder="Filter tables or columns"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          <div className="schema-tables">
            {visible.length === 0 && <p className="hint">No table or column matches “{filter}”.</p>}
            {visible.map(({ table, hit }) => (
              <details
                key={table.name}
                className="schema-table"
                open={needle ? true : tables.length <= 4}
              >
                <summary>
                  <span className="table-name">{table.name}</span>
                  <span className="table-meta">
                    {hit && !hit.table
                      ? `${hit.columns.size} of ${table.columns.length}`
                      : table.columns.length}
                  </span>
                </summary>
                <ul>
                  {/* A column-only match lists just the matching columns. */}
                  {(hit && !hit.table
                    ? table.columns.filter((c) => hit.columns.has(c.name))
                    : table.columns
                  ).map((col) => (
                    <li
                      key={col.name}
                      className={hit?.columns.has(col.name) ? "col match" : "col"}
                    >
                      <span className="col-name">{col.name}</span>
                      {col.primaryKey && <span className="badge pk">PK</span>}
                      {col.references && (
                        <span
                          className="badge fk"
                          title={`Foreign key → ${col.references.table}.${col.references.column}`}
                        >
                          → {col.references.table}
                          {col.references.column && `.${col.references.column}`}
                        </span>
                      )}
                      <span className="col-type">{col.type.toLowerCase()}</span>
                    </li>
                  ))}
                </ul>
              </details>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
