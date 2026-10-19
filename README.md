# Financial statement extraction

`extract.py` locates the balance sheet, income statement, and cash-flow
statement in a selectable-text 10-K PDF, then extracts financial indicators.
For the bundled NVIDIA 10-K, a metrics run completed in about 0.5 seconds;
runtime varies with the PDF and machine.

Install dependencies:

```powershell
uv add pymupdf
```

Run from this directory:

```powershell
uv run python extract.py nvda-10k.pdf # Metrics for all three statements (default)
uv run python extract.py nvda-10k.pdf --raw # Raw content for all three statements
```

Example metrics output (abbreviated):

```json
{
  "pdf": "nvda-10k.pdf",
  "statements": {
    "balance_sheet": {
      "page_number": 54,
      "metrics": {
        "working_capital": {
          "2025": 62079
        }
      }
    },
    "income_statement": {
      "page_number": 52,
      "metrics": {
        "revenue": {
          "2025": 130497
        },
        "roic": {
          "2025": 1.1339
        }
      }
    },
    "cash_flow": {
      "page_number": 56,
      "metrics": {
        "operating_cash_flow": {
          "2025": 64089
        }
      }
    }
  },
  "execution": {
    "duration_seconds": 0.473
  }
}
```