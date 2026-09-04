from strategy.features.zone_lifecycle import copy_snapshot_dict


def _sample():
    return {
        "active": [
            {"zone_high": 105.0, "zone_low": 101.0, "touch_count": 1, "context": {"note": "a"}},
            {"zone_high": 200.0, "zone_low": 190.0, "touch_count": 0, "context": {}},
        ],
        "mitigated": [],
        "expired_count": 3,
    }


def test_copy_is_deeply_equal_to_original():
    original = _sample()
    copied = copy_snapshot_dict(original)
    assert copied == original


def test_copy_is_not_the_same_top_level_object():
    original = _sample()
    copied = copy_snapshot_dict(original)
    assert copied is not original


def test_copy_lists_are_independent_objects():
    original = _sample()
    copied = copy_snapshot_dict(original)
    assert copied["active"] is not original["active"]


def test_copy_per_item_dicts_are_independent_objects():
    original = _sample()
    copied = copy_snapshot_dict(original)
    for a, b in zip(copied["active"], original["active"]):
        assert a is not b


def test_copy_context_dicts_are_independent_objects():
    original = _sample()
    copied = copy_snapshot_dict(original)
    for a, b in zip(copied["active"], original["active"]):
        assert a["context"] is not b["context"]


def test_mutating_copy_does_not_affect_original():
    original = _sample()
    copied = copy_snapshot_dict(original)

    copied["active"][0]["zone_high"] = -1.0
    copied["active"][0]["context"]["note"] = "poisoned"
    copied["active"].append({"fake": True})
    copied["expired_count"] = 999

    assert original["active"][0]["zone_high"] == 105.0
    assert original["active"][0]["context"]["note"] == "a"
    assert len(original["active"]) == 2
    assert original["expired_count"] == 3


def test_mutating_original_after_copy_does_not_affect_the_copy():
    original = _sample()
    copied = copy_snapshot_dict(original)

    original["active"][0]["zone_high"] = -1.0
    original["active"][0]["context"]["note"] = "poisoned"

    assert copied["active"][0]["zone_high"] == 105.0
    assert copied["active"][0]["context"]["note"] == "a"


def test_two_independent_copies_do_not_affect_each_other():
    original = _sample()
    copy_a = copy_snapshot_dict(original)
    copy_b = copy_snapshot_dict(original)

    copy_a["active"][0]["zone_high"] = -1.0
    copy_a["active"][0]["context"]["note"] = "poisoned"

    assert copy_b["active"][0]["zone_high"] == 105.0
    assert copy_b["active"][0]["context"]["note"] == "a"


def test_empty_lists_and_missing_context_handled():
    empty = {"active": [], "mitigated": [], "expired_count": 0}
    assert copy_snapshot_dict(empty) == empty
    assert copy_snapshot_dict(empty) is not empty

    no_context = {"active": [{"value": 1}], "expired_count": 0}
    copied = copy_snapshot_dict(no_context)
    assert copied == no_context
    assert copied["active"][0] is not no_context["active"][0]


def test_non_list_scalar_values_pass_through_unchanged():
    sample = {"expired_count": 42, "some_flag": True, "label": "x"}
    copied = copy_snapshot_dict(sample)
    assert copied == sample
