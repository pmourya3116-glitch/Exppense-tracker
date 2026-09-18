from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
import sqlite3
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
import io

app = Flask(__name__)
app.secret_key = "change-this-secret-key"

DATABASE = "my_expenses.db"


# ============================================================
# DATABASE
# ============================================================

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def create_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS salary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            monthly_salary REAL NOT NULL,
            username TEXT NOT NULL UNIQUE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS budget (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            monthly_budget REAL NOT NULL,
            username TEXT NOT NULL UNIQUE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            gst REAL NOT NULL,
            total_after_gst REAL NOT NULL,
            transaction_type TEXT NOT NULL,
            category TEXT NOT NULL,
            date TEXT NOT NULL,
            username TEXT NOT NULL
        )
    """)

    # Demo/admin account
    cursor.execute(
        "SELECT username FROM users WHERE username=?",
        ("admin",)
    )

    if cursor.fetchone() is None:
        cursor.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            ("admin", generate_password_hash("admin123"))
        )

        cursor.execute(
            "INSERT INTO salary (monthly_salary, username) VALUES (?, ?)",
            (30000, "admin")
        )

        cursor.execute(
            "INSERT INTO budget (monthly_budget, username) VALUES (?, ?)",
            (10000, "admin")
        )

    conn.commit()
    conn.close()


# ============================================================
# LOGIN REQUIRED
# ============================================================

def logged_in():
    return "username" in session


# ============================================================
# WELCOME
# ============================================================

@app.route("/")
def welcome():
    return render_template("welcome.html")


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"].strip()
        password = request.form["password"]

        conn = get_db()

        user = conn.execute(
            "SELECT * FROM users WHERE username=?",
            (username,)
        ).fetchone()

        conn.close()

        if user and check_password_hash(
            user["password"],
            password
        ):

            session["username"] = username

            flash(
                f"Welcome, {username}!",
                "success"
            )

            return redirect(url_for("dashboard"))

        flash(
            "Incorrect username or password.",
            "danger"
        )

    return render_template("login.html")


# ============================================================
# REGISTER
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form["username"].strip()
        password = request.form["password"]

        if not username or not password:

            flash(
                "All fields are required!",
                "danger"
            )

            return redirect(url_for("register"))

        conn = get_db()

        try:

            conn.execute(
                """
                INSERT INTO users
                (username, password)
                VALUES (?, ?)
                """,
                (
                    username,
                    generate_password_hash(password)
                )
            )

            conn.execute(
                """
                INSERT INTO salary
                (monthly_salary, username)
                VALUES (?, ?)
                """,
                (0, username)
            )

            conn.execute(
                """
                INSERT INTO budget
                (monthly_budget, username)
                VALUES (?, ?)
                """,
                (10000, username)
            )

            conn.commit()

            flash(
                "Registration successful! Please login.",
                "success"
            )

            return redirect(url_for("login"))

        except sqlite3.IntegrityError:

            flash(
                "Username already exists!",
                "danger"
            )

        finally:
            conn.close()

    return render_template("register.html")


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
def dashboard():

    if not logged_in():
        return redirect(url_for("login"))

    username = session["username"]

    conn = get_db()

    salary_row = conn.execute(
        """
        SELECT monthly_salary
        FROM salary
        WHERE username=?
        """,
        (username,)
    ).fetchone()

    budget_row = conn.execute(
        """
        SELECT monthly_budget
        FROM budget
        WHERE username=?
        """,
        (username,)
    ).fetchone()

    transactions = conn.execute(
        """
        SELECT *
        FROM transactions
        WHERE username=?
        ORDER BY date DESC, id DESC
        """,
        (username,)
    ).fetchall()

    income_row = conn.execute(
        """
        SELECT COALESCE(SUM(total_after_gst), 0)
        FROM transactions
        WHERE username=?
        AND transaction_type='Income'
        """,
        (username,)
    ).fetchone()

    expense_row = conn.execute(
        """
        SELECT COALESCE(SUM(total_after_gst), 0)
        FROM transactions
        WHERE username=?
        AND transaction_type='Expense'
        """,
        (username,)
    ).fetchone()

    conn.close()

    salary = salary_row["monthly_salary"] if salary_row else 0
    budget = budget_row["monthly_budget"] if budget_row else 0

    income = income_row[0]
    expenses = expense_row[0]

    # Account balance
    balance = salary + income - expenses

    budget_exceeded = (
        budget > 0 and expenses > budget
    )

    return render_template(
        "dashboard.html",
        username=username,
        salary=salary,
        budget=budget,
        income=income,
        expenses=expenses,
        balance=balance,
        transactions=transactions,
        budget_exceeded=budget_exceeded
    )


# ============================================================
# UPDATE SALARY AND BUDGET
# ============================================================

@app.route("/update-financial", methods=["POST"])
def update_financial():

    if not logged_in():
        return redirect(url_for("login"))

    username = session["username"]

    try:

        salary = float(
            request.form["salary"]
        )

        budget = float(
            request.form["budget"]
        )

        if salary < 0 or budget < 0:
            raise ValueError

    except ValueError:

        flash(
            "Please enter valid salary and budget values.",
            "danger"
        )

        return redirect(url_for("dashboard"))

    conn = get_db()

    conn.execute(
        """
        UPDATE salary
        SET monthly_salary=?
        WHERE username=?
        """,
        (salary, username)
    )

    conn.execute(
        """
        UPDATE budget
        SET monthly_budget=?
        WHERE username=?
        """,
        (budget, username)
    )

    conn.commit()
    conn.close()

    flash(
        "Salary and expense budget updated successfully!",
        "success"
    )

    return redirect(url_for("dashboard"))


# ============================================================
# ADD TRANSACTION
# ============================================================

@app.route("/add-transaction", methods=["POST"])
def add_transaction():

    if not logged_in():
        return redirect(url_for("login"))

    username = session["username"]

    description = request.form["description"].strip()
    amount = request.form["amount"].strip()
    gst = request.form["gst"].strip()
    transaction_type = request.form["transaction_type"].strip()
    category = request.form["category"].strip()
    date = request.form["date"].strip()

    if not all([
        description,
        amount,
        transaction_type,
        category,
        date
    ]):

        flash(
            "All transaction fields are required!",
            "danger"
        )

        return redirect(url_for("dashboard"))

    try:

        amount_value = float(amount)

        if amount_value <= 0:
            raise ValueError

        if transaction_type == "Expense" and gst:

            gst_value = float(gst)

            if gst_value < 0:
                raise ValueError

        else:

            gst_value = 0

        datetime.strptime(
            date,
            "%Y-%m-%d"
        )

    except ValueError:

        flash(
            "Invalid amount, GST or date.",
            "danger"
        )

        return redirect(url_for("dashboard"))

    gst_amount = (
        amount_value * gst_value / 100
    )

    total = (
        amount_value + gst_amount
    )

    conn = get_db()

    conn.execute(
        """
        INSERT INTO transactions
        (
            description,
            amount,
            gst,
            total_after_gst,
            transaction_type,
            category,
            date,
            username
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            description,
            amount_value,
            gst_value,
            total,
            transaction_type,
            category,
            date,
            username
        )
    )

    conn.commit()

    # Check budget after expense
    expense_row = conn.execute(
        """
        SELECT COALESCE(SUM(total_after_gst), 0)
        FROM transactions
        WHERE username=?
        AND transaction_type='Expense'
        """,
        (username,)
    ).fetchone()

    budget_row = conn.execute(
        """
        SELECT monthly_budget
        FROM budget
        WHERE username=?
        """,
        (username,)
    ).fetchone()

    conn.close()

    if (
        transaction_type == "Expense"
        and budget_row
        and expense_row[0] > budget_row["monthly_budget"]
    ):

        flash(
            f"Budget Exceeded! Your expenses are "
            f"₹{expense_row[0]:.2f}, while your budget is "
            f"₹{budget_row['monthly_budget']:.2f}.",
            "danger"
        )

    else:

        flash(
            "Transaction added successfully!",
            "success"
        )

    return redirect(url_for("dashboard"))


