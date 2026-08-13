import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import psycopg
    from psycopg.types.json import Jsonb
except ImportError:  # pragma: no cover - local JSON mode does not require psycopg
    psycopg = None
    Jsonb = None


class PersistentStore:
    """Thread-safe JSON key/value storage with an optional PostgreSQL backend.

    Production deployments should provide ``DATABASE_URL``. PostgreSQL keeps
    proposals available across Render restarts, deploys, and instance changes.
    Local development falls back to atomic JSON-file writes in ``NTS_DATA_DIR``.
    """

    def __init__(
        self,
        data_dir: Optional[str] = None,
        database_url: Optional[str] = None,
    ):
        self.database_url = os.getenv("DATABASE_URL") if database_url is None else database_url
        self.data_dir = Path(data_dir or os.getenv("NTS_DATA_DIR", "./data"))
        self.lock = threading.RLock()
        self._schema_ready = False

        if self.database_url:
            if psycopg is None:
                raise RuntimeError(
                    "DATABASE_URL is configured but psycopg is not installed"
                )
        else:
            self.data_dir.mkdir(parents=True, exist_ok=True)

    @property
    def backend(self) -> str:
        return "postgresql" if self.database_url else "json"

    def _connect(self, *, autocommit: bool = True):
        return psycopg.connect(self.database_url, autocommit=autocommit)

    def _ensure_schema(self, connection) -> None:
        if self._schema_ready:
            return
        with self.lock:
            if self._schema_ready:
                return
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS nts_kv_store (
                        store_key TEXT PRIMARY KEY,
                        payload JSONB NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
            self._schema_ready = True

    def load(self, key: str) -> Dict[str, Any]:
        """Load a dictionary from the configured durable backend."""
        if self.database_url:
            with self._connect() as connection:
                self._ensure_schema(connection)
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT payload FROM nts_kv_store WHERE store_key = %s",
                        (key,),
                    )
                    row = cursor.fetchone()
                    return row[0] if row else {}

        with self.lock:
            filepath = self.data_dir / f"{key}.json"
            if not filepath.exists():
                return {}
            try:
                with filepath.open("r", encoding="utf-8") as file_handle:
                    data = json.load(file_handle)
                    return data if isinstance(data, dict) else {}
            except (json.JSONDecodeError, OSError):
                return {}

    def save(self, key: str, data: Dict[str, Any]) -> None:
        """Atomically save a dictionary to the configured durable backend."""
        if self.database_url:
            with self._connect() as connection:
                self._ensure_schema(connection)
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO nts_kv_store (store_key, payload, updated_at)
                        VALUES (%s, %s, NOW())
                        ON CONFLICT (store_key) DO UPDATE
                        SET payload = EXCLUDED.payload, updated_at = NOW()
                        """,
                        (key, Jsonb(data)),
                    )
            return

        with self.lock:
            filepath = self.data_dir / f"{key}.json"
            filepath.parent.mkdir(parents=True, exist_ok=True)
            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=filepath.parent,
                    prefix=f".{filepath.name}.",
                    suffix=".tmp",
                    delete=False,
                ) as temp_file:
                    json.dump(data, temp_file, indent=2)
                    temp_file.flush()
                    os.fsync(temp_file.fileno())
                    temp_path = Path(temp_file.name)
                os.replace(temp_path, filepath)
            finally:
                if temp_path and temp_path.exists():
                    temp_path.unlink()

    def get(self, key: str, field: str, default: Any = None) -> Any:
        return self.load(key).get(field, default)

    def set(self, key: str, field: str, value: Any) -> None:
        def update(data: Dict[str, Any]) -> None:
            data[field] = value

        self.mutate(key, update)

    def mutate(self, key: str, mutator) -> Dict[str, Any]:
        """Atomically load, mutate, and persist one JSON document.

        PostgreSQL uses a row lock so concurrent Render workers cannot silently
        overwrite proposals submitted or reviewed at the same time.
        """
        if self.database_url:
            with self._connect(autocommit=False) as connection:
                self._ensure_schema(connection)
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO nts_kv_store (store_key, payload)
                        VALUES (%s, %s)
                        ON CONFLICT (store_key) DO NOTHING
                        """,
                        (key, Jsonb({})),
                    )
                    cursor.execute(
                        "SELECT payload FROM nts_kv_store WHERE store_key = %s FOR UPDATE",
                        (key,),
                    )
                    data = cursor.fetchone()[0]
                    updated = mutator(data)
                    if updated is not None:
                        data = updated
                    cursor.execute(
                        """
                        UPDATE nts_kv_store
                        SET payload = %s, updated_at = NOW()
                        WHERE store_key = %s
                        """,
                        (Jsonb(data), key),
                    )
                connection.commit()
                return data

        with self.lock:
            data = self.load(key)
            updated = mutator(data)
            if updated is not None:
                data = updated
            self.save(key, data)
            return data


store = PersistentStore()
