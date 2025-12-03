from flask import Flask, request, redirect, render_template, render_template_string
import os
import pandas as pd
from datetime import datetime
import re

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXCEL_FILE = os.path.join(BASE_DIR, "orders.xlsx")

# In-memory items + current customer for the ongoing order
items = []
current_customer = ""


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


@app.route("/", methods=["GET"])
def index():
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
    global items, current_customer

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

    return redirect("/")


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
    global items, current_customer

    if not items:
        return redirect("/")

    today = datetime.now().strftime("%m/%d/%Y")
    order_id = get_next_order_id()

    line_items = []
    for it in items:
        line_items.append({
            "order_id": order_id,
            "date": today,
            "customer": it["customer"],
            "item": it["item"],
            "price": it["price"],
            "count": it["count"],
            "line_total": it["line_total"],
        })

    excel_rows = [
        {
            "Order ID": li["order_id"],
            "Date": li["date"],
            "Customer": li["customer"],
            "Item": li["item"],
            "Price": li["price"],
            "Count": li["count"],
            "Line Total": li["line_total"],
            "Status" : "Accepted",
        }
        for li in line_items
    ]

    new_df = pd.DataFrame(excel_rows)

    if os.path.exists(EXCEL_FILE):
        existing_df = pd.read_excel(EXCEL_FILE)
        out_df = pd.concat([existing_df, new_df], ignore_index=True)
    else:
        out_df = new_df

    out_df.to_excel(EXCEL_FILE, index=False)

    order_date = today
    customer_name = current_customer
    grand_total = sum(li["line_total"] for li in line_items)

    # ✅ Reset in-memory state for a fresh order next time
    items = []
    current_customer = ""

    return render_template(
        "order_confirmation.html",
        order_id=order_id,
        status="Accepted",
        order_date=order_date,
        customer=customer_name,
        line_items=line_items,
        grand_total=grand_total,
    )


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
            "order_id": row["Order ID"],
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
    return redirect("/")

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

    # If no file yet, render empty dashboard
    if not os.path.exists(EXCEL_FILE):
        summary = {
            "total_orders": 0,
            "total_revenue": 0.0,
            "total_items": 0,
        }
        orders = []
        return render_template(
            "dashboard.html",
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
            "dashboard.html",
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

    # After filtering, compute summary
    if df.empty:
        summary = {
            "total_orders": 0,
            "total_revenue": 0.0,
            "total_items": 0,
        }
        orders = []
    else:
        total_orders = df["Order ID"].nunique()
        total_revenue = float(df["Line Total"].sum())
        total_items = int(df["Count"].sum())

        summary = {
            "total_orders": total_orders,
            "total_revenue": total_revenue,
            "total_items": total_items,
        }

        # Aggregate one row per order
        grouped = (
            df.groupby("Order ID")
              .agg({
                  "Date_parsed": "max",
                  "Customer": "first",
                  "Line Total": "sum",
                  "Item": "count",
              })
              .reset_index()
        )

        grouped.rename(columns={"Line Total": "Order Total", "Item": "Line Count"}, inplace=True)

        orders = []
        for _, row in grouped.iterrows():
            display_date = row["Date_parsed"].strftime("%Y-%m-%d") if not pd.isna(row["Date_parsed"]) else ""
            orders.append({
                "order_id": row["Order ID"],
                "date": display_date,
                "customer": row["Customer"],
                "total": float(row["Order Total"]),
                "line_count": int(row["Line Count"]),
            })

        # Sort newest first
        orders.sort(key=lambda r: (r["date"], r["order_id"]), reverse=True)

    return render_template(
        "dashboard.html",
        summary=summary,
        orders=orders,
        from_date=from_date_str,
        to_date=to_date_str,
        customer=customer_q,
    )

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=81)
