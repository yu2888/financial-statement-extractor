"""Metric calculations for the supported financial statements."""

import re
from collections.abc import Callable
from datetime import date, datetime
from typing import Any


def normalize_label(label: str) -> str:
    """Normalize labels so common punctuation and Unicode variants match."""
    label = label.replace("\u2019", "'").replace("\ufffd", "'").lower()
    return re.sub(r"[^a-z0-9]+", " ", label).strip()


def _values_by_label(
    rows: list[dict[str, Any]], period: str
) -> dict[str, int | float]:
    values: dict[str, int | float] = {}
    for row in rows:
        value = row["values"].get(period)
        if value is not None:
            values[normalize_label(row["label"])] = value
    return values


def _find_value(
    values: dict[str, int | float],
    *labels: str,
    startswith: bool = False,
) -> int | float | None:
    for label in labels:
        normalized = normalize_label(label)
        if normalized in values:
            return values[normalized]
    if startswith:
        for label, value in values.items():
            if any(label.startswith(normalize_label(prefix)) for prefix in labels):
                return value
    return None


def _find_row_value(
    rows: list[dict[str, Any]],
    period: str,
    *labels: str,
    last_match: bool = False,
) -> int | float | None:
    for label in labels:
        normalized = normalize_label(label)
        matches = [
            row["values"].get(period)
            for row in rows
            if normalize_label(row["label"]) == normalized
            and row["values"].get(period) is not None
        ]
        if matches:
            return matches[-1] if last_match else matches[0]
    return None


def _ratio(
    numerator: int | float | None, denominator: int | float | None
) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _growth(
    current: int | float | None, previous: int | float | None
) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return (current - previous) / abs(previous)


def _period_year(period: str) -> int:
    year_match = re.search(r"\b(?:19|20)\d{2}\b", period)
    if year_match is None:
        raise ValueError(f"Could not determine year from statement period {period!r}.")
    return int(year_match.group(0))


def _period_group(period: str) -> str:
    if ": " not in period:
        return ""
    return period.split(": ", maxsplit=1)[0].casefold()


def _growth_series(
    periods: list[str],
    values: dict[str, int | float | None],
) -> dict[str, float | None]:
    grouped_periods: dict[str, list[str]] = {}
    for period in periods:
        grouped_periods.setdefault(_period_group(period), []).append(period)

    growth: dict[str, float | None] = {}
    for group_periods in grouped_periods.values():
        chronological_periods = sorted(group_periods, key=_period_year)
        for index, period in enumerate(chronological_periods):
            previous = values[chronological_periods[index - 1]] if index else None
            growth[period] = _growth(values[period], previous)
    return growth


def _metric_output(
    periods: list[str],
    series: dict[str, dict[str, int | float | None]],
    formulas: dict[str, str],
    units: dict[str, str],
) -> dict[str, dict[str, Any]]:
    period_years: dict[str, str] = {}
    year_counts: dict[str, int] = {}
    for period in periods:
        year = str(_period_year(period))
        period_years[period] = year
        year_counts[year] = year_counts.get(year, 0) + 1

    return {
        name: {
            "unit": units[name],
            "formula": formulas[name],
            **{
                (
                    period
                    if year_counts[period_years[period]] > 1
                    else period_years[period]
                ): values.get(period)
                for period in periods
            },
        }
        for name, values in series.items()
    }


