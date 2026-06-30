"""GNN-based spurious-edge detection for knowledge graph pruning.

GNNPruner encapsulates backend selection, scoring, and pruning application.
Backend priority: PyTorch Geometric → DGL → structural heuristic (always available).

Scalability
-----------
The PyG backend builds an identity feature matrix and runs a 2-layer GCN over
the full graph. That is fine for small KGs (< ~5 000 nodes) but explodes in
RAM for larger ones. To stay safe by default we:

* skip the GNN backend (and fall back to the heuristic) when the graph has
  more than :pydata:`MAX_GNN_NODES` nodes;
* expose ``MAX_GNN_NODES`` as an env-tunable knob
  (``HYDRAMEM_GNN_MAX_NODES``);
* use a low-rank random feature matrix instead of ``eye(N)`` so memory stays
  proportional to ``N · feat_dim``, not ``N²``;
* train for far fewer epochs and skip training entirely on graphs with very
  few edges.

For production-scale (> ~50 k nodes) we recommend running this offline with
proper GraphSAINT / NeighborLoader sampling — see ``docs/benchmarks.md``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from hydramem.core.logging import get_logger

logger = get_logger(__name__)

MAX_GNN_NODES: int = int(os.getenv("HYDRAMEM_GNN_MAX_NODES", "5000"))
_FEATURE_DIM: int = 32
_TRAIN_EPOCHS: int = 30
# Laplacian Positional Encodings — non-trainable spectral features for the
# GNN pruner. Default ON; can be disabled via env or config.
USE_LAPLACIAN_PE: bool = os.getenv("HYDRAMEM_GNN_LAPLACIAN_PE", "1").lower() not in (
    "0", "false", "no",
)
_LPE_K: int = int(os.getenv("HYDRAMEM_GNN_LPE_K", "32"))


# ---------------------------------------------------------------------------
# Shared edge features (capture ↔ training ↔ scoring must agree)
# ---------------------------------------------------------------------------


def compute_edge_features(graph) -> dict[tuple, dict]:
    """Per-edge structural features shared by capture, training, and scoring.

    One undirected projection + a degree map (O(E·deg)), cheap on local graphs.
    Every dict follows the ``PRUNE_FEATURES`` schema in ``garden/review.py`` so
    the learned weights stay interpretable and consistent across the loop.
    """
    undirected = graph.to_undirected()
    deg = {n: undirected.degree(n) for n in undirected.nodes()}
    max_deg = max(deg.values(), default=1) or 1
    feats: dict[tuple, dict] = {}
    for u, v in graph.edges():
        u_nb = set(undirected.neighbors(u))
        v_nb = set(undirected.neighbors(v))
        common = len(u_nb & v_nb)
        union = len(u_nb | v_nb) or 1
        du, dv = deg.get(u, 0), deg.get(v, 0)
        maxd = max(du, dv, 1)
        hub = 1.0 if (du > 20 or dv > 20) else 0.0
        heuristic = min(1.0, round(1.0 - (common / maxd) + (0.15 if hub else 0.0), 4))
        feats[(u, v)] = {
            "heuristic": heuristic,
            "jaccard": round(common / union, 4),
            "common": round(common / maxd, 4),
            "deg_u": round(du / max_deg, 4),
            "deg_v": round(dv / max_deg, 4),
            "hub": hub,
        }
    return feats


def edge_feature_vector(features: dict) -> list[float]:
    """Ordered feature vector (matches ``PRUNE_FEATURES``) for the linear model."""
    from hydramem.garden.review import PRUNE_FEATURES

    return [float(features.get(k, 0.0)) for k in PRUNE_FEATURES]


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class PruningResult:
    method: str
    edges_analysed: int
    suggested_edges: list[tuple[str, str]] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)
    suggested_count: int = 0


# ---------------------------------------------------------------------------
# GNNPruner
# ---------------------------------------------------------------------------

class GNNPruner:
    """Detect and optionally remove spurious edges from the knowledge graph.

    Usage::

        pruner = GNNPruner(store)
        result = pruner.analyse(project="default")
        pruner.apply(result, dry_run=False)
    """

    _SPURIOUS_THRESHOLD = 0.65

    def __init__(self, store) -> None:
        self._store = store
        self._backend = self._detect_backend()
        # Honour config knobs without hard import (config may be heavy in tests).
        try:
            from hydramem.core.config import load_config
            cfg = load_config()
            self._use_lpe = bool(getattr(cfg, "gnn_use_laplacian_pe", USE_LAPLACIAN_PE))
            self._lpe_k = int(getattr(cfg, "gnn_lpe_k", _LPE_K))
        except Exception:  # noqa: BLE001
            self._use_lpe = USE_LAPLACIAN_PE
            self._lpe_k = _LPE_K

    @staticmethod
    def _detect_backend() -> str:
        try:
            import torch  # noqa: F401
            import torch_geometric  # noqa: F401
            return "pyg"
        except ImportError:
            pass
        try:
            import dgl  # noqa: F401
            import torch  # noqa: F401
            return "dgl"
        except ImportError:
            pass
        return "heuristic"

    # ── Public API ────────────────────────────────────────────────────────────

    def analyse(self, project: str = "default") -> PruningResult:
        """Build the graph and score every edge for spuriousness."""
        graph = self._build_graph(project)
        if graph.number_of_nodes() < 2:
            return PruningResult(method="skipped", edges_analysed=0)

        # Learned (supervised) scorer takes priority when a per-project model
        # has been trained from the human-labelled golden dataset.
        weights = self._load_weights(project)
        if weights:
            backend = "learned"
            scores = self._learned_scores(graph, weights)
        else:
            # Auto-fallback to heuristic when the graph is too big for in-memory GNN.
            backend = self._backend
            if backend == "pyg" and graph.number_of_nodes() > MAX_GNN_NODES:
                logger.info(
                    "GNNPruner: graph has %d nodes (> MAX_GNN_NODES=%d); using heuristic backend",
                    graph.number_of_nodes(), MAX_GNN_NODES,
                )
                backend = "heuristic"

            if backend == "pyg":
                scores = self._pyg_scores(graph)
            else:
                scores = self._heuristic_scores(graph)
        suggested = [
            (u, v) for (u, v), s in scores.items()
            if s >= self._SPURIOUS_THRESHOLD
        ]
        logger.info(
            "GNNPruner (backend=%s): %d edges scored, %d suggested",
            backend, len(scores), len(suggested),
        )
        return PruningResult(
            method=backend,
            edges_analysed=len(scores),
            suggested_edges=suggested,
            scores={f"{u}|{v}": s for (u, v), s in scores.items()},
            suggested_count=len(suggested),
        )

    def apply(
        self,
        result: PruningResult,
        project: str = "default",
        dry_run: bool = True,
    ) -> dict:
        """Apply pruning suggestions, guarded by a final SR-MKG re-check."""
        from hydramem.core.types import Relation
        from hydramem.verification.srmkg import SRMKGScorer

        scorer = SRMKGScorer()
        removed = 0
        skipped = 0

        for from_id, to_id in result.suggested_edges:
            score_key = f"{from_id}|{to_id}"
            spuriousness = result.scores.get(score_key, 1.0)
            rel = Relation(
                from_entity=from_id,
                to_entity=to_id,
                relation_type="unknown",
                confidence=1.0 - spuriousness,
            )
            srmkg_result = scorer.verify(rel)
            if srmkg_result.accepted:
                skipped += 1
                continue
            if not dry_run:
                self._store.delete_relation(from_id, to_id, "unknown")
                removed += 1

        return {"removed": removed, "skipped_kept": skipped, "dry_run": dry_run}

    # ── Graph builder ─────────────────────────────────────────────────────────

    def feature_rows(self, project: str = "default") -> list[dict]:
        """Per-edge candidates (names + features + heuristic spuriousness).

        Uses only cheap structural features (no torch), so the Night Gardener's
        review-capture step can run it every cycle.
        """
        graph = self._build_graph(project)
        if graph.number_of_nodes() < 2:
            return []
        if graph.number_of_nodes() > MAX_GNN_NODES:
            logger.info(
                "feature_rows: graph has %d nodes (> MAX_GNN_NODES=%d); skipping capture",
                graph.number_of_nodes(), MAX_GNN_NODES,
            )
            return []
        rows: list[dict] = []
        for (u, v), f in compute_edge_features(graph).items():
            rows.append(
                {
                    "from_id": u,
                    "to_id": v,
                    "from_name": graph.nodes[u].get("name", ""),
                    "to_name": graph.nodes[v].get("name", ""),
                    "spuriousness": f["heuristic"],
                    "features": f,
                }
            )
        return rows

    def _load_weights(self, project: str):
        from hydramem.garden.review import load_prune_weights

        return load_prune_weights(project)

    def _learned_scores(self, graph, weights: dict) -> dict[tuple, float]:
        import math

        from hydramem.garden.review import PRUNE_FEATURES

        w = weights.get("weights", {})
        b = float(weights.get("intercept", 0.0))
        scores: dict[tuple, float] = {}
        for edge, f in compute_edge_features(graph).items():
            z = b + sum(
                float(w.get(k, 0.0)) * float(f.get(k, 0.0)) for k in PRUNE_FEATURES
            )
            z = max(-60.0, min(60.0, z))
            scores[edge] = round(1.0 / (1.0 + math.exp(-z)), 4)
        return scores

    def _build_graph(self, project: str):
        import networkx as nx
        graph = nx.DiGraph()
        for ent in self._store.list_entities(project=project):
            graph.add_node(ent["id"], **ent)
            for nb in self._store.get_entity_neighbors(ent["id"], hops=1):
                graph.add_edge(ent["id"], nb["id"])
        return graph

    # ── Heuristic scorer ─────────────────────────────────────────────────────

    @staticmethod
    def _heuristic_scores(graph) -> dict[tuple, float]:
        return {e: f["heuristic"] for e, f in compute_edge_features(graph).items()}

    # ── PyG scorer ───────────────────────────────────────────────────────────

    def _pyg_scores(self, graph) -> dict[tuple, float]:
        try:
            import torch
            import torch.nn.functional as F
            from torch_geometric.nn import GCNConv  # type: ignore
            from torch_geometric.utils import from_networkx  # type: ignore

            data = from_networkx(graph)
            n = data.num_nodes
            if n < 4 or data.edge_index.shape[1] == 0:
                return self._heuristic_scores(graph)

            # Feature matrix: prefer Laplacian PE + degree (real spectral
            # signal) and fall back to low-rank random features.
            torch.manual_seed(0)
            x = self._build_features(graph, n)

            class _LightGCN(torch.nn.Module):
                def __init__(self, in_c, hidden, out_c):
                    super().__init__()
                    self.conv1 = GCNConv(in_c, hidden)
                    self.conv2 = GCNConv(hidden, out_c)

                def forward(self, x, edge_index):
                    x = F.relu(self.conv1(x, edge_index))
                    return self.conv2(x, edge_index)

            model = _LightGCN(x.size(1), 16, 8)
            opt = torch.optim.Adam(model.parameters(), lr=0.01)
            model.train()
            for _ in range(_TRAIN_EPOCHS):
                opt.zero_grad()
                z = model(x, data.edge_index)
                adj_hat = torch.sigmoid(z @ z.T)
                ei = data.edge_index
                loss = F.binary_cross_entropy(
                    adj_hat[ei[0], ei[1]], torch.ones(ei.shape[1])
                )
                loss.backward()
                opt.step()

            model.eval()
            with torch.no_grad():
                z = model(x, data.edge_index)
                adj_hat = torch.sigmoid(z @ z.T).numpy()

            nodes = list(graph.nodes())
            scores: dict[tuple, float] = {}
            for u, v in graph.edges():
                try:
                    ui, vi = nodes.index(u), nodes.index(v)
                    scores[(u, v)] = round(1.0 - float(adj_hat[ui, vi]), 4)
                except Exception:
                    scores[(u, v)] = 0.5
            return scores

        except Exception as exc:
            logger.debug("PyG GNN failed, using heuristic: %s", exc)
            return self._heuristic_scores(graph)

    # ── Feature builder ──────────────────────────────────────────────────────

    def _build_features(self, graph, n: int):
        """Build node features for the GNN.

        When :attr:`_use_lpe` is on, returns the Laplacian
        Positional Encoding concatenated with normalised degree. Otherwise
        falls back to low-rank random features. See
        ``docs/internal/future_work/laplacian-pe.md``.
        """
        import torch

        if not self._use_lpe:
            return torch.randn(n, min(_FEATURE_DIM, n))

        try:
            import numpy as np

            from hydramem.garden.spectral import compute_lpe

            nodes, pe = compute_lpe(graph, k=self._lpe_k)
            if pe.size == 0:
                return torch.randn(n, min(_FEATURE_DIM, n))
            # Normalised degree as an additional structural feature.
            idx = {nid: i for i, nid in enumerate(nodes)}
            deg = np.zeros(n, dtype=np.float64)
            for nid in nodes:
                deg[idx[nid]] = float(graph.degree(nid))
            max_deg = float(deg.max()) or 1.0
            deg_feat = (deg / max_deg).reshape(-1, 1)
            feats = np.concatenate([pe, deg_feat], axis=1).astype(np.float32)
            logger.debug(
                "GNNPruner: using Laplacian PE features (n=%d, dim=%d)",
                n, feats.shape[1],
            )
            return torch.from_numpy(feats)
        except Exception as exc:  # noqa: BLE001
            logger.debug("LPE feature build failed (%s); falling back to random", exc)
            return torch.randn(n, min(_FEATURE_DIM, n))
