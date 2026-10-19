"""Shared financial-statement page detection and raw-content extraction."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pymupdf


STATEMENT_KEYWORDS = {
    "balance_sheet": {
        "label": "balance sheet",
        "titles": [
            "consolidated balance sheets",
            "consolidated balance sheet",
            "balance sheets",
            "balance sheet",
            "statement of financial position",
            "statements of financial position",
        ],
        "positive": [
            "total assets",
            "total liabilities",
            "total current assets",
            "total current liabilities",
            "stockholders' equity",
            "shareholders' equity",
            "cash and cash equivalents",
            "accounts receivable",
            "inventories",
            "property and equipment",
            "goodwill",
            "accounts payable",
            "long-term debt",
            "retained earnings",
        ],
        "negative": [
            "cash flows from operating",
            "cash flows from investing",
            "cash flows from financing",
            "income from operations",
            "cost of revenue",
            "gross profit",
            "operating expenses",
            "earnings per share",
            "revenue recognition",
        ],
    },
    "income_statement": {
        "label": "income statement",
        "titles": [
            "consolidated statements of operations",
            "consolidated statement of operations",
            "consolidated statements of income",
            "consolidated statement of income",
            "statements of operations",
            "statement of operations",
            "statements of income",
            "statement of income",
            "consolidated statements of earnings",
            "statements of comprehensive income",
        ],
        "positive": [
            "total revenue",
            "net sales",
            "net revenue",
            "cost of revenue",
            "cost of goods sold",
            "cost of sales",
            "gross profit",
            "operating income",
            "operating expenses",
            "research and development",
            "selling, general and administrative",
            "income before income tax",
            "income before income taxes",
            "income tax expense",
            "net income",
            "net loss",
            "earnings per share",
            "weighted average shares",
            "interest expense",
            "other income",
        ],
        "negative": [
            "cash flows from operating",
            "cash flows from investing",
            "cash flows from financing",
            "total assets",
            "total liabilities",
            "stockholders' equity",
            "shareholders' equity",
            "balance sheet",
            "significant accounting policies",
            "revenue recognition",
        ],
    },
    "cash_flow": {
        "label": "cash flow statement",
        "titles": [
            "consolidated statements of cash flows",
            "consolidated statement of cash flows",
            "statements of cash flows",
            "statement of cash flows",
        ],
        "positive": [
            "cash flows from operating activities",
            "cash flows from investing activities",
            "cash flows from financing activities",
            "net cash provided by operating",
            "net cash used in operating",
            "net cash provided by investing",
            "net cash used in investing",
            "net cash provided by financing",
            "net cash used in financing",
            "depreciation and amortization",
            "stock-based compensation",
            "deferred income taxes",
            "capital expenditures",
            "purchases of property and equipment",
            "purchases of property, plant and equipment",
            "repayments of long-term debt",
            "repurchases of common stock",
            "dividends paid",
            "cash at beginning of period",
            "cash at end of period",
            "cash and cash equivalents at beginning of period",
            "cash and cash equivalents at end of period",
            "supplemental disclosures of cash flow information",
            "cash paid for income taxes",
            "cash paid for interest",
        ],
        "negative": [
            "total assets",
            "total liabilities",
            "stockholders' equity",
            "shareholders' equity",
            "balance sheet",
            "earnings per share",
            "cost of revenue",
            "gross profit",
            "significant accounting policies",
            "revenue recognition",
        ],
    },
}

TITLE_WEIGHT = 10
KEYWORD_WEIGHT = 2
NEGATIVE_WEIGHT = -3
DATE_PATTERN = re.compile(
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
    r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?)\.?\s+\d{1,2},?\s+\d{4}\b",
    re.IGNORECASE,
)
NUMBER_PATTERN = re.compile(r"^\(?-?\$?\d[\d,]*(?:\.\d+)?\)?$")
DASHES = {"-", "--", "\u2012", "\u2013", "\u2014", "\u2212"}
Word = tuple[float, float, float, float, str]
PositionedLines = list[list[Word]]


@dataclass
class PageScore:
    page_number: int
    score: int
    title_hits: list[str]
    keyword_hits: list[str]
    negative_hits: list[str]


def score_page(text: str, page_number: int, keywords: dict[str, Any]) -> PageScore:
    """Score one page using its statement title and line-item keywords."""
    text_lower = text.lower()
    title_hits = [phrase for phrase in keywords["titles"] if phrase in text_lower]
    keyword_hits = [phrase for phrase in keywords["positive"] if phrase in text_lower]
    negative_hits = [phrase for phrase in keywords["negative"] if phrase in text_lower]
    score = (
        len(title_hits) * TITLE_WEIGHT
        + len(keyword_hits) * KEYWORD_WEIGHT
        + len(negative_hits) * NEGATIVE_WEIGHT
    )
    return PageScore(page_number, score, title_hits, keyword_hits, negative_hits)


def find_statement_page(
    document: pymupdf.Document, statement: str
) -> tuple[PageScore, pymupdf.Page]:
    """Return the highest-scoring page for a statement or raise if none is found."""
    keywords = STATEMENT_KEYWORDS[statement]
    best: PageScore | None = None
    best_page: pymupdf.Page | None = None
    for page_number, page in enumerate(document, start=1):
        current = score_page(page.get_text(), page_number, keywords)
        if best is None or current.score > best.score:
            best = current
            best_page = page
    if best is None or best.score <= 0 or best_page is None:
        raise ValueError(f"No {keywords['label']} page detected.")
    return best, best_page


def positioned_lines(page: pymupdf.Page) -> PositionedLines:
    """Group positioned PDF words into visual lines."""
    words = page.get_text("words", sort=True)
    ordered_words: list[Word] = sorted(
        (
            (word[0], word[1], word[2], word[3], word[4])
            for word in words
        ),
        key=lambda word: ((word[1] + word[3]) / 2, word[0]),
    )
    lines: PositionedLines = []
    centers: list[float] = []
    for word in ordered_words:
        center = (word[1] + word[3]) / 2
        if not lines or center - centers[-1] > 6.5:
            lines.append([])
            centers.append(center)
        lines[-1].append(word)
        centers[-1] = sum((item[1] + item[3]) / 2 for item in lines[-1]) / len(
            lines[-1]
        )
    for line in lines:
        line.sort(key=lambda word: word[0])
    return lines


def period_headers(lines: PositionedLines, page_height: float) -> list[dict[str, Any]]:
    """Read full dates or aligned years from the upper part of a statement page."""
    headers: list[dict[str, Any]] = []
    duration_headings: list[dict[str, Any]] = []
    date_fragments: list[tuple[str, float]] = []
    year_words: list[tuple[str, Word]] = []
    year_header_candidates: list[list[dict[str, Any]]] = []
    for line in lines:
        y = min(word[1] for word in line)
        if y > page_height * 0.25:
            continue
        text = " ".join(word[4] for word in line)
        offsets: list[tuple[int, int, Word]] = []
        cursor = 0
        for word in line:
            start = text.find(word[4], cursor)
            offsets.append((start, start + len(word[4]), word))
            cursor = start + len(word[4])

        duration_pattern = re.compile(
            r"\b((?:three|six|nine|twelve)\s+months\s+ended|quarters?\s+ended)\b",
            re.IGNORECASE,
        )
        for duration_match in duration_pattern.finditer(text):
            matching_words = [
                word
                for start, end, word in offsets
                if start < duration_match.end() and end > duration_match.start()
            ]
            if not matching_words:
                continue
            duration_headings.append(
                {
                    "label": " ".join(duration_match.group(1).split()),
                    "center": (
                        min(word[0] for word in matching_words)
                        + max(word[2] for word in matching_words)
                    )
                    / 2,
                    "y": y,
                }
            )
        fragment = re.search(
            r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
            r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|"
            r"Nov(?:ember)?|Dec(?:ember)?)\.?\s+\d{1,2},?\s*$",
            text,
            re.IGNORECASE,
        )
        if fragment:
            date_fragments.append((fragment.group(0).strip(), y))
        line_years = [
            word
            for word in line
            if re.fullmatch(r"(?:19|20)\d{2}", word[4])
        ]
        year_words.extend((word[4], word) for word in line_years)
        if len(line_years) >= 2:
            year_header_candidates.append(
                [
                    {
                        "period": word[4],
                        "center": (word[0] + word[2]) / 2,
                        "y": word[3],
                    }
                    for word in line_years
                ]
            )

        for match in DATE_PATTERN.finditer(text):
            matched_words = [
                word
                for start, end, word in offsets
                if start < match.end() and end > match.start()
            ]
            if matched_words:
                headers.append(
                    {
                        "period": " ".join(match.group(0).split()),
                        "center": (
                            min(word[0] for word in matched_words)
                            + max(word[2] for word in matched_words)
                        )
                        / 2,
                        "y": max(word[3] for word in matched_words),
                    }
                )

    def apply_duration_labels(
        period_headers: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        for header in period_headers:
            applicable_headings = [
                heading
                for heading in duration_headings
                if 0 < header["y"] - heading["y"] <= 35
            ]
            if applicable_headings:
                heading = min(
                    applicable_headings,
                    key=lambda candidate: abs(candidate["center"] - header["center"]),
                )
                header["period"] = f"{heading['label']}: {header['period']}"
        return sorted(period_headers, key=lambda header: header["center"])

    if headers:
        return apply_duration_labels(headers)
    if year_header_candidates:
        return apply_duration_labels(year_header_candidates[-1])

    if len(date_fragments) == 1:
        fragment, fragment_y = date_fragments[0]
        adjacent_years = [
            (year, word)
            for year, word in year_words
            if 0 < word[1] - fragment_y < 30
        ]
        if len(adjacent_years) >= 2:
            for year, word in adjacent_years:
                headers.append(
                    {
                        "period": f"{fragment} {year}",
                        "center": (word[0] + word[2]) / 2,
                        "y": word[3],
                    }
                )
    return sorted(headers, key=lambda header: header["center"])


def parse_amount(
    token: str, replacement_dash_present: bool
) -> tuple[int | float | None, str, str]:
    """Parse a statement amount, treating printed dashes as zero."""
    token = token.strip().replace("\u00a0", "")
    if token in DASHES or (token == "\ufffdX" and replacement_dash_present):
        return 0, "\u2014", "dash_as_zero"
    if NUMBER_PATTERN.fullmatch(token):
        negative = token.startswith("(") and token.endswith(")")
        numeric = token.strip("()").replace("$", "").replace(",", "")
        value: int | float = float(numeric) if "." in numeric else int(numeric)
        return (-value if negative else value), token, "parsed"
    return None, token, "unrecognized"


def parse_rows(
    page: pymupdf.Page,
    lines: PositionedLines,
    headers: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Assign amounts to each date column and collect any extraction issues."""
    periods = [header["period"] for header in headers]
    if not periods:
        raise ValueError("No statement date columns were found.")
    boundaries = [
        (headers[index]["center"] + headers[index + 1]["center"]) / 2
        for index in range(len(headers) - 1)
    ]
    label_boundary = headers[0]["center"] - 10
    replacement_dash_present = "\u2014" in page.get_text()
    line_centers = [
        sum((word[1] + word[3]) / 2 for word in line) / len(line)
        for line in lines
    ]
    header_y = max(header["y"] for header in headers)
    rows: list[dict[str, Any]] = []
    issues: list[str] = []

    for index, line in enumerate(lines):
        line_y = line_centers[index]
        if line_y <= header_y:
            continue
        if (
            line_y > page.rect.height * 0.9
            and len(line) == 1
            and line[0][4].isdigit()
        ):
            continue
        columns: list[list[str]] = [[] for _ in periods]
        label_words: list[Word] = []
        for word in line:
            x0, _, x1, _, token = word
            if token in {"$", "\u00a3", "\u20ac"}:
                continue
            center_x = (x0 + x1) / 2
            if center_x < label_boundary:
                label_words.append(word)
                continue
            column_index = next(
                (
                    column_index
                    for column_index, boundary in enumerate(boundaries)
                    if center_x < boundary
                ),
                len(periods) - 1,
            )
            columns[column_index].append(token)
        if not any(columns):
            continue

        label = " ".join(word[4] for word in label_words).strip()
        if not label:
            issues.append(f"Found amounts without a line-item label near y={line_y:.1f}.")
            continue
        if label.casefold().startswith("see accompanying notes"):
            continue

        continuations: list[str] = []
        for previous_index in range(index - 1, max(-1, index - 4), -1):
            previous = lines[previous_index]
            previous_y = line_centers[previous_index]
            previous_label_words = [
                word for word in previous if (word[0] + word[2]) / 2 < label_boundary
            ]
            previous_label = " ".join(word[4] for word in previous_label_words).strip()
            if (
                not previous_label
                or previous_label.endswith(":")
                or any(
                    (word[0] + word[2]) / 2 >= label_boundary for word in previous
                )
                or not 0 < line_y - previous_y <= 15
                or abs(previous_label_words[0][0] - label_words[0][0]) > 5
            ):
                break
            continuations.insert(0, previous_label)
        if continuations:
            label = " ".join([*continuations, label])

        values: dict[str, int | float | None] = {}
        for period, tokens in zip(periods, columns):
            if not tokens:
                values[period] = None
                continue
            if len(tokens) != 1:
                issues.append(
                    f"{label}: expected one amount for {period}, found {tokens}."
                )
                values[period] = None
                continue
            value, raw_value, status = parse_amount(
                tokens[0], replacement_dash_present
            )
            values[period] = value
            if status == "unrecognized":
                issues.append(f"{label}, {period}: cannot parse amount {raw_value!r}.")
        rows.append({"label": label, "values": values})
    return rows, issues


def extract_statement(
    pdf_path: str | Path, statement: str
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str], list[str]]:
    """Extract statement metadata and raw rows from a PDF."""
    if statement not in STATEMENT_KEYWORDS:
        choices = ", ".join(STATEMENT_KEYWORDS)
        raise ValueError(f"Unknown statement {statement!r}. Choose from: {choices}.")
    pdf_path = Path(pdf_path)
    with pymupdf.open(pdf_path) as document:
        score, page = find_statement_page(document, statement)
        lines = positioned_lines(page)
        headers = period_headers(lines, page.rect.height)
        rows, issues = parse_rows(page, lines, headers)
        unit_match = re.search(r"\(\s*in\s+[^)]*\)", page.get_text(), re.IGNORECASE)
        unit = unit_match.group(0).strip("() ") if unit_match else "statement units"
        result = {
            "pdf": str(pdf_path),
            "statement": statement,
            "page_number": score.page_number,
            "unit": unit,
        }
        return result, rows, [header["period"] for header in headers], issues
