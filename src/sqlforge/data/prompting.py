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


def extract_sql(completion: str) -> str:
    """Pull the SQL out of a model completion.

    Tolerates markdown fences and leading chatter; returns the first statement,
    without a trailing semicolon.
    """
    text = completion.strip()
    fenced = _FENCE_RE.search(text)
    if fenced:
        text = fenced.group(1).strip()
    # Drop anything before the first SELECT/WITH (case-insensitive).
    match = re.search(r"\b(select|with)\b", text, re.IGNORECASE)
    if match:
        text = text[match.start() :]
    # Keep only the first statement.
    text = text.split(";")[0].strip()
    return re.sub(r"\s+", " ", text)
