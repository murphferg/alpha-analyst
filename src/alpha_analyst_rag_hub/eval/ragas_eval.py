"""
RAGAS Evaluation — measures retrieval-augmented generation quality using the
RAGAS framework (faithfulness, answer relevancy, context recall, etc.).

Run with:  python -m eval.ragas_eval
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class RagasEvaluator:
    """Wraps RAGAS to evaluate the quality of synthesised insights.

    Metrics computed:
    - **faithfulness**: Are claims in the answer supported by the retrieved context?
    - **answer_relevancy**: Is the answer relevant to the question?
    - **context_recall**: Does the retrieved context cover the reference answer?
    """

    def __init__(self, llm: Any | None = None) -> None:
        self._llm = llm

    async def evaluate(
        self,
        questions: list[str],
        answers: list[str],
        contexts: list[list[str]],
        ground_truths: list[str] | None = None,
    ) -> dict[str, float]:
        """Run the RAGAS evaluation suite and return a dict of metric → score.

        Parameters
        ----------
        questions:
            One question per sample (e.g. "What are the key risks for AAPL?").
        answers:
            The synthesised answer / insight for each question.
        contexts:
            A list of retrieved document excerpts per question.
        ground_truths:
            Optional reference answers for context-recall measurement.

        Returns
        -------
        dict mapping metric name to average score across all samples.
        """
        try:
            from ragas import evaluate  # type: ignore[import-untyped]
            from ragas.metrics import (  # type: ignore[import-untyped]
                answer_relevancy,
                context_recall,
                faithfulness,
            )
            from datasets import Dataset  # type: ignore[import-untyped]
        except ImportError:
            logger.warning(
                "ragas or datasets not installed. Install with: "
                "poetry install / pip install ragas datasets"
            )
            return {}

        data: dict[str, list] = {
            "question": questions,
            "answer": answers,
            "contexts": contexts,
        }
        if ground_truths:
            data["ground_truth"] = ground_truths

        dataset = Dataset.from_dict(data)

        metrics = [faithfulness, answer_relevancy]
        if ground_truths:
            metrics.append(context_recall)

        result = evaluate(dataset, metrics=metrics, llm=self._llm)
        scores: dict[str, float] = {k: float(v) for k, v in result.items()}
        logger.info("RAGAS evaluation scores: %s", scores)
        return scores


# ── CLI entrypoint ────────────────────────────────────────────────────────────

async def _demo() -> None:
    """Run a small smoke-test evaluation with stub data."""
    evaluator = RagasEvaluator()
    scores = await evaluator.evaluate(
        questions=["What are the key risks for AAPL?"],
        answers=["Apple faces supply-chain concentration risk and regulatory scrutiny."],
        contexts=[
            [
                "Apple Inc. relies heavily on a small number of contract manufacturers.",
                "Regulators in the EU are examining App Store policies.",
            ]
        ],
        ground_truths=["Apple faces supply-chain and regulatory risks."],
    )
    print("Evaluation scores:", scores)


if __name__ == "__main__":
    asyncio.run(_demo())
