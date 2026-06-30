"""Tests for the Laplacian Positional Encodings helper."""
from __future__ import annotations

import networkx as nx
import numpy as np

from hydramem.garden.spectral import compute_lpe


def test_lpe_dimensions_on_path_graph():
    g = nx.path_graph(10)
    nodes, pe = compute_lpe(g, k=4)
    assert len(nodes) == 10
    assert pe.shape == (10, 4)


def test_lpe_drops_trivial_eigenvector():
    # The trivial eigenvector (constant) should not be in the output, so
    # every column should have non-zero variance on a connected graph.
    g = nx.cycle_graph(8)
    _, pe = compute_lpe(g, k=4, sign_flip=False)
    assert pe.shape == (8, 4)
    assert all(pe[:, j].std() > 1e-6 for j in range(pe.shape[1]))


def test_lpe_handles_empty_graph():
    g = nx.DiGraph()
    nodes, pe = compute_lpe(g, k=4)
    assert nodes == []
    assert pe.shape == (0, 0)


def test_lpe_clipped_when_k_exceeds_n():
    g = nx.path_graph(3)
    _, pe = compute_lpe(g, k=32)
    # n - 1 = 2 non-trivial eigenvectors at most.
    assert pe.shape[1] <= 2


def test_lpe_is_deterministic_with_seed():
    g = nx.cycle_graph(12)
    _, pe1 = compute_lpe(g, k=5, seed=42)
    _, pe2 = compute_lpe(g, k=5, seed=42)
    assert np.allclose(pe1, pe2)


def test_lpe_handles_disconnected_components():
    g = nx.disjoint_union(nx.path_graph(4), nx.path_graph(4))
    nodes, pe = compute_lpe(g, k=3)
    assert len(nodes) == 8
    assert pe.shape == (8, 3)
