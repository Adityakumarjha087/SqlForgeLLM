import sqlite3

import pytest


@pytest.fixture
def tiny_db(tmp_path):
    """A small concerts database mirroring Spider's layout: <root>/<db_id>/<db_id>.sqlite."""
    db_dir = tmp_path / "concert_db"
    db_dir.mkdir()
    path = db_dir / "concert_db.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE stadium (
            stadium_id INTEGER PRIMARY KEY,
            name TEXT,
            capacity INTEGER
        );
        CREATE TABLE concert (
            concert_id INTEGER PRIMARY KEY,
            concert_name TEXT,
            stadium_id INTEGER,
            year INTEGER,
            FOREIGN KEY (stadium_id) REFERENCES stadium(stadium_id)
        );
        INSERT INTO stadium VALUES (1, 'Big Arena', 50000), (2, 'Small Field', NULL);
        INSERT INTO concert VALUES
            (1, 'Rock Night', 1, 2020),
            (2, 'Jazz Eve', 1, 2021),
            (3, 'Folk Day', 2, 2021);
        """
    )
    conn.commit()
    conn.close()
    return path
