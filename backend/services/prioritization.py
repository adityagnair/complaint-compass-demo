from typing import Any

SCORING_WEIGHTS = {"severity": 0.4, "frequency": 0.3, "impact": 0.3}
SCORING_FORMULA = "Priority = 0.4S + 0.3F + 0.3I"
SEVERITY_NORMALIZATION = "S = ((average severity on 1–5 scale - 1) / 4) × 100"
RELATIVE_NORMALIZATION = "F and I = (issue value / maximum value in this analysis run) × 100"


def _relative_scores(values: list[float]) -> list[float]:
    maximum = max(values, default=0)
    if maximum <= 0:
        return [0.0 for _ in values]
    return [round(max(0.0, min(100.0, value / maximum * 100)), 2) for value in values]


def score_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add normalized, auditable component scores and weighted priority scores."""
    frequencies = _relative_scores([float(issue["complaint_count"]) for issue in issues])
    impacts = _relative_scores([float(issue["affected_customers"]) for issue in issues])
    for index, issue in enumerate(issues):
        severity = max(0.0, min(100.0, (float(issue["average_severity"]) - 1.0) / 4.0 * 100.0))
        frequency = frequencies[index]
        impact = impacts[index]
        issue["severity_score"] = round(severity, 2)
        issue["frequency_score"] = frequency
        issue["impact_score"] = impact
        issue["priority_score"] = round(
            SCORING_WEIGHTS["severity"] * severity
            + SCORING_WEIGHTS["frequency"] * frequency
            + SCORING_WEIGHTS["impact"] * impact,
            2,
        )
    return issues
