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

        CREATE TABLE IF NOT EXISTS order_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT NOT NULL,           -- 발주번호 (배치 단위)
            branch_id TEXT NOT NULL REFERENCES branches(branch_id),
            order_date TEXT,                  -- 발주일자
            product_id TEXT NOT NULL REFERENCES products(product_id),
            model TEXT,
            color TEXT,
            size INTEGER,
            na_code TEXT,
            requested_qty INTEGER,            -- 신청 수량
            confirmed_qty INTEGER,            -- 확정 수량
            cancelled_qty INTEGER,            -- 발주 취소수량
            hq_confirm_date TEXT,             -- 본사 확정일자
            factory_code TEXT,                -- fact_cd
            serial_range TEXT,                -- compute_2
            factory_accept_date TEXT,         -- fact_acpt_dt
            note TEXT
        );

        CREATE TABLE IF NOT EXISTS order_units (
            order_unit_no TEXT PRIMARY KEY,   -- 오더번호 (유닛 단위 시리얼)
            branch_id TEXT NOT NULL REFERENCES branches(branch_id),
            product_id TEXT NOT NULL REFERENCES products(product_id),
            model TEXT,
            color TEXT,
            size INTEGER,
            factory TEXT,                     -- 발주공장
            order_type TEXT,                  -- 오더구분 (발주입고/Repair(검수)/이동입고/기타출고 등)
            factory_ship_date TEXT,           -- 공장 발송일자
            factory_receive_date TEXT,        -- 공장 접수일자
            factory_out_date TEXT,            -- 공장 출고일자
            trade_in_date TEXT,               -- 무역부 입고일자
            trade_ship_date TEXT,             -- 무역부 선적일자
            stock_date TEXT,                  -- 재고일자 (입고 인식일; 발주현황파일의 재고일자 사용)
            cancel_date TEXT,                 -- 취소일자
            discard_date TEXT                 -- 폐기일자
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


def save_order_batches(valid: pd.DataFrame):
    """valid: DataFrame with columns order_no, branch, order_date, model, color, size, product_id,
    na_code, requested_qty, confirmed_qty, cancelled_qty, hq_confirm_date, factory_code,
    serial_range, factory_accept_date, note.
    Overwrites by order_no (re-uploading a batch replaces its previous line items).
    """
    for b in valid["branch"].drop_duplicates():
        upsert_branch(b)

    prod_rows = valid[["product_id", "model", "color", "size"]].drop_duplicates(subset=["product_id"])
    for _, r in prod_rows.iterrows():
        upsert_product(r["product_id"], r["model"], r["color"], int(r["size"]))

    conn = get_conn()
    cur = conn.cursor()
    order_nos = list(valid["order_no"].drop_duplicates())
    cur.executemany("DELETE FROM order_batches WHERE order_no=?", [(o,) for o in order_nos])
    cur.executemany(
        """
        INSERT INTO order_batches (
            order_no, branch_id, order_date, product_id, model, color, size, na_code,
            requested_qty, confirmed_qty, cancelled_qty, hq_confirm_date, factory_code,
            serial_range, factory_accept_date, note
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        list(
            valid[
                [
                    "order_no", "branch", "order_date", "product_id", "model", "color", "size", "na_code",
                    "requested_qty", "confirmed_qty", "cancelled_qty", "hq_confirm_date", "factory_code",
                    "serial_range", "factory_accept_date", "note",
                ]
            ].itertuples(index=False, name=None)
        ),
    )
    conn.commit()
    conn.close()
    return len(valid)


def save_order_units(valid: pd.DataFrame):
    """valid: DataFrame with columns order_unit_no, branch, model, color, size, product_id, factory,
    order_type, factory_ship_date, factory_receive_date, factory_out_date, trade_in_date,
    trade_ship_date, stock_date, cancel_date, discard_date.
    Upserts by order_unit_no so re-uploads reflect status progression without duplicating rows.
    """
    for b in valid["branch"].drop_duplicates():
        upsert_branch(b)

    prod_rows = valid[["product_id", "model", "color", "size"]].drop_duplicates(subset=["product_id"])
    for _, r in prod_rows.iterrows():
        upsert_product(r["product_id"], r["model"], r["color"], int(r["size"]))

    conn = get_conn()
    conn.executemany(
        """
        INSERT INTO order_units (
            order_unit_no, branch_id, product_id, model, color, size, factory, order_type,
            factory_ship_date, factory_receive_date, factory_out_date, trade_in_date,
            trade_ship_date, stock_date, cancel_date, discard_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(order_unit_no) DO UPDATE SET
            branch_id=excluded.branch_id, product_id=excluded.product_id, model=excluded.model,
            color=excluded.color, size=excluded.size, factory=excluded.factory,
            order_type=excluded.order_type, factory_ship_date=excluded.factory_ship_date,
            factory_receive_date=excluded.factory_receive_date, factory_out_date=excluded.factory_out_date,
            trade_in_date=excluded.trade_in_date, trade_ship_date=excluded.trade_ship_date,
            stock_date=excluded.stock_date, cancel_date=excluded.cancel_date, discard_date=excluded.discard_date
        """,
        list(
            valid[
                [
                    "order_unit_no", "branch", "product_id", "model", "color", "size", "factory", "order_type",
                    "factory_ship_date", "factory_receive_date", "factory_out_date", "trade_in_date",
                    "trade_ship_date", "stock_date", "cancel_date", "discard_date",
                ]
            ].itertuples(index=False, name=None)
        ),
    )
    conn.commit()
    conn.close()
    return len(valid)


_STATUS_CASE_SQL = """
    CASE
        WHEN discard_date IS NOT NULL THEN '폐기'
        WHEN cancel_date IS NOT NULL THEN '취소'
        WHEN stock_date IS NOT NULL THEN '입고완료'
        WHEN trade_ship_date IS NOT NULL THEN '무역부선적(배송중)'
        WHEN trade_in_date IS NOT NULL THEN '무역부입고'
        WHEN factory_out_date IS NOT NULL THEN '공장출고'
        WHEN factory_receive_date IS NOT NULL THEN '공장접수(생산중)'
        WHEN factory_ship_date IS NOT NULL THEN '공장발송'
        ELSE '발주대기'
    END
"""


def get_order_status_summary() -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query(
        f"SELECT {_STATUS_CASE_SQL} AS 진행상태, COUNT(*) AS 건수 FROM order_units GROUP BY 진행상태 ORDER BY 건수 DESC",
        conn,
    )
    conn.close()
    return df


def list_order_units(branch_id: str | None = None, status: str | None = None) -> pd.DataFrame:
    conn = get_conn()
    query = f"""
        SELECT order_unit_no AS 오더번호, branch_id AS 지점, model AS 모델, color AS 컬러, size AS 사이즈,
               factory AS 발주공장, order_type AS 오더구분,
               factory_ship_date AS 공장발송일, stock_date AS 입고일, cancel_date AS 취소일, discard_date AS 폐기일,
               {_STATUS_CASE_SQL} AS 진행상태
        FROM order_units
        WHERE 1=1
    """
    params = []
    if branch_id:
        query += " AND branch_id=?"
        params.append(branch_id)
    if status:
        query += f" AND ({_STATUS_CASE_SQL})=?"
        params.append(status)
    query += " ORDER BY 오더번호 DESC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def get_lead_time_stats() -> pd.DataFrame:
    """공장 발송일 -> 재고(입고) 인식일까지 소요일수를, 발주공장별로 집계."""
    conn = get_conn()
    df = pd.read_sql_query(
        """
        SELECT factory AS 발주공장,
               COUNT(*) AS 입고건수,
               AVG(julianday(stock_date) - julianday(factory_ship_date)) AS 평균리드타임_일
        FROM order_units
        WHERE stock_date IS NOT NULL AND factory_ship_date IS NOT NULL
        GROUP BY factory
        ORDER BY 평균리드타임_일 DESC
        """,
        conn,
    )
    conn.close()
    return df


def list_order_batches(branch_id: str | None = None, start_date: str | None = None, end_date: str | None = None) -> pd.DataFrame:
    conn = get_conn()
    query = """
        SELECT order_no AS 발주번호, branch_id AS 지점, order_date AS 발주일자, model AS 모델, color AS 컬러,
               size AS 사이즈, requested_qty AS 신청수량, confirmed_qty AS 확정수량, cancelled_qty AS 취소수량,
               factory_code AS 공장, note AS 비고
        FROM order_batches
        WHERE 1=1
    """
    params = []
    if branch_id:
        query += " AND branch_id=?"
        params.append(branch_id)
    if start_date:
        query += " AND order_date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND order_date <= ?"
        params.append(end_date)
    query += " ORDER BY 발주일자 DESC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


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
