from app.guardrails import REFUSAL, check_answer

PASSAGES = [
    {"source_file": "employee_handbook.pdf", "page_number": 1, "section": "Leave", "text": "..."},
    {"source_file": "incident_runbook.pdf", "page_number": 2, "section": "On-call", "text": "..."},
]


def test_valid_citation_kept():
    r = check_answer("Employees get 24 days of paid leave [employee_handbook.pdf, p. 1].", PASSAGES)
    assert not r.refused
    assert r.citations == [{"source_file": "employee_handbook.pdf", "page_number": 1}]
    assert r.invalid_citations == []


def test_wrong_page_is_stripped_but_valid_one_kept():
    raw = "24 days [employee_handbook.pdf, p. 1]. Bridge room is X [incident_runbook.pdf, p. 9]."
    r = check_answer(raw, PASSAGES)
    assert not r.refused
    assert "[incident_runbook.pdf, p. 9]" not in r.answer
    assert r.invalid_citations == ["[incident_runbook.pdf, p. 9]"]


def test_uncited_answer_becomes_refusal():
    r = check_answer("Employees get 24 days of leave.", PASSAGES)
    assert r.refused and r.answer == REFUSAL


def test_citation_to_unretrieved_file_becomes_refusal():
    r = check_answer("Revenue was 48.2 Cr [q3_financials.xlsx, p. 1].", PASSAGES)
    assert r.refused and r.invalid_citations == ["[q3_financials.xlsx, p. 1]"]


def test_model_refusal_and_no_context():
    assert check_answer(REFUSAL, PASSAGES).refused
    assert check_answer("anything [employee_handbook.pdf, p. 1]", []).refused


def test_fullwidth_brackets_and_unicode_hyphens_are_accepted():
    r = check_answer("Brightpath Analytics, a Pune‑based startup【employee_handbook.pdf, p. 1】.", PASSAGES)
    assert not r.refused
    assert r.answer == "Brightpath Analytics, a Pune-based startup [employee_handbook.pdf, p. 1]."
