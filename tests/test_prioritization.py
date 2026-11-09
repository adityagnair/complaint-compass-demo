from backend.services.prioritization import score_issues


def test_priority_formula_and_normalization_are_transparent():
    issues = [
        {"average_severity": 5, "complaint_count": 10, "affected_customers": 8},
        {"average_severity": 3, "complaint_count": 5, "affected_customers": 4},
    ]

    scored = score_issues(issues)

    assert scored[0]["severity_score"] == 100
    assert scored[0]["frequency_score"] == 100
    assert scored[0]["impact_score"] == 0
    assert scored[0]["priority_score"] == 100
    assert scored[1]["severity_score"] == 50
    assert scored[1]["frequency_score"] == 50
    assert scored[1]["impact_score"] == 0
    assert scored[1]["priority_score"] == 50


def test_priority_handles_no_known_customers_and_empty_analysis():
    assert score_issues([]) == []
    issue = {"average_severity": 1, "complaint_count": 3, "affected_customers": 0}
    score_issues([issue])
    assert issue["severity_score"] == 0
    assert issue["frequency_score"] == 100
    assert issue["impact_score"] == 0
    assert issue["priority_score"] == 50


def test_missing_severity_moves_its_weight_to_frequency():
    issues = [
        {"average_severity": None, "severity_coverage": 0, "complaint_count": 4, "affected_customers": 1},
        {"average_severity": 5, "severity_coverage": 1, "complaint_count": 2, "affected_customers": 100},
    ]

    score_issues(issues)

    assert issues[0]["severity_weight"] == 0
    assert issues[0]["frequency_weight"] == 1
    assert issues[0]["priority_score"] == 100
    assert issues[1]["priority_score"] == 75
