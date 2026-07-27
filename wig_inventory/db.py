import sqlite3
from pathlib import Path

import pandas as pd

DB_DIR = Path(__file__).parent / "data"
DB_PATH = DB_DIR / "wig.db"


def get_conn():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS branches (
            branch_id TEXT PRIMARY KEY,   -- ERP 사업장/지점명 (엑셀에 지점코드가 없는 파일이 있어 이름을 키로 사용)
            branch_code TEXT
        );

        CREATE TABLE IF NOT EXISTS products (
            product_id TEXT PRIMARY KEY,  -- model|color|size 조합 키
            model TEXT NOT NULL,
            color TEXT,
            size INTEGER,
            category TEXT
        );

        CREATE TABLE IF NOT EXISTS inventory_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT NOT NULL,
            branch_id TEXT NOT NULL REFERENCES branches(branch_id),
            product_id TEXT NOT NULL REFERENCES products(product_id),
            quantity INTEGER NOT NULL,
            UNIQUE(snapshot_date, branch_id, product_id)
        );

        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_month TEXT NOT NULL,  -- 'YYYY-MM'
            branch_id TEXT NOT NULL REFERENCES branches(branch_id),
            product_id TEXT NOT NULL REFERENCES products(product_id),
            quantity INTEGER NOT NULL,
            amount INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS upload_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT,
            upload_type TEXT NOT NULL,
            upload_date TEXT NOT NULL,
            row_count INTEGER,
            status TEXT,
            error_message TEXT
        );
        """
    )
    conn.commit()
    conn.close()


def upsert_branch(branch_id: str, branch_code: str | None = None):
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO branches (branch_id, branch_code) VALUES (?, ?)
        ON CONFLICT(branch_id) DO UPDATE SET branch_code=COALESCE(excluded.branch_code, branches.branch_code)
        """,
        (branch_id, branch_code),
    )
    conn.commit()
    conn.close()


def upsert_product(product_id: str, model: str, color: str | None, size: int, category: str | None = None):
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO products (product_id, model, color, size, category) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(product_id) DO UPDATE SET category=COALESCE(excluded.category, products.category)
        """,
        (product_id, model, color, size, category),
    )
    conn.commit()
    conn.close()


def replace_inventory_snapshots(dates: set, rows: list):
    """Delete existing snapshot rows for the given dates, then insert the new rows (overwrite-on-reupload)."""
    conn = get_conn()
    cur = conn.cursor()
    cur.executemany("DELETE FROM inventory_snapshots WHERE snapshot_date=?", [(d,) for d in dates])
    cur.executemany(
        "INSERT INTO inventory_snapshots (snapshot_date, branch_id, product_id, quantity) VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()


def replace_sales(months: set, rows: list):
    """Delete existing sales rows for the given sale_months, then insert the new rows (overwrite-on-reupload)."""
    conn = get_conn()
    cur = conn.cursor()
    cur.executemany("DELETE FROM sales WHERE sale_month=?", [(m,) for m in months])
    cur.executemany(
        "INSERT INTO sales (sale_month, branch_id, product_id, quantity, amount) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()


def save_stock_upload(valid: pd.DataFrame, snapshot_date_str: str):
    """valid: DataFrame with columns branch, model, color, size, quantity, category, product_id."""
    for b in valid["branch"].drop_duplicates():
        upsert_branch(b)

    prod_rows = valid[["product_id", "model", "color", "size", "category"]].drop_duplicates(subset=["product_id"])
    for _, r in prod_rows.iterrows():
        upsert_product(r["product_id"], r["model"], r["color"], int(r["size"]), r["category"])

    rows = list(zip([snapshot_date_str] * len(valid), valid["branch"], valid["product_id"], valid["quantity"]))
    replace_inventory_snapshots({snapshot_date_str}, rows)
    return len(rows)


def save_sales_upload(valid: pd.DataFrame):
    """valid: DataFrame with columns sale_month, branch, branch_code, model, color, size, quantity, amount, product_id."""
    branch_map = valid[["branch", "branch_code"]].drop_duplicates(subset=["branch"])
    for _, r in branch_map.iterrows():
        upsert_branch(r["branch"], r["branch_code"] or None)

    prod_rows = valid[["product_id", "model", "color", "size"]].drop_duplicates(subset=["product_id"])
    for _, r in prod_rows.iterrows():
        upsert_product(r["product_id"], r["model"], r["color"], int(r["size"]))

    months = set(valid["sale_month"])
    rows = list(zip(valid["sale_month"], valid["branch"], valid["product_id"], valid["quantity"], valid["amount"]))
    replace_sales(months, rows)
    return len(rows), months


def log_upload(file_name: str, upload_type: str, row_count: int, status: str, error_message: str | None):
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO upload_logs (file_name, upload_type, upload_date, row_count, status, error_message)
        VALUES (?, ?, datetime('now', 'localtime'), ?, ?, ?)
        """,
        (file_name, upload_type, row_count, status, error_message),
    )
    conn.commit()
    conn.close()


