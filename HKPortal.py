from flask import (Flask, request, redirect, render_template, render_template_string, send_file,url_for,
    session,)
import os
import pandas as pd
from datetime import datetime
import re
import io
from functools import wraps

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXCEL_FILE = os.path.join(BASE_DIR, "orders.xlsx")
EXPENSE_FILE = os.path.join(BASE_DIR, "Expenses.xlsx")
REMIT_FILE = os.path.join(BASE_DIR, "MoneyMatters.xlsx")
Dashboard_page = "dashboard.html"


# In-memory items + current customer for the ongoing order
items = []
current_customer = ""
orderid="order_id"

def get_cart():
    session.setdefault("items", [])
    session.setdefault("current_customer", "")
    return session["items"], session["current_customer"]

def set_cart(items, current_customer):
    session["items"] = items
    session["current_customer"] = current_customer
    session.modified = True

def login_required(f):
    """Decorator to protect routes: sends user to login if not authenticated."""
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapped

def get_next_order_id():
    """
    Look at existing orders.xlsx (if present),
    find the highest numeric part of 'Order ID',
    and return HK<last+1>. If no file/IDs, start at HK1000.
    """
    base_num = 1000

    if not os.path.exists(EXCEL_FILE):
        return f"HK{base_num}"

    df = pd.read_excel(EXCEL_FILE)

    if "Order ID" not in df.columns or df["Order ID"].dropna().empty:
        return f"HK{base_num}"

    nums = []
    for val in df["Order ID"].dropna().astype(str):
        m = re.search(r"(\d+)$", val)
        if m:
            nums.append(int(m.group(1)))

    if not nums:
        next_num = base_num
    else:
        next_num = max(nums) + 1

    return f"HK{next_num}"

@app.route("/", methods=["GET", "POST"])
def login():
    """
    Landing page: login form.
    On success -> /home
    """
    error = None

    if request.method == "POST":
        userid = request.form.get("userid", "").strip()
        password = request.form.get("password", "")

        # ⭐ Hard-coded credentials for now (change as you like)
        VALID_USERS = {
            "HK-204": "hk204@123",
            "admin": "admin123",
        }

        if userid in VALID_USERS and VALID_USERS[userid] == password:
            session["logged_in"] = True
            session["user_id"] = userid
            return redirect(url_for("home"))
        else:
            error = "Invalid User ID or Password. Please try again."

    return render_template("index.html", error=error)

@app.route("/home", methods=["GET"])
@login_required
def home():
    """
    Simple home page with tabs:
    Dashboard | Add Order | Search Order | Update Order (later)
    """
    user_id = session.get("user_id")
    return render_template("home.html", user_id=user_id)


@app.route("/logout", methods=["GET"])
def logout():
    """Clear session and go back to login."""
    session.clear()
    return redirect(url_for("login"))

@app.route("/addorder", methods=["GET"])
def addorder():
    items, current_customer = get_cart()
    grand_total = sum(i["line_total"] for i in items) if items else 0

    return render_template(
        "addorderpg.html",
        items=items,
        grand_total=grand_total,
        current_customer=current_customer,
    )


@app.route("/add", methods=["POST"])
def add_item():
    """Add a single line item to the in-memory list and show it on the page."""
    items, current_customer = get_cart()
    posted_customer = request.form["customer"].strip()
    item = request.form["item"].strip()
    price = float(request.form["price"])
    count = int(request.form["count"])

    # Fix the customer name on the first add, and reuse afterwards
    if not current_customer:
        current_customer = posted_customer
    # Always use the stored customer (ignore any tampering on the client)
    customer = current_customer

    line_total = price * count

    items.append({
        "customer": customer,
        "item": item,
        "price": price,
        "count": count,
        "line_total": line_total,
    })
    set_cart(items, current_customer)
    return redirect("/addorder")


