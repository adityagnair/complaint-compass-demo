from typing import Any

SCORING_WEIGHTS = {"severity": 0.5, "frequency": 0.5}
SCORING_FORMULA = "Priority = wS·S + wF·F; base weights are 0.5 each, with the severity weight scaled by severity coverage and the remainder assigned to frequency"
SEVERITY_NORMALIZATION = "S maps average supplied or Ollama-assessed severity from 1–5 to 0–100; effective severity weight = 0.5 × severity coverage, and the remainder is assigned to F"
RELATIVE_NORMALIZATION = "F = unique complaint count / maximum unique complaint count in this analysis run × 100"


def _relative_scores(values: list[float]) -> list[float]:
    maximum = max(values, default=0)
    if maximum <= 0:
        return [0.0 for _ in values]
    return [round(max(0.0, min(100.0, value / maximum * 100)), 2) for value in values]


def score_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add normalized, auditable component scores and weighted priority scores."""
    frequencies = _relative_scores([float(issue["complaint_count"]) for issue in issues])
    for index, issue in enumerate(issues):
        average_severity = issue.get("average_severity")
        coverage = max(0.0, min(1.0, float(issue.get("severity_coverage_fraction", issue.get("severity_coverage", 1.0))))) if average_severity is not None else 0.0
        severity = max(0.0, min(100.0, (float(average_severity) - 1.0) / 4.0 * 100.0)) if average_severity is not None else 0.0
        frequency = frequencies[index]
        severity_weight = SCORING_WEIGHTS["severity"] * coverage
        frequency_weight = SCORING_WEIGHTS["frequency"] + SCORING_WEIGHTS["severity"] - severity_weight
        issue["severity_score"] = round(severity, 2)
        issue["frequency_score"] = frequency
        # Retain this legacy field for compatibility; customer impact is not part of priority.
        issue["impact_score"] = 0.0
        issue["severity_coverage"] = round(coverage * 100, 2)
        issue["severity_coverage_fraction"] = coverage
        issue["severity_weight"] = round(severity_weight, 4)
        issue["frequency_weight"] = round(frequency_weight, 4)
        issue["impact_weight"] = 0.0
        issue["priority_score"] = round(
            severity_weight * severity + frequency_weight * frequency,
            2,
        )
    return issues
