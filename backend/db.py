"""Additive, namespaced migrations; short SQLite transactions only."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .errors import APIError, conflict


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class Store:
    def __init__(self, storage: Path):
        self.root = storage
        self.path = storage / "trainer.sqlite3"

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path, timeout=5)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        try:
            yield con
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    def migrate(self):
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "pdfs").mkdir(exist_ok=True)
        with self.connect() as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.executescript("""
                CREATE TABLE IF NOT EXISTS trainer_migrations(version INTEGER PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS trainer_decks(
                    id TEXT PRIMARY KEY, filename TEXT NOT NULL,
                    pages TEXT NOT NULL, pdf_path TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS trainer_sessions(
                    id TEXT PRIMARY KEY, deck_id TEXT NOT NULL REFERENCES trainer_decks(id),
                    state_version INTEGER NOT NULL, state TEXT NOT NULL, model_version TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS trainer_attempts(
                    session_id TEXT NOT NULL REFERENCES trainer_sessions(id), attempt_id TEXT NOT NULL,
                    request TEXT NOT NULL, raw_model TEXT NOT NULL, response TEXT NOT NULL,
                    PRIMARY KEY(session_id, attempt_id));
                CREATE TABLE IF NOT EXISTS trainer_rounds(
                    session_id TEXT NOT NULL REFERENCES trainer_sessions(id), round INTEGER NOT NULL,
                    data TEXT NOT NULL, PRIMARY KEY(session_id, round));
                CREATE TABLE IF NOT EXISTS trainer_retrieval_cache(
                    deck_id TEXT NOT NULL REFERENCES trainer_decks(id), index_version TEXT NOT NULL,
                    data TEXT NOT NULL, PRIMARY KEY(deck_id, index_version));
                CREATE TABLE IF NOT EXISTS trainer_content_indexes(
                    index_version TEXT PRIMARY KEY, data TEXT NOT NULL);
                INSERT OR IGNORE INTO trainer_migrations VALUES (1);
            """)

    def ready(self):
        try:
            with self.connect() as con:
                return con.execute("SELECT version FROM trainer_migrations WHERE version=1").fetchone() is not None
        except sqlite3.Error:
            return False

    def deck(self, deck_id):
        with self.connect() as con:
            row = con.execute("SELECT * FROM trainer_decks WHERE id=?", (deck_id,)).fetchone()
        if not row:
            raise APIError(404, "DECK_NOT_FOUND", "ไม่พบไฟล์สไลด์")
        return {**dict(row), "pages": json.loads(row["pages"])}

    def save_deck(self, deck_id, filename, pages, pdf_path):
        with self.connect() as con:
            con.execute("INSERT INTO trainer_decks VALUES (?,?,?,?)", (deck_id, filename, dump(pages), str(pdf_path)))

    def create_session(self, sid, state, model_version):
        with self.connect() as con:
            con.execute("INSERT INTO trainer_sessions VALUES (?,?,?,?,?)",
                        (sid, state["deck_id"], 0, dump(state), model_version))

    def session(self, sid):
        with self.connect() as con:
            row = con.execute("SELECT state,model_version FROM trainer_sessions WHERE id=?", (sid,)).fetchone()
        if not row:
            raise APIError(404, "SESSION_NOT_FOUND", "ไม่พบรอบซ้อม")
        return json.loads(row["state"]), row["model_version"]

    @staticmethod
    def _replay(con, sid, request):
        row = con.execute("SELECT request,response FROM trainer_attempts WHERE session_id=? AND attempt_id=?",
                          (sid, request["attempt_id"])).fetchone()
        if row:
            if row["request"] != dump(request):
                raise conflict()
            return json.loads(row["response"])

    def replay(self, sid, request):
        with self.connect() as con:
            return self._replay(con, sid, request)

    def commit_answer(self, sid, request, state, response, raw_model, closed_round):
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            replay = self._replay(con, sid, request)
            if replay is not None:
                return replay
            changed = con.execute(
                "UPDATE trainer_sessions SET state_version=?,state=? WHERE id=? AND state_version=?",
                (state["state_version"], dump(state), sid, request["state_version"])).rowcount
            if changed != 1:
                raise conflict()
            con.execute("INSERT INTO trainer_attempts VALUES (?,?,?,?,?)",
                        (sid, request["attempt_id"], dump(request), dump(raw_model), dump(response)))
            if closed_round is not None:
                con.execute("INSERT INTO trainer_rounds VALUES (?,?,?)", (sid, closed_round["round"], dump(closed_round)))
        return response

    def cached(self, deck_id, version):
        with self.connect() as con:
            row = con.execute("SELECT data FROM trainer_retrieval_cache WHERE deck_id=? AND index_version=?",
                              (deck_id, version)).fetchone()
        return json.loads(row["data"]) if row else None

    def cache(self, deck_id, version, data):
        with self.connect() as con:
            con.execute("INSERT OR REPLACE INTO trainer_retrieval_cache VALUES (?,?,?)", (deck_id, version, dump(data)))

    def content_cached(self, version):
        with self.connect() as con:
            row = con.execute("SELECT data FROM trainer_content_indexes WHERE index_version=?", (version,)).fetchone()
        return json.loads(row["data"]) if row else None

    def cache_content(self, version, data):
        with self.connect() as con:
            con.execute("INSERT OR REPLACE INTO trainer_content_indexes VALUES (?,?)", (version, dump(data)))
