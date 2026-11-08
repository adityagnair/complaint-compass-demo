from backend.services.complaints import parse_csv


def test_csv_accepts_utf8_bom_aliases_and_common_channel_names():
    content = (
        '\ufeffID,Customer ID,Description,Source,Date,Priority,Country,Region\r\n'
        'C-1,U-1,"Paiement débité deux fois",E-mail,2026-10-01,critical,India,Delhi\r\n'
        'C-2,U-2,Refund still pending,website,10/02/2026,low,India,Karnataka\r\n'
    ).encode("utf-8")

    valid, errors = parse_csv(content)

    assert errors == []
    assert [item.complaint_id for _, item in valid] == ["C-1", "C-2"]
    assert valid[0][1].channel == "email"
    assert valid[0][1].severity == 5
    assert valid[0][1].customer.country == "India"
    assert valid[1][1].channel == "web"
    assert valid[1][1].severity == 1


def test_csv_detects_semicolon_delimiters():
    content = "ID;Complaint;Source;Date\nC-1;Refund pending;phone;2026/10/03 11:30:00\n".encode()

    valid, errors = parse_csv(content)

    assert errors == []
    assert len(valid) == 1
    assert valid[0][1].complaint_id == "C-1"
    assert valid[0][1].channel == "voice"


def test_csv_keeps_valid_rows_and_reports_invalid_and_repeated_ids():
    content = (
        "complaint_id,complaint,channel,severity\n"
        "C-1,Payment deducted twice,email,4\n"
        "C-2,Delivery was late,chat,urgent\n"
        "C-1,Second copy,voice,2\n"
        "C-3,Refund pending,web,not-a-severity\n"
    ).encode()

    valid, errors = parse_csv(content)

    assert [item.complaint_id for _, item in valid] == ["C-1", "C-2"]
    assert [error["row"] for error in errors] == ["4", "5"]
    assert "duplicate complaint_id" in errors[0]["error"]
    assert "severity" in errors[1]["error"]


def test_csv_rejects_non_utf8_and_missing_required_columns():
    try:
        parse_csv(b"\xff\xfe")
    except ValueError as error:
        assert "UTF-8" in str(error)
    else:
        raise AssertionError("non-UTF-8 content should fail")

    try:
        parse_csv(b"complaint_id,channel\nC-1,email\n")
    except ValueError as error:
        assert "complaint_text" in str(error)
    else:
        raise AssertionError("a missing complaint text column should fail")