# ============================================================
# DELETE TRANSACTION
# ============================================================

@app.route("/delete/<int:transaction_id>", methods=["POST"])
def delete_transaction(transaction_id):

    if not logged_in():
        return redirect(url_for("login"))

    username = session["username"]

    conn = get_db()

    conn.execute(
        """
        DELETE FROM transactions
        WHERE id=?
        AND username=?
        """,
        (
            transaction_id,
            username
        )
    )

    conn.commit()
    conn.close()

    flash(
        "Transaction deleted successfully!",
        "success"
    )

    return redirect(url_for("dashboard"))


# ============================================================
# FILTER TRANSACTIONS
# ============================================================

@app.route("/filter")
def filter_transactions():

    if not logged_in():
        return redirect(url_for("login"))

    username = session["username"]

    from_date = request.args.get(
        "from_date",
        ""
    )

    to_date = request.args.get(
        "to_date",
        ""
    )

    try:

        datetime.strptime(
            from_date,
            "%Y-%m-%d"
        )

        datetime.strptime(
            to_date,
            "%Y-%m-%d"
        )

    except ValueError:

        flash(
            "Enter valid dates in YYYY-MM-DD format.",
            "danger"
        )

        return redirect(url_for("dashboard"))

    conn = get_db()

    transactions = conn.execute(
        """
        SELECT *
        FROM transactions
        WHERE username=?
        AND date BETWEEN ? AND ?
        ORDER BY date DESC, id DESC
        """,
        (
            username,
            from_date,
            to_date
        )
    ).fetchall()

    conn.close()

    return render_template(
        "dashboard.html",
        username=username,
        salary=get_salary(username),
        budget=get_budget(username),
        income=get_income(username),
        expenses=get_expenses(username),
        balance=get_balance(username),
        transactions=transactions,
        budget_exceeded=(
            get_expenses(username)
            > get_budget(username)
        ),
        filtered=True
    )


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_salary(username):

    conn = get_db()

    row = conn.execute(
        """
        SELECT monthly_salary
        FROM salary
        WHERE username=?
        """,
        (username,)
    ).fetchone()

    conn.close()

    return row["monthly_salary"] if row else 0


