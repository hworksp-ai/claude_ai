import math
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

DB_DIR = Path(__file__).parent / "data"
DB_PATH = DB_DIR / "wig.db"

_engine: Engine | None = None


def _sanitize(v):
    """pandas가 만드는 float NaN을 파이썬 None으로 바꾼다.
    sqlite3 드라이버는 float('nan') 바인딩을 조용히 NULL로 저장하지만 psycopg2(Postgres)는
    그대로 값으로 저장해버려 두 백엔드의 동작이 달라지므로, DB에 넣기 직전에 명시적으로 정리한다.
    """
    if isinstance(v, float) and math.isnan(v):
        return None
    return v


def _sanitize_dict(d: dict) -> dict:
    return {k: _sanitize(v) for k, v in d.items()}


def _sanitize_dicts(dicts: list) -> list:
    return [_sanitize_dict(d) for d in dicts]


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    DB_DIR.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DB_PATH}"


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(_database_url(), pool_pre_ping=True)
    return _engine


def _is_sqlite() -> bool:
    return get_engine().dialect.name == "sqlite"


def init_db():
    id_pk = "INTEGER PRIMARY KEY AUTOINCREMENT" if _is_sqlite() else "SERIAL PRIMARY KEY"
    statements = [
        """
        CREATE TABLE IF NOT EXISTS branches (
            branch_id TEXT PRIMARY KEY,
            branch_code TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS products (
            product_id TEXT PRIMARY KEY,
            model TEXT NOT NULL,
            color TEXT,
            size INTEGER,
            category TEXT
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS inventory_snapshots (
            id {id_pk},
            snapshot_date TEXT NOT NULL,
            branch_id TEXT NOT NULL REFERENCES branches(branch_id),
            product_id TEXT NOT NULL REFERENCES products(product_id),
            quantity INTEGER NOT NULL,
            UNIQUE(snapshot_date, branch_id, product_id)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS sales (
            id {id_pk},
            sale_month TEXT NOT NULL,
            branch_id TEXT NOT NULL REFERENCES branches(branch_id),
            product_id TEXT NOT NULL REFERENCES products(product_id),
            quantity INTEGER NOT NULL,
            amount INTEGER NOT NULL
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS upload_logs (
            id {id_pk},
            file_name TEXT,
            upload_type TEXT NOT NULL,
            upload_date TEXT NOT NULL,
            row_count INTEGER,
            status TEXT,
            error_message TEXT
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS order_batches (
            id {id_pk},
            order_no TEXT NOT NULL,
            branch_id TEXT NOT NULL REFERENCES branches(branch_id),
            order_date TEXT,
            product_id TEXT NOT NULL REFERENCES products(product_id),
            model TEXT,
            color TEXT,
            size INTEGER,
            na_code TEXT,
            requested_qty INTEGER,
            confirmed_qty INTEGER,
            cancelled_qty INTEGER,
            hq_confirm_date TEXT,
            factory_code TEXT,
            serial_range TEXT,
            factory_accept_date TEXT,
            note TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS order_units (
            order_unit_no TEXT PRIMARY KEY,
            branch_id TEXT NOT NULL REFERENCES branches(branch_id),
            product_id TEXT NOT NULL REFERENCES products(product_id),
            model TEXT,
            color TEXT,
            size INTEGER,
            factory TEXT,
            order_type TEXT,
            factory_ship_date TEXT,
            factory_receive_date TEXT,
            factory_out_date TEXT,
            trade_in_date TEXT,
            trade_ship_date TEXT,
            stock_date TEXT,
            cancel_date TEXT,
            discard_date TEXT
        )
        """,
    ]
    engine = get_engine()
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))


def upsert_branch(branch_id: str, branch_code: str | None = None):
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO branches (branch_id, branch_code) VALUES (:branch_id, :branch_code)
                ON CONFLICT(branch_id) DO UPDATE SET branch_code=COALESCE(excluded.branch_code, branches.branch_code)
                """
            ),
            _sanitize_dict({"branch_id": branch_id, "branch_code": branch_code}),
        )


def upsert_product(product_id: str, model: str, color: str | None, size: int, category: str | None = None):
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO products (product_id, model, color, size, category)
                VALUES (:product_id, :model, :color, :size, :category)
                ON CONFLICT(product_id) DO UPDATE SET category=COALESCE(excluded.category, products.category)
                """
            ),
            _sanitize_dict(
                {"product_id": product_id, "model": model, "color": color, "size": size, "category": category}
            ),
        )


