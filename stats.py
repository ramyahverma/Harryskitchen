import os
import pandas as pd
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXCEL_FILE = os.path.join(BASE_DIR, "orders.xlsx")
EXPENSE_FILE = os.path.join(BASE_DIR, "Expenses.xlsx")
REMIT_FILE = os.path.join(BASE_DIR, "MoneyMatters.xlsx")


def main():
    stats_by_year = stats()
    print(stats_by_year)


def stats():
    # Read Excel files
    df_orders = pd.read_excel(EXCEL_FILE)
    df_exp = pd.read_excel(EXPENSE_FILE)
    df_cash = pd.read_excel(REMIT_FILE)

    # Build three monthly summaries
    rev_df = build_monthly_sum(
        df_orders,
        amt_col="Line Total",
        new_col="total_revenue",
        exclude_cancelled=True,
    )

    exp_df = build_monthly_sum(
        df_exp,
        amt_col="Amount",
        new_col="total_expense",
        exclude_cancelled=False,
    )

    cash_df = build_monthly_sum(
        df_cash,
        amt_col="Cash Amount",
        new_col="total_cash",
        exclude_cancelled=False,
    )

    # Merge them all on Year + Month
    merged = (
        rev_df
        .merge(exp_df, on=["Year", "MonthNum", "Month"], how="outer")
        .merge(cash_df, on=["Year", "MonthNum", "Month"], how="outer")
        .fillna(0)
    )

    # Convert to your stats_by_year structure
    stats_by_year = {}
    merged = merged.sort_values(["Year", "MonthNum"])

    for _, row in merged.iterrows():
        year = int(row["Year"])
        month_label = row["Month"]

        stats_by_year.setdefault(year, []).append({
            "month": month_label,
            "total_revenue": float(row.get("total_revenue", 0.0)),
            "total_expense": float(row.get("total_expense", 0.0)),
            "total_cash": float(row.get("total_cash", 0.0)),
        })

    return stats_by_year


def build_monthly_sum(df, amt_col, new_col, exclude_cancelled=False):
    """
    Helper to aggregate a single dataframe into:
    Year, MonthNum, Month, <new_col>

    - df:        input DataFrame
    - amt_col:   column to sum (e.g., 'Line Total', 'Amount', 'Cash Amount')
    - new_col:   output column name (e.g., 'total_revenue')
    - exclude_cancelled: if True, filter out Status == 'cancelled'
    """
    if df.empty:
        # Return empty frame with expected columns
        return pd.DataFrame(columns=["Year", "MonthNum", "Month", new_col])

    df = df.copy()

    if exclude_cancelled and "Status" in df.columns:
        df = df[df["Status"].astype(str).str.lower() != "cancelled"].copy()

    # Parse Date (mm/dd/yyyy)
    df["Date"] = pd.to_datetime(df["Date"], format="%m/%d/%Y")

    df["Year"] = df["Date"].dt.year
    df["MonthNum"] = df["Date"].dt.month
    df["Month"] = df["Date"].dt.strftime("%b")

    grouped = (
        df.groupby(["Year", "MonthNum", "Month"])
          .agg(**{new_col: (amt_col, "sum")})
          .reset_index()
    )

    return grouped

def compute_totals(stats_by_year):
    """
    stats_by_year looks like:
    {
        2025: [
            {"month": "Nov", "total_revenue": 0, "total_expense": 90, "total_cash": 0},
            {"month": "Dec", "total_revenue": 306, "total_expense": 255.37, "total_cash": 293},
        ],
        2026: [...]
    }

    Returns:
        totals_by_year = { year: {"total_revenue": X, "total_expense": Y, "total_cash": Z} }
        grand_totals   = {"total_revenue": X, "total_expense": Y, "total_cash": Z}
    """

    totals_by_year = {}
    grand_totals = {
        "total_revenue": 0.0,
        "total_expense": 0.0,
        "total_cash": 0.0,
    }

    for year, rows in stats_by_year.items():
        year_rev = 0.0
        year_exp = 0.0
        year_cash = 0.0

        for row in rows:
            year_rev += float(row.get("total_revenue", 0) or 0)
            year_exp += float(row.get("total_expense", 0) or 0)
            year_cash += float(row.get("total_cash", 0) or 0)

        totals_by_year[year] = {
            "total_revenue": year_rev,
            "total_expense": year_exp,
            "total_cash": year_cash,
        }

        grand_totals["total_revenue"] += year_rev
        grand_totals["total_expense"] += year_exp
        grand_totals["total_cash"] += year_cash

    return totals_by_year, grand_totals


if __name__ == "__main__":
    main()