def calculate_balance_sheet_metrics(
    rows: list[dict[str, Any]], periods: list[str], amount_unit: str
) -> dict[str, dict[str, Any]]:
    series: dict[str, dict[str, int | float | None]] = {}
    for period in periods:
        values = _values_by_label(rows, period)
        cash = _find_value(values, "cash and cash equivalents")
        marketable_securities = _find_value(values, "marketable securities")
        receivables = _find_value(values, "accounts receivable", startswith=True)
        inventory = _find_value(values, "inventories", "inventory")
        current_assets = _find_value(values, "total current assets")
        current_liabilities = _find_value(values, "total current liabilities")
        total_assets = _find_value(values, "total assets")
        total_liabilities = _find_value(values, "total liabilities")
        if total_liabilities is None:
            combined_liabilities_equity = _find_value(
                values,
                "total liabilities and shareholders equity",
                "total liabilities and stockholders equity",
            )
            combined_equity = _find_value(
                values, "total stockholders equity", "total shareholders equity"
            )
            if combined_liabilities_equity is not None and combined_equity is not None:
                total_liabilities = combined_liabilities_equity - combined_equity
        equity = _find_value(
            values, "total shareholders equity", "total stockholders equity"
        )
        long_term_debt = _find_value(values, "long-term debt", "long term debt")
        current_debt = _find_value(
            values,
            "short-term debt",
            "short term debt",
            "current portion of long-term debt",
            "current portion of long term debt",
        )
        debt = (
            long_term_debt + (current_debt if current_debt is not None else 0)
            if long_term_debt is not None
            else None
        )
        quick_assets = (
            cash + marketable_securities + receivables
            if cash is not None
            and marketable_securities is not None
            and receivables is not None
            else None
        )
        cash_assets = (
            cash + marketable_securities
            if cash is not None and marketable_securities is not None
            else None
        )

        series.setdefault("working_capital", {})[period] = (
            current_assets - current_liabilities
            if current_assets is not None and current_liabilities is not None
            else None
        )
        series.setdefault("current_ratio", {})[period] = _ratio(
            current_assets, current_liabilities
        )
        series.setdefault("quick_ratio", {})[period] = _ratio(
            quick_assets, current_liabilities
        )
        series.setdefault("cash_ratio", {})[period] = _ratio(
            cash_assets, current_liabilities
        )
        series.setdefault("total_debt", {})[period] = debt
        series.setdefault("net_debt", {})[period] = (
            debt - cash if debt is not None and cash is not None else None
        )
        series.setdefault("debt_to_equity", {})[period] = _ratio(debt, equity)
        series.setdefault("liabilities_to_assets", {})[period] = _ratio(
            total_liabilities, total_assets
        )
        series.setdefault("equity_to_assets", {})[period] = _ratio(equity, total_assets)
        series.setdefault("cash_to_assets", {})[period] = _ratio(cash, total_assets)
        series.setdefault("receivables_to_assets", {})[period] = _ratio(
            receivables, total_assets
        )
        series.setdefault("inventory_to_assets", {})[period] = _ratio(
            inventory, total_assets
        )

    formulas = {
        "working_capital": "total current assets - total current liabilities",
        "current_ratio": "total current assets / total current liabilities",
        "quick_ratio": "(cash + marketable securities + accounts receivable) / total current liabilities",
        "cash_ratio": "(cash + marketable securities) / total current liabilities",
        "total_debt": "short-term debt + long-term debt",
        "net_debt": "total debt - cash and cash equivalents",
        "debt_to_equity": "total debt / total shareholders' or stockholders' equity",
        "liabilities_to_assets": "total liabilities / total assets",
        "equity_to_assets": "total shareholders' or stockholders' equity / total assets",
        "cash_to_assets": "cash and cash equivalents / total assets",
        "receivables_to_assets": "accounts receivable / total assets",
        "inventory_to_assets": "inventory / total assets",
    }
    ratio_names = {
        "current_ratio",
        "quick_ratio",
        "cash_ratio",
        "debt_to_equity",
        "liabilities_to_assets",
        "equity_to_assets",
        "cash_to_assets",
        "receivables_to_assets",
        "inventory_to_assets",
    }
    units = {
        name: "x" if name in ratio_names else amount_unit
        for name in formulas
    }
    return _metric_output(periods, series, formulas, units)


