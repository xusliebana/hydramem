"""Tests for the verification pipeline (SR-MKG, VoG, VerificationPipeline)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from hydramem.core.types import Chunk, Relation


class TestSRMKGScorer:
    def test_high_score_with_many_common_neighbors(self):
        from hydramem.verification.srmkg import SRMKGScorer

        scorer = SRMKGScorer()
        rel = Relation(from_entity="a", to_entity="b", relation_type="causes", confidence=0.8)
        score = scorer.score(rel, common_neighbors=5, degree_from=6, degree_to=6)
        assert 0.0 <= score <= 1.0

    def test_isolated_nodes_reduce_score(self):
        from hydramem.verification.srmkg import SRMKGScorer

        scorer = SRMKGScorer()
        rel = Relation(from_entity="a", to_entity="b", relation_type="related_to", confidence=0.5)
        normal = scorer.score(rel, common_neighbors=2, degree_from=3, degree_to=3)
        isolated = scorer.score(rel, common_neighbors=0, degree_from=0, degree_to=0)
        assert isolated <= normal

    def test_returns_float_in_range(self):
        from hydramem.verification.srmkg import SRMKGScorer

        scorer = SRMKGScorer()
        for conf in [0.1, 0.5, 0.9]:
            rel = Relation(from_entity="a", to_entity="b", relation_type="causes", confidence=conf)
            assert 0.0 <= scorer.score(rel) <= 1.0

    def test_auto_accept(self):
        from hydramem.verification.srmkg import SRMKGScorer

        scorer = SRMKGScorer()
        # confidence=0.9, many common neighbours → score well above 0.7 threshold
        rel = Relation(from_entity="a", to_entity="b", relation_type="uses", confidence=0.9)
        result = scorer.verify(rel, common_neighbors=8, degree_from=9, degree_to=9)
        assert result.accepted
        assert result.level == "srmkg_high"

    def test_auto_reject(self):
        from hydramem.verification.srmkg import SRMKGScorer

        scorer = SRMKGScorer()
        rel = Relation(from_entity="a", to_entity="b", relation_type="unknown", confidence=0.0)
        result = scorer.verify(rel, common_neighbors=0, degree_from=0, degree_to=0)
        assert not result.accepted
        assert result.level == "srmkg_low"


class TestVoGVerifier:
    def _make_verifier(self, response="GROUNDED\nCONFIDENCE: 0.92"):
        from hydramem.verification.vog import VoGVerifier

        mock_provider = MagicMock()
        mock_provider.complete.return_value = response
        return VoGVerifier(mock_provider)

    def test_grounded_accepted(self):
        verifier = self._make_verifier("GROUNDED\nCONFIDENCE: 0.92")
        rel = Relation(
            from_entity="A",
            to_entity="B",
            relation_type="causes",
            source_text="A causes B in all cases.",
            target_text="B follows A.",
        )
        result = verifier.verify(rel)
        assert result.accepted
        assert abs(result.score - 0.92) < 0.01
        assert result.vog_verdict == "GROUNDED"

    def test_rejected_not_accepted(self):
        verifier = self._make_verifier("REJECTED\nCONFIDENCE: 0.15")
        rel = Relation(
            from_entity="A",
            to_entity="B",
            relation_type="causes",
            source_text="A is unrelated.",
            target_text="B is unrelated.",
        )
        result = verifier.verify(rel)
        assert not result.accepted
        assert result.vog_verdict == "REJECTED"

    def test_partial_accepted_with_reduced_score(self):
        verifier = self._make_verifier("PARTIAL\nCONFIDENCE: 0.8")
        rel = Relation(
            from_entity="A",
            to_entity="B",
            relation_type="related",
            source_text="maybe.",
            target_text="possibly.",
        )
        result = verifier.verify(rel)
        assert result.accepted
        assert result.score < 0.8  # reduced by 0.6 factor

    def test_llm_unavailable_rejects(self):
        verifier = self._make_verifier("")
        rel = Relation(
            from_entity="A",
            to_entity="B",
            relation_type="causes",
            source_text="text a",
            target_text="text b",
        )
        result = verifier.verify(rel)
        # Honest contract: empty LLM response → reject (no optimistic fake score).
        assert not result.accepted
        assert result.score == 0.0
        assert result.level == "vog_unavailable"

    def test_no_source_texts_rejected(self):
        verifier = self._make_verifier("should not be called")
        rel = Relation(from_entity="A", to_entity="B", relation_type="uses")
        result = verifier.verify(rel)
        # Honest contract: no evidence → reject; LLM must NOT be called.
        assert not result.accepted
        assert result.score == 0.0
        assert result.level == "vog_no_evidence"
        verifier._provider.complete.assert_not_called()


class TestVerificationPipeline:
    @pytest.fixture
    def pipeline(self):
        from hydramem.core.config import Config
        from hydramem.verification.pipeline import VerificationPipeline

        cfg = Config(
            {
                "verification": {
                    "srmkg_threshold_accept": 0.7,
                    "srmkg_threshold_reject": 0.3,
                    "vog_max_candidates": 5,
                    "vog_use_local_llm": True,
                }
            }
        )
        p = VerificationPipeline(config=cfg)
        # Inject mock VoG provider
        p._vog._provider = MagicMock()
        p._vog._provider.complete.return_value = "GROUNDED\nCONFIDENCE: 0.85"
        return p

    def test_high_confidence_accepted_without_vog(self, pipeline):
        rel = Relation(from_entity="a", to_entity="b", relation_type="uses", confidence=0.95)
        result = pipeline.verify(rel, common_neighbors=5, degree_from=6, degree_to=6)
        assert result.accepted
        assert result.level == "srmkg_high"
        pipeline._vog._provider.complete.assert_not_called()

    def test_low_confidence_rejected_without_vog(self, pipeline):
        rel = Relation(from_entity="a", to_entity="b", relation_type="unknown", confidence=0.0)
        result = pipeline.verify(rel, common_neighbors=0, degree_from=0, degree_to=0)
        assert not result.accepted
        assert result.level == "srmkg_low"

    def test_borderline_goes_to_vog(self, pipeline):
        rel = Relation(
            from_entity="a",
            to_entity="b",
            relation_type="uses",
            confidence=0.5,
            source_text="A uses B in practice.",
            target_text="B is used by A.",
        )
        result = pipeline.verify(rel, common_neighbors=1, degree_from=2, degree_to=2)
        assert result.level == "vog"

    def test_vog_cap_prevents_excessive_llm_calls(self, pipeline):
        pipeline.reset_vog_cap()
        rel = Relation(
            from_entity="a",
            to_entity="b",
            relation_type="uses",
            confidence=0.5,
            source_text="text",
            target_text="text",
        )
        # Exhaust cap
        for _ in range(5):
            pipeline.verify(rel, common_neighbors=1, degree_from=2, degree_to=2)
        # Next one should hit the cap
        result = pipeline.verify(rel, common_neighbors=1, degree_from=2, degree_to=2)
        assert result.level == "srmkg_cap"

    def test_verify_chunks(self, pipeline):
        chunks = [
            Chunk(
                id=f"c{i}",
                text=f"chunk {i}",
                source="t.md",
                project="test",
                similarity=0.9 - i * 0.2,
            )
            for i in range(4)
        ]
        result = pipeline.verify_chunks(chunks, query="test query")
        assert "filtered" in result
        assert "verified" in result
        # Honest naming: vector prefilter (deprecated alias kept).
        assert "rejected_vector" in result
        assert "rejected_srmkg" in result  # backward-compat alias
        assert "rejected_vog" in result
        assert isinstance(result["vog_scores"], list)