def get_budget(username):

    conn = get_db()

    row = conn.execute(
        """
        SELECT monthly_budget
        FROM budget
        WHERE username=?
        """,
        (username,)
    ).fetchone()

    conn.close()

    return row["monthly_budget"] if row else 0


def get_income(username):

    conn = get_db()

    row = conn.execute(
        """
        SELECT COALESCE(SUM(total_after_gst), 0)
        FROM transactions
        WHERE username=?
        AND transaction_type='Income'
        """,
        (username,)
    ).fetchone()

    conn.close()

    return row[0]


def get_expenses(username):

    conn = get_db()

    row = conn.execute(
        """
        SELECT COALESCE(SUM(total_after_gst), 0)
        FROM transactions
        WHERE username=?
        AND transaction_type='Expense'
        """,
        (username,)
    ).fetchone()

    conn.close()

    return row[0]


def get_balance(username):

    return (
        get_salary(username)
        + get_income(username)
        - get_expenses(username)
    )


# ============================================================
# EXPORT TO EXCEL
# ============================================================

@app.route("/export")
def export_excel():

    if not logged_in():
        return redirect(url_for("login"))

    username = session["username"]

    conn = get_db()

    rows = conn.execute(
        """
        SELECT
            id,
            description,
            amount,
            gst,
            total_after_gst,
            transaction_type,
            category,
            date
        FROM transactions
        WHERE username=?
        ORDER BY date DESC
        """,
        (username,)
    ).fetchall()

    conn.close()

    if not rows:

        flash(
            "No transactions available to export.",
            "warning"
        )

        return redirect(url_for("dashboard"))

    data = [
        dict(row)
        for row in rows
    ]

    df = pd.DataFrame(data)

    output = io.BytesIO()

    with pd.ExcelWriter(
        output,
        engine="openpyxl"
    ) as writer:

        df.to_excel(
            writer,
            index=False,
            sheet_name="Transactions"
        )

    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="transactions.xlsx",
        mimetype=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        )
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    flash(
        "You have been logged out successfully.",
        "success"
    )

    return redirect(url_for("login"))


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    create_db()

    app.run(
        debug=True,
        host="0.0.0.0",
        port=5000
    )
