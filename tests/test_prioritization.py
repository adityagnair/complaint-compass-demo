from backend.services.prioritization import score_issues


def test_priority_formula_and_normalization_are_transparent():
    issues = [
        {"average_severity": 5, "complaint_count": 10, "affected_customers": 8},
        {"average_severity": 3, "complaint_count": 5, "affected_customers": 4},
    ]

    scored = score_issues(issues)

    assert scored[0]["severity_score"] == 100
    assert scored[0]["frequency_score"] == 100
    assert scored[0]["impact_score"] == 100
    assert scored[0]["priority_score"] == 100
    assert scored[1]["severity_score"] == 50
    assert scored[1]["frequency_score"] == 50
    assert scored[1]["impact_score"] == 50
    assert scored[1]["priority_score"] == 50


def test_priority_handles_no_known_customers_and_empty_analysis():
    assert score_issues([]) == []
    issue = {"average_severity": 1, "complaint_count": 3, "affected_customers": 0}
    score_issues([issue])
    assert issue["severity_score"] == 0
    assert issue["frequency_score"] == 100
    assert issue["impact_score"] == 0
    assert issue["priority_score"] == 30