def replace_inventory_snapshots(dates: set, rows: list):
    """Delete existing snapshot rows for the given dates, then insert the new rows (overwrite-on-reupload)."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM inventory_snapshots WHERE snapshot_date=:d"), [{"d": d} for d in dates]
        )
        if rows:
            conn.execute(
                text(
                    """
                    INSERT INTO inventory_snapshots (snapshot_date, branch_id, product_id, quantity)
                    VALUES (:snapshot_date, :branch_id, :product_id, :quantity)
                    """
                ),
                _sanitize_dicts(
                    [
                        {"snapshot_date": r[0], "branch_id": r[1], "product_id": r[2], "quantity": r[3]}
                        for r in rows
                    ]
                ),
            )


def replace_sales(months: set, rows: list):
    """Delete existing sales rows for the given sale_months, then insert the new rows (overwrite-on-reupload)."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM sales WHERE sale_month=:m"), [{"m": m} for m in months])
        if rows:
            conn.execute(
                text(
                    """
                    INSERT INTO sales (sale_month, branch_id, product_id, quantity, amount)
                    VALUES (:sale_month, :branch_id, :product_id, :quantity, :amount)
                    """
                ),
                _sanitize_dicts(
                    [
                        {
                            "sale_month": r[0], "branch_id": r[1], "product_id": r[2], "quantity": r[3],
                            "amount": r[4],
                        }
                        for r in rows
                    ]
                ),
            )


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
        upsert_branch(r["branch"], _sanitize(r["branch_code"]) or None)

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

    engine = get_engine()
    order_nos = list(valid["order_no"].drop_duplicates())
    cols = [
        "order_no", "branch", "order_date", "product_id", "model", "color", "size", "na_code",
        "requested_qty", "confirmed_qty", "cancelled_qty", "hq_confirm_date", "factory_code",
        "serial_range", "factory_accept_date", "note",
    ]
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM order_batches WHERE order_no=:o"), [{"o": o} for o in order_nos])
        conn.execute(
            text(
                """
                INSERT INTO order_batches (
                    order_no, branch_id, order_date, product_id, model, color, size, na_code,
                    requested_qty, confirmed_qty, cancelled_qty, hq_confirm_date, factory_code,
                    serial_range, factory_accept_date, note
                ) VALUES (
                    :order_no, :branch, :order_date, :product_id, :model, :color, :size, :na_code,
                    :requested_qty, :confirmed_qty, :cancelled_qty, :hq_confirm_date, :factory_code,
                    :serial_range, :factory_accept_date, :note
                )
                """
            ),
            _sanitize_dicts([dict(zip(cols, row)) for row in valid[cols].itertuples(index=False, name=None)]),
        )
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

    engine = get_engine()
    cols = [
        "order_unit_no", "branch", "product_id", "model", "color", "size", "factory", "order_type",
        "factory_ship_date", "factory_receive_date", "factory_out_date", "trade_in_date",
        "trade_ship_date", "stock_date", "cancel_date", "discard_date",
    ]
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO order_units (
                    order_unit_no, branch_id, product_id, model, color, size, factory, order_type,
                    factory_ship_date, factory_receive_date, factory_out_date, trade_in_date,
                    trade_ship_date, stock_date, cancel_date, discard_date
                ) VALUES (
                    :order_unit_no, :branch, :product_id, :model, :color, :size, :factory, :order_type,
                    :factory_ship_date, :factory_receive_date, :factory_out_date, :trade_in_date,
                    :trade_ship_date, :stock_date, :cancel_date, :discard_date
                )
                ON CONFLICT(order_unit_no) DO UPDATE SET
                    branch_id=excluded.branch_id, product_id=excluded.product_id, model=excluded.model,
                    color=excluded.color, size=excluded.size, factory=excluded.factory,
                    order_type=excluded.order_type, factory_ship_date=excluded.factory_ship_date,
                    factory_receive_date=excluded.factory_receive_date, factory_out_date=excluded.factory_out_date,
                    trade_in_date=excluded.trade_in_date, trade_ship_date=excluded.trade_ship_date,
                    stock_date=excluded.stock_date, cancel_date=excluded.cancel_date,
                    discard_date=excluded.discard_date
                """
            ),
            _sanitize_dicts([dict(zip(cols, row)) for row in valid[cols].itertuples(index=False, name=None)]),
        )
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
    engine = get_engine()
    return pd.read_sql_query(
        text(f"SELECT {_STATUS_CASE_SQL} AS 진행상태, COUNT(*) AS 건수 FROM order_units GROUP BY 진행상태 ORDER BY 건수 DESC"),
        engine,
    )


def list_order_units(branch_id: str | None = None, status: str | None = None) -> pd.DataFrame:
    engine = get_engine()
    query = f"""
        SELECT order_unit_no AS 오더번호, branch_id AS 지점, model AS 모델, color AS 컬러, size AS 사이즈,
               factory AS 발주공장, order_type AS 오더구분,
               COALESCE(factory_ship_date, '') AS 공장발송일, COALESCE(stock_date, '') AS 입고일,
               COALESCE(cancel_date, '') AS 취소일, COALESCE(discard_date, '') AS 폐기일,
               {_STATUS_CASE_SQL} AS 진행상태
        FROM order_units
        WHERE 1=1
    """
    params = {}
    if branch_id:
        query += " AND branch_id=:branch_id"
        params["branch_id"] = branch_id
    if status:
        query += f" AND ({_STATUS_CASE_SQL})=:status"
        params["status"] = status
    query += " ORDER BY 오더번호 DESC"
    return pd.read_sql_query(text(query), engine, params=params)


def get_lead_time_stats() -> pd.DataFrame:
    """공장 발송일 -> 재고(입고) 인식일까지 소요일수를, 발주공장별로 집계 (dialect 이식성을 위해 pandas에서 계산)."""
    engine = get_engine()
    df = pd.read_sql_query(
        text(
            """
            SELECT factory AS 발주공장, stock_date, factory_ship_date
            FROM order_units
            WHERE stock_date IS NOT NULL AND factory_ship_date IS NOT NULL
            """
        ),
        engine,
    )
    if df.empty:
        return pd.DataFrame(columns=["발주공장", "입고건수", "평균리드타임_일"])
    df["lead_days"] = (pd.to_datetime(df["stock_date"]) - pd.to_datetime(df["factory_ship_date"])).dt.days
    result = (
        df.groupby("발주공장")["lead_days"]
        .agg(입고건수="count", 평균리드타임_일="mean")
        .reset_index()
        .sort_values("평균리드타임_일", ascending=False)
    )
    return result


def list_order_batches(
    branch_id: str | None = None, start_date: str | None = None, end_date: str | None = None
) -> pd.DataFrame:
    engine = get_engine()
    query = """
        SELECT order_no AS 발주번호, branch_id AS 지점, order_date AS 발주일자, model AS 모델, color AS 컬러,
               size AS 사이즈, requested_qty AS 신청수량, confirmed_qty AS 확정수량, cancelled_qty AS 취소수량,
               factory_code AS 공장, note AS 비고
        FROM order_batches
        WHERE 1=1
    """
    params = {}
    if branch_id:
        query += " AND branch_id=:branch_id"
        params["branch_id"] = branch_id
    if start_date:
        query += " AND order_date >= :start_date"
        params["start_date"] = start_date
    if end_date:
        query += " AND order_date <= :end_date"
        params["end_date"] = end_date
    query += " ORDER BY 발주일자 DESC"
    return pd.read_sql_query(text(query), engine, params=params)


def log_upload(file_name: str, upload_type: str, row_count: int, status: str, error_message: str | None):
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO upload_logs (file_name, upload_type, upload_date, row_count, status, error_message)
                VALUES (:file_name, :upload_type, :upload_date, :row_count, :status, :error_message)
                """
            ),
            {
                "file_name": file_name,
                "upload_type": upload_type,
                "upload_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "row_count": row_count,
                "status": status,
                "error_message": error_message,
            },
        )