def list_snapshot_dates():
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT snapshot_date FROM inventory_snapshots ORDER BY snapshot_date DESC"
    ).fetchall()
    conn.close()
    return [r["snapshot_date"] for r in rows]


def list_branches():
    conn = get_conn()
    rows = conn.execute("SELECT branch_id FROM branches ORDER BY branch_id").fetchall()
    conn.close()
    return [(r["branch_id"], r["branch_id"]) for r in rows]


def list_products():
    conn = get_conn()
    rows = conn.execute(
        "SELECT product_id, model, color, size FROM products ORDER BY model, color, size"
    ).fetchall()
    conn.close()
    return [(r["product_id"], f"{r['model']} ({r['color'] or '-'}/{r['size']})") for r in rows]


def get_inventory_pivot(snapshot_date: str) -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query(
        """
        SELECT s.branch_id AS 지점,
               (p.model || ' (' || COALESCE(p.color, '-') || '/' || CAST(p.size AS TEXT) || ')') AS 상품,
               s.quantity AS 수량
        FROM inventory_snapshots s
        JOIN products p ON p.product_id = s.product_id
        WHERE s.snapshot_date = ?
        """,
        conn,
        params=(snapshot_date,),
    )
    conn.close()
    if df.empty:
        return df
    return df.pivot_table(index="지점", columns="상품", values="수량", fill_value=0, aggfunc="sum")


def get_inventory_trend(branch_id: str, product_id: str) -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query(
        """
        SELECT snapshot_date, quantity
        FROM inventory_snapshots
        WHERE branch_id=? AND product_id=?
        ORDER BY snapshot_date
        """,
        conn,
        params=(branch_id, product_id),
    )
    conn.close()
    return df


def get_sales_months():
    conn = get_conn()
    rows = conn.execute("SELECT DISTINCT sale_month FROM sales ORDER BY sale_month").fetchall()
    conn.close()
    return [r["sale_month"] for r in rows]


def get_branch_ranking(start_month: str, end_month: str) -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query(
        """
        SELECT branch_id AS 지점, SUM(amount) AS 판매금액, SUM(quantity) AS 판매수량
        FROM sales
        WHERE sale_month BETWEEN ? AND ?
        GROUP BY branch_id
        ORDER BY 판매금액 DESC
        """,
        conn,
        params=(start_month, end_month),
    )
    conn.close()
    return df


def get_monthly_trend(branch_id: str | None = None) -> pd.DataFrame:
    conn = get_conn()
    if branch_id:
        df = pd.read_sql_query(
            """
            SELECT sale_month, SUM(amount) AS amount, SUM(quantity) AS quantity
            FROM sales WHERE branch_id=? GROUP BY sale_month ORDER BY sale_month
            """,
            conn,
            params=(branch_id,),
        )
    else:
        df = pd.read_sql_query(
            """
            SELECT sale_month, SUM(amount) AS amount, SUM(quantity) AS quantity
            FROM sales GROUP BY sale_month ORDER BY sale_month
            """,
            conn,
        )
    conn.close()
    return df


def get_branch_comparison(start_month: str, end_month: str, metric: str = "amount") -> pd.DataFrame:
    col = "amount" if metric == "amount" else "quantity"
    conn = get_conn()
    df = pd.read_sql_query(
        f"""
        SELECT sale_month, branch_id, SUM({col}) AS value
        FROM sales
        WHERE sale_month BETWEEN ? AND ?
        GROUP BY sale_month, branch_id
        """,
        conn,
        params=(start_month, end_month),
    )
    conn.close()
    if df.empty:
        return df
    return df.pivot_table(index="sale_month", columns="branch_id", values="value", fill_value=0)


def list_upload_logs() -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query(
        "SELECT file_name, upload_type, upload_date, row_count, status, error_message FROM upload_logs ORDER BY upload_date DESC",
        conn,
    )
    conn.close()
    return df
