"use client";

import { useCallback, useEffect, useState } from "react";
import { SchemaBrowser } from "@/components/schema-browser";
import { ThemeToggle } from "@/components/theme-toggle";
import { highlightSql } from "@/lib/highlight";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface QueryResult {
  sql: string;
  latency_ms: number;
  tokens_per_second: number | null;
  columns: string[];
  rows: unknown[][];
  truncated: boolean;
  execution_error: string | null;
}

type ApiStatus = { state: "checking" } | { state: "online"; backend: string } | { state: "offline" };

function StatusPill({ status }: { status: ApiStatus }) {
  const label =
    status.state === "online"
      ? `API online · ${status.backend} backend`
      : status.state === "offline"
        ? "API unreachable"
        : "Connecting…";
  return (
    <span className={`status-pill ${status.state}`} title={API}>
      <span className="dot" aria-hidden />
      {label}
    </span>
  );
}

function Cell({ value }: { value: unknown }) {
  if (value === null) return <td className="null">NULL</td>;
  if (typeof value === "number") return <td className="num">{value}</td>;
  return <td>{String(value)}</td>;
}

export default function Home() {
  const [status, setStatus] = useState<ApiStatus>({ state: "checking" });
  const [databases, setDatabases] = useState<string[]>([]);
  const [dbHint, setDbHint] = useState("");
  const [dbId, setDbId] = useState("");
  const [schema, setSchema] = useState("");
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<QueryResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [shortcut, setShortcut] = useState("Ctrl ↵");

  useEffect(() => {
    if (/Mac|iPhone|iPad/.test(navigator.userAgent)) setShortcut("⌘ ↵");
    fetch(`${API}/health`)
      .then((r) => r.json())
      .then((d) => setStatus({ state: "online", backend: d.backend }))
      .catch(() => setStatus({ state: "offline" }));
    fetch(`${API}/databases`)
      .then((r) => r.json())
      .then((d) => {
        setDatabases(d.databases);
        setDbHint(d.hint ?? "");
        if (d.databases.length) setDbId(d.databases[0]);
      })
      .catch(() => setError(`Could not reach the API at ${API}`));
  }, []);

  useEffect(() => {
    if (!dbId) return;
    setSchema("");
    fetch(`${API}/schema/${dbId}`)
      .then((r) => r.json())
      .then((d) => setSchema(d.schema))
      .catch(() => setSchema("(failed to load schema)"));
  }, [dbId]);

  const ask = useCallback(async () => {
    if (!question.trim() || !dbId || loading) return;
    setLoading(true);
    setError("");
    setResult(null);
    setCopied(false);
    try {
      const response = await fetch(`${API}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question.trim(), db_id: dbId }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? `API error ${response.status}`);
      }
      setResult(await response.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [question, dbId, loading]);

  const copySql = useCallback(async () => {
    if (!result) return;
    try {
      await navigator.clipboard.writeText(result.sql);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard needs a secure context; the SQL stays selectable by hand.
    }
  }, [result]);

  return (
    <div className="container">
      <header className="site-header">
        <div className="brand">
          <span className="logo" aria-hidden>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
              <ellipse cx="12" cy="5.5" rx="7.5" ry="3" />
              <path d="M4.5 5.5v6c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3v-6" />
              <path d="M4.5 11.5v6c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3v-6" />
            </svg>
          </span>
          <div>
            <h1>SQLForge</h1>
            <p>Ask in English — a fine-tuned 1.5B model writes the SQL, a read-only sandbox runs it.</p>
          </div>
        </div>
        <div className="header-actions">
          <StatusPill status={status} />
          <ThemeToggle />
        </div>
      </header>

      <div className="layout">
        <aside className="panel sidebar">
          <label className="panel-title" htmlFor="db-select">
            Database
          </label>
          <select id="db-select" value={dbId} onChange={(e) => setDbId(e.target.value)}>
            {databases.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
          {dbHint && <p className="hint">{dbHint}</p>}
          <h2 className="panel-title spaced">Schema</h2>
          {dbId && <SchemaBrowser schema={schema} />}
        </aside>

        <main className="workspace">
          <section className="panel">
            <label className="panel-title" htmlFor="question">
              Question
            </label>
            <textarea
              id="question"
              value={question}
              placeholder="e.g. How many singers are there, by country?"
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) ask();
              }}
            />
            <div className="ask-row">
              <span className="hint">
                <kbd>{shortcut}</kbd> to run
              </span>
              <button className="btn-primary" onClick={ask} disabled={loading || !question.trim() || !dbId}>
                {loading ? "Generating…" : "Generate & run"}
              </button>
            </div>
            {error && <p className="error">{error}</p>}
          </section>

          {loading && (
            <section className="panel" aria-busy>
              <div className="panel-head">
                <h2 className="panel-title">Generated SQL</h2>
              </div>
              <div className="skeleton" />
              <div className="skeleton short" />
            </section>
          )}

          {!loading && !result && !error && (
            <section className="panel empty-state">
              <p>
                Pick a database, browse its tables, and ask a question. The generated query and its
                rows show up here.
              </p>
            </section>
          )}

          {result && (
            <>
              <section className="panel">
                <div className="panel-head">
                  <h2 className="panel-title">Generated SQL</h2>
                  <div className="chips">
                    <span className="chip">{result.latency_ms.toFixed(0)} ms</span>
                    {result.tokens_per_second ? (
                      <span className="chip">{result.tokens_per_second.toFixed(1)} tok/s</span>
                    ) : null}
                    <button className="btn-ghost" onClick={copySql}>
                      {copied ? "Copied" : "Copy"}
                    </button>
                  </div>
                </div>
                <pre className="sql-block">{highlightSql(result.sql)}</pre>
              </section>

              <section className="panel">
                <div className="panel-head">
                  <h2 className="panel-title">Result</h2>
                  {!result.execution_error && (
                    <div className="chips">
                      <span className="chip">
                        {result.rows.length} {result.rows.length === 1 ? "row" : "rows"}
                      </span>
                      {result.truncated && <span className="chip warn">truncated</span>}
                    </div>
                  )}
                </div>
                {result.execution_error ? (
                  <p className="error">{result.execution_error}</p>
                ) : result.rows.length === 0 ? (
                  <p className="hint">Query ran fine but returned no rows.</p>
                ) : (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          {result.columns.map((c, i) => (
                            <th key={i}>{c}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {result.rows.map((row, i) => (
                          <tr key={i}>
                            {row.map((cell, j) => (
                              <Cell key={j} value={cell} />
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                {result.truncated && (
                  <p className="hint">Showing the first {result.rows.length} rows (server row limit).</p>
                )}
              </section>
            </>
          )}
        </main>
      </div>
    </div>
  );
}
