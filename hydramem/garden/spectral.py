"""Spectral graph features — Laplacian Positional Encodings.

Provides ``compute_lpe(graph, k)`` to build non-trainable positional features
for the GNN pruner. Pure NumPy (no SciPy dependency) so it runs on the same
stack the rest of HydraMem uses.

Roadmap slot: 0.4.x — Geometric memory.
See ``docs/internal/future_work/laplacian-pe.md`` for the design discussion.
"""

from __future__ import annotations

from hydramem.core.logging import get_logger

logger = get_logger(__name__)


def compute_lpe(
    graph,
    k: int = 32,
    *,
    seed: int = 0,
    sign_flip: bool = True,
) -> tuple[list, object]:  # returns numpy array, kept loose to avoid hard numpy import
    """Compute Laplacian Positional Encodings for ``graph``.

    Parameters
    ----------
    graph:
        A NetworkX graph (directed or undirected). Direction is ignored —
        the symmetric normalised Laplacian is computed on the underlying
        undirected graph.
    k:
        Number of non-trivial eigenvectors to keep. The actual returned
        feature dimension is ``min(k, n_nodes - 1)``.
    seed:
        Random seed for the sign-flip augmentation. Determinism is
        important for reproducible benchmarks.
    sign_flip:
        Whether to apply a random sign per eigenvector. The Laplacian
        eigenvectors are unique only up to sign; flipping at training
        time mitigates the ambiguity.

    Returns
    -------
    (nodes, features):
        ``nodes`` is the ordered list of node ids; ``features`` is a NumPy
        ``(n_nodes, dim)`` array.

    Notes
    -----
    Uses ``numpy.linalg.eigh`` on the dense normalised Laplacian. This is
    O(n³) so the GNN pruner already caps the graph at ``MAX_GNN_NODES``
    (5 000 by default) before calling here.

    Disconnected components are handled implicitly — eigenvectors of a
    block-diagonal Laplacian are the per-component eigenvectors padded
    with zeros, which is the desired behaviour.
    """
    import numpy as np

    nodes = list(graph.nodes())
    n = len(nodes)
    if n == 0:
        return nodes, np.zeros((0, 0))

    idx = {nid: i for i, nid in enumerate(nodes)}

    # Symmetric adjacency from a (possibly directed) graph.
    a = np.zeros((n, n), dtype=np.float64)
    for u, v in graph.edges():
        ui = idx.get(u)
        vi = idx.get(v)
        if ui is None or vi is None or ui == vi:
            continue
        a[ui, vi] = 1.0
        a[vi, ui] = 1.0

    deg = a.sum(axis=1)
    # D^(-1/2)
    with np.errstate(divide="ignore"):
        d_inv_sqrt = np.where(deg > 0, 1.0 / np.sqrt(deg), 0.0)
    # L_sym = I - D^(-1/2) A D^(-1/2)
    laplacian = np.eye(n) - (d_inv_sqrt[:, None] * a) * d_inv_sqrt[None, :]

    try:
        eigvals, eigvecs = np.linalg.eigh(laplacian)
    except np.linalg.LinAlgError as exc:
        logger.debug("LPE eigendecomposition failed: %s", exc)
        return nodes, np.zeros((n, 0))

    # eigh returns ascending order. The smallest eigenvalue (≈ 0) is the
    # trivial constant eigenvector — drop it.
    order = np.argsort(eigvals)
    eigvecs = eigvecs[:, order]
    take = min(k, max(0, n - 1))
    pe = eigvecs[:, 1 : 1 + take]

    if sign_flip and pe.size > 0:
        rng = np.random.default_rng(seed)
        signs = rng.choice([-1.0, 1.0], size=pe.shape[1])
        pe = pe * signs[None, :]

    return nodes, pe