@app.route("/submit-order", methods=["POST"])
def submit_order():
    """
    When user clicks 'Submit Order':
    - compute next Order ID based on Excel
    - apply SAME Order ID to all current items
    - append them to Excel
    - clear current in-memory items & customer
    - show acknowledgement page
    """
    "global items, current_customer"
    items, current_customer = get_cart()
    if not items:
        return redirect("/addorder")

    today = datetime.now().strftime("%m/%d/%Y")
    order_id = get_next_order_id()

    excel_rows = []
    for it in items:
        excel_rows.append({
            "Order ID": order_id,
            "Date": today,
            "Customer": it["customer"],
            "Item": it["item"],
            "Price": float(it["price"]),
            "Count": int(it["count"]),
            "Line Total": float(it["line_total"]),
            "Status": "Accepted",
        })

    new_df = pd.DataFrame(excel_rows)

    if os.path.exists(EXCEL_FILE):
        existing_df = pd.read_excel(EXCEL_FILE)
        out_df = pd.concat([existing_df, new_df], ignore_index=True)
    else:
        out_df = new_df

    out_df.to_excel(EXCEL_FILE, index=False)

    order_date = today
    customer_name = current_customer
    grand_total = sum(r["Line Total"] for r in excel_rows)
    line_items = [
        {
            "date": today,
            "customer": r["Customer"],
            "item": r["Item"],
            "price": r["Price"],
            "count": r["Count"],
            "line_total": r["Line Total"],
        }
        for r in excel_rows
    ]

    # ✅ Reset in-memory state for a fresh order next time
    set_cart([], "")


    return render_template(
        "order_confirmation.html",
        order_id=order_id,
        status="Accepted",
        order_date=order_date,
        customer=customer_name,
        line_items=line_items,
        grand_total=grand_total,
    )

@app.route("/search-order", methods=["GET", "POST"])
@login_required
def srchorder():
    order_info = None
    error = None

    if request.method == "POST":
        order_id = request.form.get(orderid, "").strip()

        if not order_id:
            error = "Please enter an Order ID."
        else:
            # Redirect to view_order() which you already have
            return redirect(url_for("view_order", order_id=order_id))

    return render_template("srchorder.html", order_info=order_info, error=error)

@app.route("/updorder", methods=["GET","POST"])
@login_required
def updorder():
    order_info = None
    msg = request.args.get("msg")
    error = None

    if request.method == "POST":
        order_id = request.form.get(orderid, "").strip()

        if not order_id:
            error = "Please enter an Order ID."
        else:
            # Redirect to update_view_order() which you already have
            return redirect(url_for("update_view_order", order_id=order_id))

    return render_template("updorder.html", order_info=order_info, error=error, msg=msg)

@app.route("/order/<order_id>/forupdate", methods=["GET"])
def update_view_order(order_id):
    """View an existing order later by ID using the same acknowledgment page."""
    if not os.path.exists(EXCEL_FILE):
        return f"No orders found. File {EXCEL_FILE} does not exist.", 404

    df = pd.read_excel(EXCEL_FILE)

    if "Order ID" not in df.columns:
        return "Invalid orders file (no 'Order ID' column).", 500

    subset = df[df["Order ID"] == order_id]

    if subset.empty:
        return f"No order found with ID {order_id}", 404

    line_items = []
    for _, row in subset.iterrows():
        line_items.append({
            orderid: row["Order ID"],
            "date": row["Date"],
            "customer": row["Customer"],
            "item": row["Item"],
            "price": float(row["Price"]),
            "count": int(row["Count"]),
            "line_total": float(row["Line Total"]),
            "status": row["Status"]
        })

    order_date = line_items[0]["date"]
    customer_name = line_items[0]["customer"]
    status= line_items[0]["status"]
    grand_total = sum(li["line_total"] for li in line_items)

    return render_template(
        "updstatus.html",
        order_id=order_id,
        status=status,
        order_date=order_date,
        customer=customer_name,
        line_items=line_items,
        grand_total=grand_total,
    )


@app.route("/order/<order_id>/update-status", methods=["GET","POST"])
@login_required
def update_order_status(order_id):
    """
    Update the Status column for all rows with this Order ID
    based on the dropdown selection from the update page.
    """
    new_status = request.form.get("status", "").strip()

    if not new_status:
        # No status selected – just go back to the order page
        return redirect(url_for("view_order", order_id=order_id))

    # Ensure the Excel file exists
    if not os.path.exists(EXCEL_FILE):
        return f"No orders found. File {EXCEL_FILE} does not exist.", 404

    df = pd.read_excel(EXCEL_FILE)

    if "Order ID" not in df.columns:
        return "Invalid orders file (no 'Order ID' column).", 500

    # Find rows for this order_id
    mask = df["Order ID"] == order_id

    if not mask.any():
        return f"No order found with ID {order_id}", 404

    # Make sure Status column exists
    if "Status" not in df.columns:
        df["Status"] = ""

    # ✅ Update status
    df.loc[mask, "Status"] = new_status

    # Save back to Excel
    df.to_excel(EXCEL_FILE, index=False)

    # Redirect back to the order details page (updateOrder)
    #return redirect(url_for("updorder",  msg="Order updated successfully"))
    msg= "Order id : " + order_id + " updated successfully"
    return render_template("updorder.html", msg=msg)