def list_snapshot_dates():
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT DISTINCT snapshot_date FROM inventory_snapshots ORDER BY snapshot_date DESC")
        ).mappings().all()
    return [r["snapshot_date"] for r in rows]


def list_branches():
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT branch_id FROM branches ORDER BY branch_id")).mappings().all()
    return [(r["branch_id"], r["branch_id"]) for r in rows]


def list_products(category: str | None = None, model_search: str | None = None):
    engine = get_engine()
    query = "SELECT product_id, model, color, size FROM products WHERE 1=1"
    params = {}
    if category:
        query += " AND category=:category"
        params["category"] = category
    if model_search:
        query += " AND model LIKE :model_search"
        params["model_search"] = f"%{model_search}%"
    query += " ORDER BY model, color, size"
    with engine.connect() as conn:
        rows = conn.execute(text(query), params).mappings().all()
    return [(r["product_id"], f"{r['model']} ({r['color'] or '-'}/{r['size']})") for r in rows]


def list_categories():
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT DISTINCT category FROM products WHERE category IS NOT NULL ORDER BY category")
        ).mappings().all()
    return [r["category"] for r in rows]


def get_inventory_branch_totals(snapshot_date: str) -> pd.DataFrame:
    """지점별 총 재고 수량 (전체 상품 합계) - 대시보드 기본 요약용."""
    engine = get_engine()
    return pd.read_sql_query(
        text(
            """
            SELECT branch_id AS 지점, SUM(quantity) AS 총재고수량
            FROM inventory_snapshots
            WHERE snapshot_date = :snapshot_date
            GROUP BY branch_id
            ORDER BY 총재고수량 DESC
            """
        ),
        engine,
        params={"snapshot_date": snapshot_date},
    )


