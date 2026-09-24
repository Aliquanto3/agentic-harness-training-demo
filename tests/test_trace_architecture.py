from __future__ import annotations

import pytest
from pydantic import ValidationError

from wavestack.trace.catalog import ArchitectureChangedPayload
from wavestack.trace.envelope import Envelope, now_iso
from wavestack.trace.scope import TraceScope

NODES = [
    {
        "id": "core.harness",
        "kind": "harness",
        "hosting": "local",
        "label_fr": "Harnais WaveStack",
        "wanted": True,
        "available": True,
        "reason_fr": None,
    },
    {
        "id": "core.model",
        "kind": "model",
        "hosting": "local",
        "label_fr": "Modèle",
        "wanted": True,
        "available": True,
        "reason_fr": None,
    },
]


def _envelope(payload: dict) -> Envelope:
    scope = TraceScope()
    return Envelope(
        seq=1,
        ts=now_iso(),
        session_epoch=0,
        turn_id=scope.turn_id,
        context_id=scope.context_id,
        call_id=scope.call_id,
        step_id=scope.step_id,
        parent_step=scope.parent_step,
        kind="architecture_changed",
        actor=scope.actor,
        trigger=scope.trigger,
        brick=scope.brick,
        component=scope.component,
        edge=scope.edge,
        payload=payload,
    )


def test_two_fixed_nodes_no_edges_is_valid():
    envelope = _envelope({"nodes": NODES, "edges": []})
    assert envelope.payload["nodes"][0]["id"] == "core.harness"


def test_payload_model_parses_edge_from_alias():
    payload = ArchitectureChangedPayload.model_validate(
        {
            "nodes": NODES,
            "edges": [{"from": "core.harness", "to": "core.model", "crosses_boundary": False}],
        }
    )
    assert payload.edges[0].from_ == "core.harness"
    assert payload.edges[0].crosses_boundary is False


def test_unknown_node_kind_is_rejected():
    bad_node = {**NODES[0], "kind": "tool"}  # not emitted yet
    with pytest.raises(ValidationError):
        _envelope({"nodes": [bad_node], "edges": []})


def test_missing_required_field_is_rejected():
    with pytest.raises(ValidationError):
        _envelope({"nodes": [{"id": "core.harness"}], "edges": []})


def test_edge_to_an_absent_node_is_rejected():
    edge = {"from": "short_memory.history", "to": "core.harness", "crosses_boundary": False}
    with pytest.raises(ValidationError):
        _envelope({"nodes": NODES, "edges": [edge]})