@app.route("/order/<order_id>", methods=["GET"])
def view_order(order_id):
    """View an existing order later by ID using the same acknowledgment page."""
    if not os.path.exists(EXCEL_FILE):
        return f"No orders found. File {EXCEL_FILE} does not exist.", 404

    df = pd.read_excel(EXCEL_FILE)

    if "Order ID" not in df.columns:
        return "Invalid orders file (no 'Order ID' column).", 500

    subset = df[df["Order ID"] == order_id]

    if subset.empty:
        return f"No order found with ID {order_id}", 404

    line_items = []
    for _, row in subset.iterrows():
        line_items.append({
            orderid: row["Order ID"],
            "date": row["Date"],
            "customer": row["Customer"],
            "item": row["Item"],
            "price": float(row["Price"]),
            "count": int(row["Count"]),
            "line_total": float(row["Line Total"]),
            "status": row["Status"]
        })

    order_date = line_items[0]["date"]
    customer_name = line_items[0]["customer"]
    status= line_items[0]["status"]
    grand_total = sum(li["line_total"] for li in line_items)

    return render_template(
        "order_confirmation.html",
        order_id=order_id,
        status=status,
        order_date=order_date,
        customer=customer_name,
        line_items=line_items,
        grand_total=grand_total,
    )


@app.route("/reset", methods=["POST"])
def reset_order():
    """Clear all in-memory items and customer and start fresh."""
    global items, current_customer
    items = []
    current_customer = ""
    return redirect("/addorder")

@app.route("/dashboard", methods=["GET"])
def dashboard():
    """
    Admin dashboard with optional filters:
    - from_date (YYYY-MM-DD)
    - to_date   (YYYY-MM-DD)
    - customer  (partial match, case-insensitive)
    """
    # Read query params
    from_date_str = request.args.get("from_date", "").strip()
    to_date_str = request.args.get("to_date", "").strip()
    customer_q = request.args.get("customer", "").strip()
    status_q = request.args.get("status", "").strip().lower() 
    if "status" not in request.args:
       status_q = "not_cancelled"
    # If no file yet, render empty dashboard
    if not os.path.exists(EXCEL_FILE):
        summary = {
            "total_orders": 0,
            "total_revenue": 0.0,
            "total_items": 0,
        }
        orders = []
        return render_template(
            Dashboard_page,
            summary=summary,
            orders=orders,
            from_date=from_date_str,
            to_date=to_date_str,
            customer=customer_q,
        )

    df = pd.read_excel(EXCEL_FILE)

    if df.empty or "Order ID" not in df.columns:
        summary = {
            "total_orders": 0,
            "total_revenue": 0.0,
            "total_items": 0,
        }
        orders = []
        return render_template(
            Dashboard_page,
            summary=summary,
            orders=orders,
            from_date=from_date_str,
            to_date=to_date_str,
            customer=customer_q,
        )

    # Parse dates from the "Date" column
    df["Date_parsed"] = pd.to_datetime(df["Date"], errors="coerce")

    # Apply date filters if provided (browser sends YYYY-MM-DD)
    if from_date_str:
        from_dt = pd.to_datetime(from_date_str, errors="coerce")
        if not pd.isna(from_dt):
            df = df[df["Date_parsed"] >= from_dt]

    if to_date_str:
        to_dt = pd.to_datetime(to_date_str, errors="coerce")
        if not pd.isna(to_dt):
            # include the end date fully
            df = df[df["Date_parsed"] <= to_dt]

    # Apply customer filter (contains, case-insensitive)
    if customer_q:
        df = df[df["Customer"].astype(str).str.contains(customer_q, case=False, na=False)]
    df_filtered = df.copy()        
    df_table=df.copy()
    if status_q == "not_cancelled":
        df_filtered = df_filtered[
        df_filtered["Status"].astype(str).str.lower() != "cancelled"]
    elif status_q:
        df_filtered = df_filtered[df_filtered["Status"].astype(str).str.lower() == status_q]
    #→ EXCLUDE CANCELLED ORDERS FROM SUMMARY
    df_summary= df[df["Status"].astype(str).str.lower() != "cancelled"]
    # After filtering, compute summary
    if df_summary.empty:
        summary = {
            "total_orders": 0,
            "total_revenue": 0.0,
            "total_items": 0,
        }
        orders = []
    else:
        total_orders = df_summary["Order ID"].nunique()
        total_revenue = float(df_summary["Line Total"].sum())
        total_items = int(df_summary["Count"].sum())

        summary = {
            "total_orders": total_orders,
            "total_revenue": total_revenue,
            "total_items": total_items,
        }
    
    orders = []
    if not df_filtered.empty:
        # Aggregate one row per order
        grouped = (
            df_filtered.groupby("Order ID")
              .agg({
                  "Date_parsed": "max",
                  "Customer": "first",
                  "Status": "first",
                  "Line Total": "sum",
                  "Item": "count",
              })
              .reset_index()
        )

        grouped.rename(columns={"Line Total": "Order Total", "Item": "Line Count"}, inplace=True)

        orders = []
        for _, row in grouped.iterrows():
            display_date = row["Date_parsed"].strftime("%m-%d-%Y`") if not pd.isna(row["Date_parsed"]) else ""
            orders.append({
                orderid: row["Order ID"],
                "date": display_date,
                "customer": row["Customer"],
                "status": row["Status"],
                "total": float(row["Order Total"]),
                "line_count": int(row["Line Count"]),
            })

        # Sort newest first
        orders.sort(key=lambda r: (r["date"], r[orderid]), reverse=True)

    return render_template(
        Dashboard_page,
        summary=summary,
        orders=orders,
        from_date=from_date_str,
        to_date=to_date_str,
        customer=customer_q,
        status=status_q,
    )