def calculate_income_statement_metrics(
    rows: list[dict[str, Any]], periods: list[str], amount_unit: str
) -> dict[str, dict[str, Any]]:
    inputs: dict[str, dict[str, int | float | None]] = {}
    for period in periods:
        values = _values_by_label(rows, period)
        revenue = _find_value(
            values,
            "revenue",
            "total revenue",
            "net revenue",
            "net sales",
            "total net sales",
        )
        cost = _find_value(
            values, "cost of revenue", "cost of goods sold", "cost of sales"
        )
        gross_profit = _find_value(values, "gross profit")
        if gross_profit is None and revenue is not None and cost is not None:
            gross_profit = revenue - cost
        operating_income = _find_value(
            values, "operating income", "income from operations"
        )
        pretax_income = _find_value(
            values,
            "income before income tax",
            "income before income taxes",
            "pretax income",
        )
        tax_expense = _find_value(
            values,
            "income tax expense",
            "income tax expense (benefit)",
            "provision for income taxes",
            "tax provision",
            startswith=True,
        )
        net_income = _find_value(values, "net income", "net earnings")
        basic_eps = _find_row_value(
            rows, period, "basic earnings per share", "basic eps", "basic"
        )
        diluted_eps = _find_row_value(
            rows, period, "diluted earnings per share", "diluted eps", "diluted"
        )
        basic_shares = _find_row_value(
            rows,
            period,
            "weighted average basic shares",
            "weighted average shares basic",
            "weighted average shares used in computation basic",
            "basic",
            last_match=True,
        )
        diluted_shares = _find_row_value(
            rows,
            period,
            "weighted average diluted shares",
            "weighted average shares diluted",
            "weighted average shares used in computation diluted",
            "diluted",
            last_match=True,
        )
        research = _find_value(
            values,
            "research and development",
            "research development",
            startswith=True,
        )
        sga = _find_value(
            values,
            "selling general and administrative",
            "selling general administrative",
            "selling general and administrative expenses",
            "sales general and administrative",
            "sales general administrative",
            startswith=True,
        )
        inputs[period] = {
            "revenue": revenue,
            "gross_profit": gross_profit,
            "operating_income": operating_income,
            "pretax_income": pretax_income,
            "income_tax_expense": tax_expense,
            "net_income": net_income,
            "basic_eps": basic_eps,
            "diluted_eps": diluted_eps,
            "basic_shares": basic_shares,
            "diluted_shares": diluted_shares,
            "research_and_development": research,
            "selling_general_and_administrative": sga,
        }

    def direct(name: str) -> dict[str, int | float | None]:
        return {period: values[name] for period, values in inputs.items()}

    series: dict[str, dict[str, int | float | None]] = {
        name: direct(name)
        for name in (
            "revenue",
            "gross_profit",
            "operating_income",
            "pretax_income",
            "income_tax_expense",
            "net_income",
            "basic_eps",
            "diluted_eps",
            "basic_shares",
            "diluted_shares",
        )
    }
    for metric, numerator in (
        ("gross_margin", "gross_profit"),
        ("operating_margin", "operating_income"),
        ("pretax_margin", "pretax_income"),
        ("net_margin", "net_income"),
        ("research_and_development_to_revenue", "research_and_development"),
        (
            "selling_general_and_administrative_to_revenue",
            "selling_general_and_administrative",
        ),
    ):
        series[metric] = {
            period: _ratio(values[numerator], values["revenue"])
            for period, values in inputs.items()
        }
    series["effective_tax_rate"] = {
        period: _ratio(values["income_tax_expense"], values["pretax_income"])
        for period, values in inputs.items()
    }
    series["dilution_rate"] = {
        period: (
            (values["diluted_shares"] / values["basic_shares"]) - 1
            if values["diluted_shares"] is not None
            and values["basic_shares"] not in (None, 0)
            else None
        )
        for period, values in inputs.items()
    }

    for metric, source in (
        ("revenue_growth", "revenue"),
        ("net_income_growth", "net_income"),
        ("basic_eps_growth", "basic_eps"),
        ("diluted_eps_growth", "diluted_eps"),
    ):
        series[metric] = _growth_series(
            periods,
            {period: values[source] for period, values in inputs.items()},
        )

    formulas = {
        "revenue": "reported revenue or net sales",
        "revenue_growth": "(current revenue - prior revenue) / abs(prior revenue)",
        "gross_profit": "reported gross profit, or revenue - cost of revenue",
        "gross_margin": "gross profit / revenue",
        "operating_income": "reported operating income",
        "operating_margin": "operating income / revenue",
        "pretax_income": "reported income before income tax",
        "pretax_margin": "income before income tax / revenue",
        "income_tax_expense": "reported income tax expense or provision",
        "effective_tax_rate": "income tax expense / income before income tax",
        "net_income": "reported net income",
        "net_margin": "net income / revenue",
        "net_income_growth": "(current net income - prior net income) / abs(prior net income)",
        "basic_eps": "reported basic earnings per share",
        "basic_eps_growth": "(current basic EPS - prior basic EPS) / abs(prior basic EPS)",
        "diluted_eps": "reported diluted earnings per share",
        "diluted_eps_growth": "(current diluted EPS - prior diluted EPS) / abs(prior diluted EPS)",
        "basic_shares": "reported weighted-average basic shares",
        "diluted_shares": "reported weighted-average diluted shares",
        "dilution_rate": "(diluted shares / basic shares) - 1",
        "research_and_development_to_revenue": "research and development / revenue",
        "selling_general_and_administrative_to_revenue": "selling, general and administrative / revenue",
    }
    ratio_names = {
        "gross_margin",
        "operating_margin",
        "pretax_margin",
        "net_margin",
        "effective_tax_rate",
        "dilution_rate",
        "research_and_development_to_revenue",
        "selling_general_and_administrative_to_revenue",
    }
    percent_names = {
        "revenue_growth",
        "net_income_growth",
        "basic_eps_growth",
        "diluted_eps_growth",
    }
    units = {
        name: (
            "x"
            if name in ratio_names
            else "%"
            if name in percent_names
            else "per share"
            if name in {"basic_eps", "diluted_eps"}
            else "shares"
            if name in {"basic_shares", "diluted_shares"}
            else amount_unit
        )
        for name in formulas
    }
    return _metric_output(periods, series, formulas, units)


