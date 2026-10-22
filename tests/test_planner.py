"""Generation safety contracts, independent of Anki and dictionary payloads."""

import pytest

from katanki.generation.planner import (
    Identity,
    LearningUnit,
    plan_generation,
    prerequisite_order,
)


def identity(key="景", kind="kanji", mode="recognition"):
    return Identity(f"{kind}-{mode}", key)


def test_character_key_and_separate_note_types():
    assert identity() != identity(mode="production")
    assert identity("か\u3099", "primitive") == identity("が", "primitive")
    assert identity("vg:shape/001", "primitive").key == "vg:shape/001"
    for note_type, key in (("unknown", "景"), ("kanji-recognition", "")):
        with pytest.raises(ValueError):
            Identity(note_type, key)


def test_recognition_does_not_imply_production_or_generate_unselected_production():
    recognition = LearningUnit(identity())
    production = LearningUnit(identity(mode="production"))
    plan = plan_generation([recognition], (), include_primitives=False)
    assert [item.unit for item in plan.items] == [recognition]
    plan = plan_generation(
        [recognition, production], [recognition.identity], include_primitives=False
    )
    outcomes = {item.unit.identity: item.outcome for item in plan.items}
    assert outcomes == {recognition.identity: "skip", production.identity: "create"}


def test_graph_order_is_deterministic_and_deduplicates_dependencies():
    root = identity()
    component = identity("vg:unencoded", "primitive")
    units = {root: LearningUnit(root, (component, component)), component: LearningUnit(component)}
    assert prerequisite_order(units) == (component, root)
    assert prerequisite_order(dict(reversed(list(units.items())))) == (component, root)


def test_invalid_graphs_are_rejected():
    a, b = identity(), identity("色")
    for graph in (
        {a: LearningUnit(a, (b,))},
        {a: LearningUnit(a, (b,)), b: LearningUnit(b, (a,))},
        {a: LearningUnit(b)},
    ):
        with pytest.raises(ValueError):
            prerequisite_order(graph)


def test_plan_rerun_and_source_deletion_are_independent():
    units = [LearningUnit(identity(char)) for char in "景色景"]
    plan = plan_generation(units, (), include_primitives=True)
    assert [item.outcome for item in plan.items] == ["create", "create"]
    existing = [item.unit.identity for item in plan.items]
    assert all(
        item.outcome == "skip"
        for item in plan_generation(units, existing, include_primitives=True).items
    )
    assert plan_generation([], existing, include_primitives=True).items == ()


def test_unavailable_prerequisites_and_optional_primitives():
    root, primitive = identity(), identity("shape", "primitive")
    units = [
        LearningUnit(root, (primitive,)),
        LearningUnit(primitive, unavailable_reason="No data"),
    ]
    assert all(
        item.outcome == "unavailable"
        for item in plan_generation(units, (), include_primitives=True).items
    )
    plan = plan_generation(units, (), include_primitives=False)
    assert len(plan.items) == 1
    assert plan.items[0].outcome == "create"
    plan = plan_generation(units, (primitive,), include_primitives=True)
    assert [item.outcome for item in plan.items] == ["skip", "create"]


def test_conflicting_units_fail_instead_of_silently_overwriting():
    with pytest.raises(ValueError, match="Conflicting"):
        plan_generation(
            [LearningUnit(identity(), label="one"), LearningUnit(identity(), label="two")],
            (),
            include_primitives=True,
        )