@app.route("/menu")
def menu():
    return render_template("menu.html")

@app.route("/stats/export")
def export_stats_excel():
    stats_by_year = build_stats()  # same as in /stats
    df = stats_to_dataframe(stats_by_year)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Stats")
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="HarrysKitchen_Stats.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

def compute_grand_totals(stats_by_year):

    grand = {
        "total_expense": 0.0,
        "total_cash": 0.0,
        "total_revenue": 0.0,
    }

    for year, rows in stats_by_year.items():
        for row in rows:
            grand["total_expense"] += float(row.get("total_expense", 0) or 0)
            grand["total_cash"]    += float(row.get("total_cash", 0) or 0)
            grand["total_revenue"] += float(row.get("total_revenue", 0) or 0)

    return grand

def stats_to_dataframe(stats_by_year):
    """
    Flattens stats_by_year into a DataFrame with columns:
    Year, Month, Total Expense, Total Cash, Total Revenue
    """
    rows = []
    for year, monthly in stats_by_year.items():
        for row in monthly:
            rows.append({
                "Year": year,
                "Month": row["month"],
                "Total Expense": float(row.get("total_expense", 0) or 0),
                "Total Cash": float(row.get("total_cash", 0) or 0),
                "Total Revenue": float(row.get("total_revenue", 0) or 0),
            })
    return pd.DataFrame(rows)

@app.route("/stats")
def stats():
    stats_by_year = build_stats()
    years = sorted(stats_by_year.keys(), reverse=True)
    grand_totals = compute_grand_totals(stats_by_year)
    return render_template(
        "stats.html",
        stats_by_year=stats_by_year,
        grand_totals=grand_totals,
        years=years,
    )

def build_stats():

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

@app.route("/monthly-summary", methods=["GET"])
def monthly_summary():
    # Get month & year from query params, default to current month/year
    now = datetime.now()
    month = request.args.get("month", default=str(now.month))
    year = request.args.get("year", default=str(now.year))

    # Convert to int safely
    try:
        month_int = int(month)
        year_int = int(year)
    except ValueError:
        month_int = now.month
        year_int = now.year

    summary_rows = []
    monthly_total = 0.0
    file_missing = False
    no_data = False

    if not os.path.exists(EXCEL_FILE):
        file_missing = True
    else:
        df = pd.read_excel(EXCEL_FILE)

        # Make sure the date column exists
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            df = df.dropna(subset=["Date"])

            # Optionally exclude Cancelled
            if "Status" in df.columns:
                df = df[df["Status"].astype(str).str.lower() != "cancelled"]

            # Filter by selected month & year
            df_filtered = df[
                (df["Date"].dt.month == month_int) &
                (df["Date"].dt.year == year_int)
            ]

            if df_filtered.empty:
                no_data = True
            else:
                # Group by date (just the date part)
                df_grouped = df_filtered.groupby(df_filtered["Date"].dt.date).agg(
                    total_amount=("Line Total", "sum"),
                    order_count=("Order ID", "nunique") if "Order ID" in df.columns else ("Date", "count")
                ).reset_index()

                # Prepare rows for template
                for _, row in df_grouped.iterrows():
                    summary_rows.append({
                        "date": row["Date"].strftime("%Y-%m-%d"),
                        "order_count": int(row["order_count"]),
                        "total_amount": float(row["total_amount"])
                    })

                monthly_total = sum(r["total_amount"] for r in summary_rows)
        else:
            no_data = True

    # Month options for dropdown
    month_options = [
        {"value": i, "label": datetime(2000, i, 1).strftime("%B")}
        for i in range(1, 13)
    ]

    return render_template(
        "monthly_summary.html",
        month=str(month_int),
        year=str(year_int),
        month_options=month_options,
        summary_rows=summary_rows,
        monthly_total=monthly_total,
        file_missing=file_missing,
        no_data=no_data,
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
