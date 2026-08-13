import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
import threading
import tempfile


class PersistentStore:
    """
    Thread-safe persistent data store.
    Uses JSON files in NTS_DATA_DIR for durability.
    """
    
    def __init__(self):
        self.data_dir = Path(os.getenv("NTS_DATA_DIR", "./data"))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
    
    def load(self, key: str) -> Dict[str, Any]:
        """Load data from persistent store."""
        with self.lock:
            filepath = self.data_dir / f"{key}.json"
            if filepath.exists():
                try:
                    with open(filepath, 'r') as f:
                        return json.load(f)
                except (json.JSONDecodeError, IOError):
                    return {}
            return {}
    
    def save(self, key: str, data: Dict[str, Any]) -> None:
        """Save data to persistent store."""
        with self.lock:
            filepath = self.data_dir / f"{key}.json"
            # Write-then-replace prevents a process interruption from leaving a
            # partially written JSON file behind.
            fd, temporary_name = tempfile.mkstemp(
                prefix=f".{key}.", suffix=".tmp", dir=self.data_dir
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temporary_name, filepath)
            finally:
                if os.path.exists(temporary_name):
                    os.unlink(temporary_name)
    
    def get(self, key: str, field: str, default: Any = None) -> Any:
        """Get a field from stored data."""
        data = self.load(key)
        return data.get(field, default)
    
    def set(self, key: str, field: str, value: Any) -> None:
        """Set a field in stored data."""
        with self.lock:
            data = self.load(key)
            data[field] = value
            self.save(key, data)

    def mutate(self, key: str, mutator) -> Dict[str, Any]:
        """Atomically load, mutate, and persist one JSON document."""
        with self.lock:
            data = self.load(key)
            updated = mutator(data)
            if updated is not None:
                data = updated
            self.save(key, data)
            return data


# Global store instance
store = PersistentStore()
