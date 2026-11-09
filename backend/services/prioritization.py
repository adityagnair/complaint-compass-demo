from typing import Any

SCORING_WEIGHTS = {"severity": 0.4, "frequency": 0.3, "impact": 0.3}
SCORING_FORMULA = "Priority = wS·S + wF·F + wI·I; wS = 0.4×severity coverage and the remaining weight is shared by F and I"
SEVERITY_NORMALIZATION = "S uses supplied severity values only; effective severity weight = 0.4 × severity coverage, with the unused weight split evenly between frequency and impact"
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
        coverage = max(0.0, min(1.0, float(issue.get("severity_coverage_fraction", issue.get("severity_coverage", 1.0)))))
        average_severity = issue.get("average_severity")
        severity = max(0.0, min(100.0, (float(average_severity) - 1.0) / 4.0 * 100.0)) if average_severity is not None else 0.0
        frequency = frequencies[index]
        impact = impacts[index]
        severity_weight = SCORING_WEIGHTS["severity"] * coverage
        remaining_weight = SCORING_WEIGHTS["severity"] - severity_weight
        frequency_weight = SCORING_WEIGHTS["frequency"] + remaining_weight / 2
        impact_weight = SCORING_WEIGHTS["impact"] + remaining_weight / 2
        issue["severity_score"] = round(severity, 2)
        issue["frequency_score"] = frequency
        issue["impact_score"] = impact
        issue["severity_coverage"] = round(coverage * 100, 2)
        issue["severity_coverage_fraction"] = coverage
        issue["severity_weight"] = round(severity_weight, 4)
        issue["frequency_weight"] = round(frequency_weight, 4)
        issue["impact_weight"] = round(impact_weight, 4)
        issue["priority_score"] = round(
            severity_weight * severity
            + frequency_weight * frequency
            + impact_weight * impact,
            2,
        )
    return issues
