"""Provisional unified evaluation public interface."""

from .models import EVALUATION_RESULT_SCHEMA_VERSION, EvaluationRunResult
from .runner import run_evaluation, validate_result

__all__ = ["EVALUATION_RESULT_SCHEMA_VERSION", "EvaluationRunResult", "run_evaluation", "validate_result"]
