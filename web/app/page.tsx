"use client";

import { useCallback, useEffect, useState } from "react";
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

export default function Home() {
  const [databases, setDatabases] = useState<string[]>([]);
  const [dbId, setDbId] = useState("");
  const [schema, setSchema] = useState("");
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<QueryResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${API}/databases`)
      .then((r) => r.json())
      .then((d) => {
        setDatabases(d.databases);
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

  return (
    <div className="container">
      <header>
        <h1>SQLForge</h1>
        <p>Ask a question in English — a fine-tuned 1.5B model writes and runs the SQL.</p>
      </header>

      <div className="layout">
        <aside className="panel">
          <h2>Database</h2>
          <select value={dbId} onChange={(e) => setDbId(e.target.value)}>
            {databases.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
          <h2 style={{ marginTop: 16 }}>Schema</h2>
          <div className="schema">{schema || "…"}</div>
        </aside>

        <main>
          <div className="panel">
            <h2>Question</h2>
            <textarea
              value={question}
              placeholder="e.g. How many singers are there, by country?"
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) ask();
              }}
            />
            <button onClick={ask} disabled={loading || !question.trim()}>
              {loading ? "Generating…" : "Ask"}
            </button>
            {error && <p className="error">{error}</p>}
          </div>

          {result && (
            <>
              <div className="panel" style={{ marginTop: 16 }}>
                <h2>Generated SQL</h2>
                <div className="sql-block">{highlightSql(result.sql)}</div>
                <p className="meta">
                  {result.latency_ms.toFixed(0)} ms
                  {result.tokens_per_second
                    ? ` · ${result.tokens_per_second.toFixed(1)} tok/s`
                    : ""}
                </p>
              </div>

              <div className="panel" style={{ marginTop: 16 }}>
                <h2>Result</h2>
                {result.execution_error ? (
                  <p className="error">{result.execution_error}</p>
                ) : result.rows.length === 0 ? (
                  <p className="hint">Query ran fine but returned no rows.</p>
                ) : (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          {result.columns.map((c) => (
                            <th key={c}>{c}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {result.rows.map((row, i) => (
                          <tr key={i}>
                            {row.map((cell, j) => (
                              <td key={j}>{cell === null ? "NULL" : String(cell)}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {result.truncated && (
                      <p className="hint">Rows truncated by the server’s row limit.</p>
                    )}
                  </div>
                )}
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  );
}