def calculate_roic(
    income_rows: list[dict[str, Any]],
    income_periods: list[str],
    balance_rows: list[dict[str, Any]],
    balance_periods: list[str],
) -> dict[str, dict[str, Any]]:
    """Calculate ROIC using effective tax rate and average debt-plus-equity less cash."""
    date_pattern = re.compile(
        r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
        r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|"
        r"Nov(?:ember)?|Dec(?:ember)?)\.?\s+\d{1,2},?\s+\d{4}\b",
        re.IGNORECASE,
    )

    def period_date(period: str) -> date | None:
        match = date_pattern.search(period)
        if match is None:
            return None
        normalized_date = " ".join(match.group(0).replace(",", "").split())
        for date_format in ("%b %d %Y", "%B %d %Y"):
            try:
                return datetime.strptime(normalized_date, date_format).date()
            except ValueError:
                continue
        return None

    balance_capital: list[tuple[date, int | float | None]] = []
    for period in balance_periods:
        balance_date = period_date(period)
        if balance_date is None:
            continue
        values = _values_by_label(balance_rows, period)
        cash = _find_value(
            values, "cash and cash equivalents", "cash cash equivalents"
        )
        equity = _find_value(
            values,
            "total shareholders equity",
            "total stockholders equity",
            "total equity",
        )

        debt_labels = {
            "short term debt",
            "current portion of long term debt",
            "current portion of debt",
            "long term debt",
            "long term borrowings",
        }
        reported_debt_values = [
            row["values"].get(period)
            for row in balance_rows
            if normalize_label(row["label"]) in debt_labels
            and row["values"].get(period) is not None
        ]
        debt = sum(reported_debt_values) if reported_debt_values else None
        invested_capital = (
            debt + equity - cash
            if debt is not None and equity is not None and cash is not None
            else None
        )
        balance_capital.append((balance_date, invested_capital))
    balance_capital.sort(key=lambda item: item[0])

    roic_values: dict[str, int | float | None] = {}
    for period in income_periods:
        year_match = re.search(r"\b(?:19|20)\d{2}\b", period)
        if year_match is None:
            raise ValueError(f"Could not determine year from income period {period!r}.")
        income_date = period_date(period)
        current_capital: int | float | None = None
        previous_capital: int | float | None = None
        if income_date is not None:
            current_index = next(
                (
                    index
                    for index, (balance_date, _) in enumerate(balance_capital)
                    if balance_date == income_date
                ),
                None,
            )
            if current_index is not None:
                current_capital = balance_capital[current_index][1]
                previous_capital = next(
                    (
                        capital
                        for balance_date, capital in reversed(
                            balance_capital[:current_index]
                        )
                        if balance_date < income_date
                    ),
                    None,
                )
        income_values = _values_by_label(income_rows, period)
        operating_income = _find_value(
            income_values, "operating income", "income from operations"
        )
        pretax_income = _find_value(
            income_values,
            "income before income tax",
            "income before income taxes",
            "pretax income",
        )
        tax_expense = _find_value(
            income_values,
            "income tax expense",
            "income tax expense benefit",
            "provision for income taxes",
            "tax provision",
            startswith=True,
        )
        effective_tax_rate = _ratio(tax_expense, pretax_income)
        nopat = (
            operating_income * (1 - effective_tax_rate)
            if operating_income is not None and effective_tax_rate is not None
            else None
        )
        average_invested_capital = (
            (current_capital + previous_capital) / 2
            if current_capital is not None and previous_capital is not None
            else None
        )
        roic_values[period] = _ratio(nopat, average_invested_capital)

    return _metric_output(
        income_periods,
        {"roic": roic_values},
        {
            "roic": (
                "NOPAT / average invested capital; "
                "NOPAT = operating income * (1 - effective tax rate); "
                "invested capital = interest-bearing debt + equity - cash"
            )
        },
        {"roic": "%"},
    )


