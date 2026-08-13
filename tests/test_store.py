from app.store import PersistentStore


def test_json_store_survives_new_store_instance(tmp_path):
    first = PersistentStore(data_dir=str(tmp_path), database_url="")
    first.save(
        "translation_memory",
        {"proposals": [{"proposal_id": "proposal-123", "status": "proposed"}]},
    )

    restarted = PersistentStore(data_dir=str(tmp_path), database_url="")

    assert restarted.load("translation_memory") == {
        "proposals": [{"proposal_id": "proposal-123", "status": "proposed"}]
    }


def test_json_store_replaces_existing_value_atomically(tmp_path):
    store = PersistentStore(data_dir=str(tmp_path), database_url="")
    store.save("translation_memory", {"version": 1})
    store.save("translation_memory", {"version": 2})

    assert store.load("translation_memory") == {"version": 2}
    assert list(tmp_path.glob("*.tmp")) == []
