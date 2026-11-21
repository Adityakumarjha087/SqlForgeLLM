"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { parseSchema, type Table } from "@/lib/schema";

type View = "tables" | "ddl";

function matches(table: Table, needle: string): { table: boolean; columns: Set<string> } {
  const columns = new Set(
    table.columns.filter((c) => c.name.toLowerCase().includes(needle)).map((c) => c.name)
  );
  return { table: table.name.toLowerCase().includes(needle), columns };
}

function isMatch(table: Table, needle: string): boolean {
  const hit = matches(table, needle);
  return hit.table || hit.columns.size > 0;
}

/** Tables and columns of the selected database, with the raw prompt DDL one click away. */
export function SchemaBrowser({ schema }: { schema: string }) {
  const tables = useMemo(() => parseSchema(schema), [schema]);
  const [view, setView] = useState<View>("tables");
  const [filter, setFilter] = useState("");
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [jumpTo, setJumpTo] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const tableRefs = useRef(new Map<string, HTMLDetailsElement>());

  // Small schemas start expanded, large ones collapsed.
  useEffect(() => {
    setOpen(new Set(tables.length <= 4 ? tables.map((t) => t.name) : []));
  }, [tables]);

  // Scroll after the target table has rendered open.
  useEffect(() => {
    if (!jumpTo) return;
    const el = tableRefs.current.get(jumpTo);
    if (!el) return;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el.scrollIntoView({ block: "nearest", behavior: reduceMotion ? "auto" : "smooth" });
    setFlash(jumpTo);
    setJumpTo(null);
  }, [jumpTo, open]);

  useEffect(() => {
    if (!flash) return;
    const timer = setTimeout(() => setFlash(null), 1200);
    return () => clearTimeout(timer);
  }, [flash]);

  if (!schema) return <div className="schema-empty">Loading schema…</div>;

  const needle = filter.trim().toLowerCase();
  const visible = tables
    .map((table) => ({ table, hit: needle ? matches(table, needle) : null }))
    .filter(({ hit }) => !hit || hit.table || hit.columns.size > 0);
  const showDdl = view === "ddl" || tables.length === 0;
  const columnCount = tables.reduce((n, t) => n + t.columns.length, 0);

  const updateFilter = (value: string) => {
    setFilter(value);
    const n = value.trim().toLowerCase();
    if (n) setOpen(new Set(tables.filter((t) => isMatch(t, n)).map((t) => t.name)));
  };

  const toggle = (name: string, isOpen: boolean) =>
    setOpen((prev) => {
      if (prev.has(name) === isOpen) return prev;
      const next = new Set(prev);
      if (isOpen) next.add(name);
      else next.delete(name);
      return next;
    });

  // Foreign-key targets are matched case-insensitively (Spider mixes cases).
  const reveal = (target: string) => {
    const table = tables.find((t) => t.name.toLowerCase() === target.toLowerCase());
    if (!table) return;
    if (needle && !isMatch(table, needle)) setFilter("");
    toggle(table.name, true);
    setJumpTo(table.name);
  };

  return (
    <div className="schema-browser">
      <div className="schema-toolbar">
        <span className="schema-count">
          {tables.length
            ? `${tables.length} tables · ${columnCount} columns`
            : "Raw schema"}
        </span>
        {tables.length > 0 && (
          <div className="segmented" role="group" aria-label="Schema view">
            {(["tables", "ddl"] as const).map((v) => (
              <button key={v} type="button" aria-pressed={view === v} onClick={() => setView(v)}>
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
            onChange={(e) => updateFilter(e.target.value)}
          />
          <div className="schema-actions">
            <button
              type="button"
              className="link-button"
              onClick={() => setOpen(new Set(visible.map(({ table }) => table.name)))}
            >
              Expand all
            </button>
            <button type="button" className="link-button" onClick={() => setOpen(new Set())}>
              Collapse all
            </button>
          </div>
          <div className="schema-tables">
            {visible.length === 0 && <p className="hint">No table or column matches “{filter}”.</p>}
            {visible.map(({ table, hit }) => (
              <details
                key={table.name}
                ref={(el) => {
                  if (el) tableRefs.current.set(table.name, el);
                  else tableRefs.current.delete(table.name);
                }}
                className={flash === table.name ? "schema-table flash" : "schema-table"}
                open={open.has(table.name)}
                onToggle={(e) => toggle(table.name, e.currentTarget.open)}
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
                        <button
                          type="button"
                          className="badge fk"
                          title={`Foreign key → ${col.references.table}.${col.references.column} (click to show)`}
                          onClick={() => col.references && reveal(col.references.table)}
                        >
                          → {col.references.table}
                          {col.references.column && `.${col.references.column}`}
                        </button>
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
