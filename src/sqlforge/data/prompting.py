"""The single prompt template used by training, eval and serving.

Keeping this in one place is the guarantee that the model is always asked the
question the same way it was trained on.
"""

import re

SYSTEM_PROMPT = (
    "You are an expert SQLite engineer. Given a database schema and a question, "
    "respond with a single valid SQLite SELECT query that answers the question. "
    "Output only the SQL query, with no explanation and no markdown."
)

USER_TEMPLATE = """Database schema:
{schema}

Question: {question}

SQL:"""


def build_messages(schema: str, question: str) -> list[dict[str, str]]:
    """Chat messages for one example; the assistant target is the SQL alone."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_TEMPLATE.format(schema=schema, question=question)},
    ]


_FENCE_RE = re.compile(r"```(?:sql)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def _first_statement(text: str) -> str:
    return re.sub(r"\s+", " ", text.split(";")[0].strip())


def extract_sql(completion: str) -> str:
    """Pull the SQL out of a model completion.

    Tolerates markdown fences and leading chatter; returns the first statement,
    without a trailing semicolon. Chatter can contain the word "with" (as in
    "I'll help with that: SELECT ..."), so each SELECT/WITH position is a
    candidate and the first one that parses as a query wins; if none parses,
    fall back to the earliest candidate so scoring still sees the attempt.
    """
    from sqlforge.execution import validate_select_only

    text = completion.strip()
    fenced = _FENCE_RE.search(text)
    if fenced:
        text = fenced.group(1).strip()

    candidates = [
        _first_statement(text[match.start() :])
        for match in re.finditer(r"\b(select|with)\b", text, re.IGNORECASE)
    ][:5]
    for candidate in candidates:
        if validate_select_only(candidate) is None:
            return candidate
    return candidates[0] if candidates else _first_statement(text)