def calculate_cash_flow_metrics(
    rows: list[dict[str, Any]], periods: list[str], amount_unit: str
) -> dict[str, dict[str, Any]]:
    inputs: dict[str, dict[str, int | float | None]] = {}
    for period in periods:
        values = _values_by_label(rows, period)
        operating = _find_value(
            values,
            "net cash provided by operating",
            "net cash provided by (used in) operating",
            "net cash used in operating",
            "net cash from operating",
            startswith=True,
        )
        investing = _find_value(
            values,
            "net cash provided by investing",
            "net cash provided by (used in) investing",
            "net cash used in investing",
            "net cash from investing",
            startswith=True,
        )
        financing = _find_value(
            values,
            "net cash provided by financing",
            "net cash provided by (used in) financing",
            "net cash used in financing",
            "net cash from financing",
            startswith=True,
        )
        capex_values = [
            value
            for label, value in values.items()
            if label.startswith(
                (
                    "purchases of property",
                    "purchases related to property",
                    "capital expenditures",
                    "payments to acquire property",
                )
            )
        ]
        capex = sum(capex_values) if capex_values else None
        net_income = _find_value(values, "net income", "net earnings")
        beginning_cash = _find_value(
            values,
            "cash and cash equivalents at beginning of period",
            "cash at beginning of period",
            "cash cash equivalents and restricted cash beginning of period",
        )
        ending_cash = _find_value(
            values,
            "cash and cash equivalents at end of period",
            "cash at end of period",
            "cash cash equivalents and restricted cash end of period",
        )
        inputs[period] = {
            "operating_cash_flow": operating,
            "investing_cash_flow": investing,
            "financing_cash_flow": financing,
            "capital_expenditure_cash_flow": capex,
            "free_cash_flow": (
                operating + capex if operating is not None and capex is not None else None
            ),
            "net_income": net_income,
            "beginning_cash": beginning_cash,
            "ending_cash": ending_cash,
        }

    series: dict[str, dict[str, int | float | None]] = {
        name: {period: values[name] for period, values in inputs.items()}
        for name in (
            "operating_cash_flow",
            "investing_cash_flow",
            "financing_cash_flow",
            "capital_expenditure_cash_flow",
            "free_cash_flow",
            "beginning_cash",
            "ending_cash",
        )
    }
    series["operating_cash_flow_to_net_income"] = {
        period: _ratio(values["operating_cash_flow"], values["net_income"])
        for period, values in inputs.items()
    }
    for metric, source in (
        ("operating_cash_flow_growth", "operating_cash_flow"),
        ("free_cash_flow_growth", "free_cash_flow"),
    ):
        series[metric] = _growth_series(
            periods,
            {period: values[source] for period, values in inputs.items()},
        )

    formulas = {
        "operating_cash_flow": "reported net cash from operating activities",
        "investing_cash_flow": "reported net cash from investing activities",
        "financing_cash_flow": "reported net cash from financing activities",
        "capital_expenditure_cash_flow": "sum of reported property and equipment purchase cash flows",
        "free_cash_flow": "operating cash flow + reported capital expenditure cash flows",
        "operating_cash_flow_to_net_income": "operating cash flow / net income",
        "operating_cash_flow_growth": "(current - prior operating cash flow) / abs(prior operating cash flow)",
        "free_cash_flow_growth": "(current - prior free cash flow) / abs(prior free cash flow)",
        "beginning_cash": "reported beginning cash and cash equivalents",
        "ending_cash": "reported ending cash and cash equivalents",
    }
    ratio_names = {"operating_cash_flow_to_net_income"}
    growth_names = {"operating_cash_flow_growth", "free_cash_flow_growth"}
    units = {
        name: "x" if name in ratio_names else "%" if name in growth_names else amount_unit
        for name in formulas
    }
    return _metric_output(periods, series, formulas, units)


METRIC_CALCULATORS: dict[
    str, Callable[[list[dict[str, Any]], list[str], str], dict[str, dict[str, Any]]]
] = {
    "balance_sheet": calculate_balance_sheet_metrics,
    "income_statement": calculate_income_statement_metrics,
    "cash_flow": calculate_cash_flow_metrics,
}
