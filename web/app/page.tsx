"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { SchemaBrowser } from "@/components/schema-browser";
import { ThemeToggle } from "@/components/theme-toggle";
import { downloadCsv } from "@/lib/csv";
import { exampleQuestions } from "@/lib/examples";
import { highlightSql } from "@/lib/highlight";
import { addToHistory, loadHistory, saveHistory, type HistoryEntry } from "@/lib/history";
import { parseSchema } from "@/lib/schema";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
// Fallback until /health reports the server's max_question_chars (configs/serve.yaml).
// The API enforces the cap; the UI only warns early.
const DEFAULT_MAX_QUESTION_CHARS = 500;

interface QueryResult {
  sql: string;
  latency_ms: number;
  tokens_per_second: number | null;
  columns: string[];
  rows: unknown[][];
  truncated: boolean;
  execution_error: string | null;
}

// The database a result came from: the picker may have moved on since.
type ShownResult = QueryResult & { dbId: string };

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

// Past this many characters a cell is likely clipped by the CSS width cap,
// so the full value goes in a tooltip.
const LONG_CELL = 40;

function Cell({ value }: { value: unknown }) {
  if (value === null) return <td className="null">NULL</td>;
  if (typeof value === "number") return <td className="num">{value}</td>;
  const text = String(value);
  return (
    <td title={text.length > LONG_CELL ? text : undefined}>
      <span className="cell-text">{text}</span>
    </td>
  );
}

export default function Home() {
  const [status, setStatus] = useState<ApiStatus>({ state: "checking" });
  const [databases, setDatabases] = useState<string[]>([]);
  const [dbHint, setDbHint] = useState("");
  const [dbId, setDbId] = useState("");
  const [schema, setSchema] = useState("");
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<ShownResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [shortcut, setShortcut] = useState("Ctrl ↵");
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  // The mock backend returns a canned query, so its tok/s figure says nothing about a real model.
  const showThroughput = !(status.state === "online" && status.backend === "mock");
  const [maxQuestionChars, setMaxQuestionChars] = useState(DEFAULT_MAX_QUESTION_CHARS);

  useEffect(() => {
    if (/Mac|iPhone|iPad/.test(navigator.userAgent)) setShortcut("⌘ ↵");
    setHistory(loadHistory());
    fetch(`${API}/health`)
      .then((r) => r.json())
      .then((d) => {
        setStatus({ state: "online", backend: d.backend });
        if (Number.isInteger(d.max_question_chars) && d.max_question_chars > 0) {
          setMaxQuestionChars(d.max_question_chars);
        }
      })
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
    // Ignore a slow response for a database the picker has already moved off.
    let stale = false;
    fetch(`${API}/schema/${dbId}`)
      .then(async (r) => {
        if (!r.ok) {
          const body = await r.json().catch(() => null);
          throw new Error(body?.detail ?? `API error ${r.status}`);
        }
        return r.json();
      })
      .then((d) => {
        if (!stale) setSchema(d.schema);
      })
      .catch((e) => {
        if (!stale) setSchema(`(failed to load schema: ${e instanceof Error ? e.message : e})`);
      });
    return () => {
      stale = true;
    };
  }, [dbId]);

  const questionRef = useRef<HTMLTextAreaElement>(null);
  const announcement = loading
    ? "Generating SQL…"
    : copied
      ? "SQL copied to clipboard."
      : result
        ? result.execution_error
          ? "SQL generated, but running it failed."
          : `SQL generated. The query returned ${result.rows.length} ${result.rows.length === 1 ? "row" : "rows"}.`
        : "";
  const examples = useMemo(() => exampleQuestions(parseSchema(schema)), [schema]);

  // Code points, like Python's len() on the server (emoji count once, not twice).
  const questionLength = [...question.trim()].length;
  const tooLong = questionLength > maxQuestionChars;

  const ask = useCallback(async () => {
    if (!question.trim() || tooLong || !dbId || loading) return;
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
      setResult({ ...((await response.json()) as QueryResult), dbId });
      setHistory((h) => addToHistory(h, { dbId, question: question.trim() }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [question, tooLong, dbId, loading]);

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

        <main className="workspace" aria-busy={loading}>
          {/* Screen readers hear progress and outcome without moving focus. */}
          <p className="sr-only" role="status" aria-live="polite">
            {announcement}
          </p>
          <section className="panel">
            <label className="panel-title" htmlFor="question">
              Question
            </label>
            <textarea
              ref={questionRef}
              id="question"
              value={question}
              placeholder="e.g. How many singers are there, by country?"
              aria-invalid={tooLong}
              aria-describedby="question-count"
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) ask();
              }}
            />
            {examples.length > 0 && (
              <div className="examples">
                <span className="examples-label">Try</span>
                {examples.map((example) => (
                  <button
                    key={example}
                    type="button"
                    className="example-chip"
                    onClick={() => {
                      setQuestion(example);
                      questionRef.current?.focus();
                    }}
                  >
                    {example}
                  </button>
                ))}
              </div>
            )}
            <div className="ask-row">
              <span className="hint kbd-hint">
                <kbd>{shortcut}</kbd> to run
              </span>
              <span
                id="question-count"
                className={`char-count${tooLong ? " over" : questionLength > maxQuestionChars * 0.9 ? " near" : ""}`}
              >
                {questionLength}/{maxQuestionChars}
                {tooLong && " · too long"}
              </span>
              <button
                className="btn-primary"
                onClick={ask}
                disabled={loading || !question.trim() || tooLong || !dbId}
              >
                {loading ? "Generating…" : "Generate & run"}
              </button>
            </div>
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
            {history.length > 0 && (
              <div className="history">
                <div className="history-head">
                  <span className="examples-label">Recent</span>
                  <button
                    type="button"
                    className="link-button"
                    onClick={() => {
                      setHistory([]);
                      saveHistory([]);
                    }}
                  >
                    Clear
                  </button>
                </div>
                <ul>
                  {history.map((entry) => (
                    <li key={`${entry.dbId}\u0000${entry.question}`}>
                      <button
                        type="button"
                        title={`Restore this question on ${entry.dbId}`}
                        onClick={() => {
                          if (databases.includes(entry.dbId)) setDbId(entry.dbId);
                          setQuestion(entry.question);
                          questionRef.current?.focus();
                        }}
                      >
                        <span className="history-db">{entry.dbId}</span>
                        <span className="history-question">{entry.question}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>

          {loading && (
            <section className="panel" aria-busy="true" aria-label="Generating SQL">
              <div className="panel-head">
                <h2 className="panel-title">Generated SQL</h2>
              </div>
              <div className="skeleton" aria-hidden />
              <div className="skeleton short" aria-hidden />
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
                    {showThroughput && result.tokens_per_second ? (
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
                      {result.rows.length > 0 && (
                        <button
                          type="button"
                          className="btn-ghost"
                          title="Download these rows as CSV"
                          onClick={() =>
                            downloadCsv(`${result.dbId}-result.csv`, result.columns, result.rows)
                          }
                        >
                          CSV
                        </button>
                      )}
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
                      <caption className="sr-only">
                        Query result: {result.rows.length} {result.rows.length === 1 ? "row" : "rows"},{" "}
                        {result.columns.length} {result.columns.length === 1 ? "column" : "columns"}
                      </caption>
                      <thead>
                        <tr>
                          {result.columns.map((c, i) => (
                            <th key={i} scope="col">
                              {c}
                            </th>
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
