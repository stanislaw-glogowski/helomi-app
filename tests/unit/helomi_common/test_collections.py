from helomi_common.collections import DeepMergeDict


def test_deep_merge_dict_basic() -> None:
    base = DeepMergeDict({"a": 1, "b": 2})
    assert base["a"] == 1
    assert base["b"] == 2


def test_deep_merge_dict_merged_with_none() -> None:
    base = DeepMergeDict({"a": 1})
    merged = base.merged_with(None)
    assert merged is base


def test_deep_merge_dict_nested_merge() -> None:
    base = DeepMergeDict(
        {
            "audio": {"channels": 1, "rate": 16000},
            "profile": "default",
        }
    )
    override = {
        "audio": {"rate": 48000, "buffer": 512},
        "profile": "custom",
        "extra": True,
    }
    merged = base.merged_with(override)

    assert isinstance(merged, DeepMergeDict)
    assert merged["audio"]["channels"] == 1
    assert merged["audio"]["rate"] == 48000
    assert merged["audio"]["buffer"] == 512
    assert merged["profile"] == "custom"
    assert merged["extra"] is True
    # Ensure original base was not mutated
    assert base["audio"]["rate"] == 16000


def test_deep_merge_dict_or_operator() -> None:
    base = DeepMergeDict({"key1": "val1", "nested": {"x": 10}})
    override = {"key2": "val2", "nested": {"y": 20}}
    merged = base | override

    assert isinstance(merged, DeepMergeDict)
    assert merged["key1"] == "val1"
    assert merged["key2"] == "val2"
    assert merged["nested"] == {"x": 10, "y": 20}


def test_deep_merge_dict_override_non_dict_with_dict() -> None:
    base = DeepMergeDict({"key": "scalar"})
    override = {"key": {"sub": "val"}}
    merged = base.merged_with(override)
    assert merged["key"] == {"sub": "val"}
