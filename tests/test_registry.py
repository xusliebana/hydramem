"""Tests for the entity disambiguation registry (collision avoidance)."""

from __future__ import annotations

from hydramem.ingest.registry import EntityRegistry, canonical_key, entity_id


def test_canonical_key_merges_variants():
    for variant in ("HydraMem", "hydramem", "HYDRAMEM", "Hydra Mem", "hydra-mem"):
        assert canonical_key(variant) == "hydramem"
    assert canonical_key("Night Gardener") == canonical_key("NightGardener")
    assert canonical_key("!!!") == ""


def test_distinct_entities_do_not_merge():
    assert canonical_key("LanceDB") != canonical_key("Grafeo")
    assert entity_id("p", "LanceDB") != entity_id("p", "Grafeo")


def test_registry_resolves_to_single_canonical_entity():
    reg = EntityRegistry("demo")
    for name, typ in [
        ("HydraMem", "identifier"),
        ("Hydra Mem", "concept"),
        ("HydraMem", "identifier"),
    ]:
        reg.register(name, typ)

    a = reg.resolve("HydraMem", "identifier")
    b = reg.resolve("Hydra Mem", "concept")
    assert a.id == b.id  # same canonical node
    assert a.name == b.name == "HydraMem"  # deterministic best display
    assert a.type == "identifier"  # most specific type wins
    assert reg.merged_count == 1  # two surface forms collapsed into one
    assert reg.id_for("hydra mem") == a.id  # any variant maps to the canonical id


def test_registry_disabled_keeps_legacy_ids():
    reg = EntityRegistry("demo", enabled=False)
    assert reg.resolve("HydraMem").id != reg.resolve("hydramem").id


def test_id_for_unregistered_returns_none():
    assert EntityRegistry("demo").id_for("Unknown") is None