def get_inventory_category_pivot(snapshot_date: str) -> pd.DataFrame:
    """지점 x 카테고리(gubun) 재고 합계 - 컬럼 수가 적어 안전하게 렌더링 가능."""
    engine = get_engine()
    df = pd.read_sql_query(
        text(
            """
            SELECT s.branch_id AS 지점, COALESCE(p.category, '미분류') AS 카테고리, s.quantity AS 수량
            FROM inventory_snapshots s
            JOIN products p ON p.product_id = s.product_id
            WHERE s.snapshot_date = :snapshot_date
            """
        ),
        engine,
        params={"snapshot_date": snapshot_date},
    )
    if df.empty:
        return df
    return df.pivot_table(index="지점", columns="카테고리", values="수량", fill_value=0, aggfunc="sum")


def get_inventory_pivot(snapshot_date: str, category: str | None = None, model_search: str | None = None) -> pd.DataFrame:
    """지점 x 상품 재고 피벗. 카테고리/모델 검색으로 좁혀서 호출해야 렌더링 가능한 크기를 유지한다."""
    engine = get_engine()
    query = """
        SELECT s.branch_id AS 지점,
               (p.model || ' (' || COALESCE(p.color, '-') || '/' || CAST(p.size AS TEXT) || ')') AS 상품,
               s.quantity AS 수량
        FROM inventory_snapshots s
        JOIN products p ON p.product_id = s.product_id
        WHERE s.snapshot_date = :snapshot_date
    """
    params = {"snapshot_date": snapshot_date}
    if category:
        query += " AND p.category = :category"
        params["category"] = category
    if model_search:
        query += " AND p.model LIKE :model_search"
        params["model_search"] = f"%{model_search}%"
    df = pd.read_sql_query(text(query), engine, params=params)
    if df.empty:
        return df
    return df.pivot_table(index="지점", columns="상품", values="수량", fill_value=0, aggfunc="sum")


def get_inventory_trend(branch_id: str, product_id: str) -> pd.DataFrame:
    engine = get_engine()
    return pd.read_sql_query(
        text(
            """
            SELECT snapshot_date, quantity
            FROM inventory_snapshots
            WHERE branch_id=:branch_id AND product_id=:product_id
            ORDER BY snapshot_date
            """
        ),
        engine,
        params={"branch_id": branch_id, "product_id": product_id},
    )


def get_sales_months():
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT DISTINCT sale_month FROM sales ORDER BY sale_month")).mappings().all()
    return [r["sale_month"] for r in rows]


def get_branch_ranking(start_month: str, end_month: str) -> pd.DataFrame:
    engine = get_engine()
    return pd.read_sql_query(
        text(
            """
            SELECT branch_id AS 지점, SUM(amount) AS 판매금액, SUM(quantity) AS 판매수량
            FROM sales
            WHERE sale_month BETWEEN :start_month AND :end_month
            GROUP BY branch_id
            ORDER BY 판매금액 DESC
            """
        ),
        engine,
        params={"start_month": start_month, "end_month": end_month},
    )


def get_monthly_trend(branch_id: str | None = None) -> pd.DataFrame:
    engine = get_engine()
    if branch_id:
        return pd.read_sql_query(
            text(
                """
                SELECT sale_month, SUM(amount) AS amount, SUM(quantity) AS quantity
                FROM sales WHERE branch_id=:branch_id GROUP BY sale_month ORDER BY sale_month
                """
            ),
            engine,
            params={"branch_id": branch_id},
        )
    return pd.read_sql_query(
        text(
            """
            SELECT sale_month, SUM(amount) AS amount, SUM(quantity) AS quantity
            FROM sales GROUP BY sale_month ORDER BY sale_month
            """
        ),
        engine,
    )


def get_branch_comparison(start_month: str, end_month: str, metric: str = "amount") -> pd.DataFrame:
    col = "amount" if metric == "amount" else "quantity"
    engine = get_engine()
    df = pd.read_sql_query(
        text(
            f"""
            SELECT sale_month, branch_id, SUM({col}) AS value
            FROM sales
            WHERE sale_month BETWEEN :start_month AND :end_month
            GROUP BY sale_month, branch_id
            """
        ),
        engine,
        params={"start_month": start_month, "end_month": end_month},
    )
    if df.empty:
        return df
    return df.pivot_table(index="sale_month", columns="branch_id", values="value", fill_value=0)


def list_upload_logs() -> pd.DataFrame:
    engine = get_engine()
    return pd.read_sql_query(
        text(
            "SELECT file_name, upload_type, upload_date, row_count, status, error_message "
            "FROM upload_logs ORDER BY upload_date DESC"
        ),
        engine,
    )
