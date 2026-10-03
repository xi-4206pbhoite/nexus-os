"""CSV, the fifth accepted type (Q37).

`doc/11` stage 5 lists PDF, DOCX, PPTX, XLSX **and CSV**. CSV matters more than
its place on that list suggests: it is what an SME's accounting package and CRM
export, so it is the most likely shape for the numbers a founder actually wants
NEXUS to read.

**Not `_parse_txt` with a different extension.** A CSV decoded as plain text
gives one page of comma soup, and a chunk of comma soup retrieves badly and
cites worse — a citation has to point somewhere a human can look. Rows are
rendered so a column keeps its header next to its value, which is what makes a
retrieved row mean anything on its own.

Two encodings are load-bearing rather than pedantic. Excel on Windows writes
CSVs with a **UTF-8 BOM**, and an unstripped BOM corrupts the first header —
the first column of every export from the most common tool in the market.
"""

from __future__ import annotations

from app.documents.parse import DocumentKind, ParseOutcome, kind_for_filename, parse_document


def test_a_csv_is_recognised_by_its_extension() -> None:
    assert kind_for_filename("export.csv") is DocumentKind.CSV
    assert kind_for_filename("EXPORT.CSV") is DocumentKind.CSV


def test_a_row_keeps_its_headers_beside_its_values() -> None:
    """The property the whole parser exists for.

    A retrieved chunk is shown to a founder and cited. `Muscat Trading, 4500`
    is not an answer to anything; `Customer: Muscat Trading | Amount: 4500` is
    a fact that survives being read on its own.
    """
    parsed = parse_document(
        b"Customer,Amount,Due\nMuscat Trading,4500,2026-03-01\n", filename="ar.csv"
    )

    assert parsed.outcome is ParseOutcome.OK
    text = parsed.pages[0].text
    assert "Customer: Muscat Trading" in text
    assert "Amount: 4500" in text
    assert "Due: 2026-03-01" in text


def test_a_utf8_bom_does_not_corrupt_the_first_header() -> None:
    """Excel on Windows writes this. Unstripped, it makes the first column of
    every such export unretrievable — and the failure is silent, because the
    file parses fine and only the header is wrong."""
    parsed = parse_document("﻿Customer,Amount\nMuscat Trading,4500\n".encode(), filename="excel.csv")

    assert "Customer: Muscat Trading" in parsed.pages[0].text
    assert "﻿" not in parsed.pages[0].text


def test_a_semicolon_delimited_export_is_read_as_columns() -> None:
    """The European/Gulf Excel default. Read as commas it is one column whose
    name contains every header, which parses without error and retrieves
    nothing — the worst kind of failure this codebase has a rule about."""
    parsed = parse_document(b"Customer;Amount\nMuscat Trading;4500\n", filename="eu.csv")

    assert "Customer: Muscat Trading" in parsed.pages[0].text
    assert "Amount: 4500" in parsed.pages[0].text


def test_a_headerless_csv_still_parses() -> None:
    """Not every export has a header row, and refusing one would be the product
    being fussier than the customer's tooling."""
    parsed = parse_document(b"4500\n2300\n", filename="numbers.csv")
    assert parsed.outcome is ParseOutcome.OK
    assert "4500" in parsed.pages[0].text


def test_an_empty_csv_reports_empty_rather_than_ok() -> None:
    parsed = parse_document(b"Customer,Amount\n", filename="headers-only.csv")
    assert parsed.outcome is ParseOutcome.EMPTY


def test_a_long_csv_is_split_into_pages_that_can_be_cited() -> None:
    """One page of ten thousand rows cites as "page 1", which tells a founder
    checking a number nothing at all. Pages are what a citation points at."""
    rows = b"Customer,Amount\n" + b"".join(f"Row {i},{i}\n".encode() for i in range(2000))
    parsed = parse_document(rows, filename="big.csv")

    assert parsed.outcome is ParseOutcome.OK
    assert len(parsed.pages) > 1, "a long export must be citable at finer than whole-file"
    assert all(p.label for p in parsed.pages), "every page needs a label a human can follow"


def test_a_csv_that_is_not_text_fails_visibly() -> None:
    """Bytes that cannot be decoded are a failure with a reason, never a silent
    pass — the rule the parse outcomes already follow."""
    parsed = parse_document(b"\x00\x01\x02\x03" * 100, filename="binary.csv")
    assert parsed.outcome in {ParseOutcome.CORRUPT, ParseOutcome.EMPTY}
    assert parsed.message
