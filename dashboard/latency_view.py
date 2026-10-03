from collections.abc import Mapping

import pandas as pd


PAGE_COLUMNS = (
    ("latency_s", "Home"),
    ("latency_product_s", "Product"),
    ("latency_cart_s", "Cart"),
)
PAGE_NAMES = tuple(page_name for _, page_name in PAGE_COLUMNS)
FRAME_COLUMNS = (
    "Page",
    "Before (seconds)",
    "During (seconds)",
    "Change (seconds)",
    "Failed requests during",
    "Failed requests after",
)


def build_page_latency_frame(
    latency_report: Mapping[str, Mapping[str, float | int | None]],
) -> pd.DataFrame:
    rows = []
    for column, page_name in PAGE_COLUMNS:
        values = latency_report.get(column)
        if values is None:
            continue
        rows.append(
            {
                "Page": page_name,
                "Before (seconds)": values["before_seconds"],
                "During (seconds)": values["during_seconds"],
                "Change (seconds)": values["increase_seconds"],
                "Failed requests during": values["timeouts"],
                "Failed requests after": values["timeouts_after_fault"],
            }
        )
    return pd.DataFrame(rows, columns=FRAME_COLUMNS)


def find_largest_slowdown(page_frame: pd.DataFrame) -> tuple[str, float] | None:
    increases = page_frame.loc[
        page_frame["Change (seconds)"].notna()
        & (page_frame["Change (seconds)"] > 0)
    ]
    if increases.empty:
        return None
    largest = max(
        increases.to_dict("records"),
        key=lambda row: row["Change (seconds)"],
    )
    return str(largest["Page"]), float(largest["Change (seconds)"])


def find_unavailable_pages(page_frame: pd.DataFrame) -> list[str]:
    comparable_pages = set(
        page_frame.loc[
            page_frame["Before (seconds)"].notna()
            & page_frame["During (seconds)"].notna(),
            "Page",
        ]
    )
    return [page for page in PAGE_NAMES if page not in comparable_pages]
