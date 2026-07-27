"""Pure data-transformation helpers for ERP excel uploads (no Streamlit dependency, so they can be unit-tested directly)."""

import pandas as pd


def normalize_key(col) -> str:
    return str(col).strip().replace(" ", "").lower()


def build_lookup(df: pd.DataFrame) -> dict:
    return {normalize_key(c): c for c in df.columns}


class MissingColumnError(ValueError):
    pass


def require_col(lookup: dict, key: str, label: str) -> str:
    norm_key = normalize_key(key)
    if norm_key not in lookup:
        raise MissingColumnError(f"'{label}' 컬럼을 찾을 수 없습니다. (필요한 컬럼: {key})")
    return lookup[norm_key]


def make_product_id(model: str, color: str, size: int) -> str:
    return f"{model}|{color}|{size}"


def parse_date_series(s: pd.Series) -> pd.Series:
    """ERP 파일에서 빈 날짜는 공백(' ') 문자열로 채워져 있어, 공백을 NaT로 바꾼 뒤 'YYYY-MM-DD' 문자열로 정규화한다."""
    cleaned = s.astype(str).str.strip()
    cleaned = cleaned.where(cleaned != "", None)
    parsed = pd.to_datetime(cleaned, errors="coerce")
    return parsed.dt.strftime("%Y-%m-%d")


def transform_stock(
    df: pd.DataFrame,
    branch_col: str,
    model_col: str,
    color_col: str,
    size_col: str,
    qty_col: str,
    category_col: str | None,
) -> tuple[pd.DataFrame, int]:
    """Returns (valid_rows, dropped_count). valid_rows has columns:
    branch, model, color, size, quantity, category, product_id
    """
    work = pd.DataFrame(
        {
            "branch": df[branch_col].astype(str).str.strip(),
            "model": df[model_col].astype(str).str.strip(),
            "color": df[color_col].astype(str).str.strip(),
            "size": pd.to_numeric(df[size_col], errors="coerce"),
            "quantity": pd.to_numeric(df[qty_col], errors="coerce"),
        }
    )
    work["category"] = df[category_col].astype(str).str.strip() if category_col else None

    total = len(work)
    valid = work.dropna(subset=["branch", "model", "quantity"])
    valid = valid[(valid["branch"] != "") & (valid["model"] != "")].copy()
    valid["size"] = valid["size"].fillna(0).astype(int)
    valid["quantity"] = valid["quantity"].astype(int)
    valid["product_id"] = [
        make_product_id(m, c, s) for m, c, s in zip(valid["model"], valid["color"].fillna(""), valid["size"])
    ]
    dropped = total - len(valid)

    # ERP 파일에 동일 지점+상품 조합이 여러 행(예: 별도 로트/창고)으로 나뉘어 있는 경우가 있어 수량을 합산한다.
    valid = valid.groupby(["branch", "product_id"], as_index=False).agg(
        {"model": "first", "color": "first", "size": "first", "category": "first", "quantity": "sum"}
    )
    return valid, dropped


def transform_sales(
    df: pd.DataFrame,
    month_col: str,
    branch_code_col: str,
    branch_name_col: str,
    model_col: str,
    color_col: str,
    size_col: str,
    qty_col: str,
    amount_col: str,
) -> tuple[pd.DataFrame, int]:
    """Returns (valid_rows, dropped_count). valid_rows has columns:
    sale_month, branch, branch_code, model, color, size, quantity, amount, product_id
    """
    work = pd.DataFrame(
        {
            "month_raw": df[month_col].astype(str).str.strip().str.lstrip("'"),
            "branch_code": df[branch_code_col].astype(str).str.strip().str.lstrip("'"),
            "branch": df[branch_name_col].astype(str).str.strip(),
            "model": df[model_col].astype(str).str.strip(),
            "color": df[color_col].astype(str).str.strip(),
            "size": pd.to_numeric(df[size_col], errors="coerce"),
            "quantity": pd.to_numeric(df[qty_col], errors="coerce"),
            "amount": pd.to_numeric(df[amount_col], errors="coerce"),
        }
    )
    work["sale_month"] = work["month_raw"].str.replace(r"^(\d{4})(\d{2})$", r"\1-\2", regex=True)

    total = len(work)
    valid = work.dropna(subset=["branch", "model", "quantity", "amount"])
    valid = valid[
        (valid["branch"] != "") & (valid["model"] != "") & valid["sale_month"].str.match(r"^\d{4}-\d{2}$")
    ].copy()
    valid["size"] = valid["size"].fillna(0).astype(int)
    valid["quantity"] = valid["quantity"].astype(int)
    valid["amount"] = valid["amount"].astype(int)
    valid["product_id"] = [
        make_product_id(m, c, s) for m, c, s in zip(valid["model"], valid["color"].fillna(""), valid["size"])
    ]
    dropped = total - len(valid)
    return valid, dropped


def transform_order_batch(
    df: pd.DataFrame,
    order_no_col: str,
    branch_col: str,
    order_date_col: str,
    model_col: str,
    color_col: str,
    size_col: str,
    requested_qty_col: str,
    confirmed_qty_col: str,
    cancelled_qty_col: str,
    na_code_col: str | None,
    hq_confirm_date_col: str | None,
    factory_code_col: str | None,
    serial_range_col: str | None,
    factory_accept_date_col: str | None,
    note_col: str | None,
) -> tuple[pd.DataFrame, int]:
    """발주(order batch) 라인아이템 파일 변환. Returns (valid_rows, dropped_count)."""
    work = pd.DataFrame(
        {
            "order_no": df[order_no_col].astype(str).str.strip(),
            "branch": df[branch_col].astype(str).str.strip(),
            "order_date": parse_date_series(df[order_date_col]),
            "model": df[model_col].astype(str).str.strip(),
            "color": df[color_col].astype(str).str.strip(),
            "size": pd.to_numeric(df[size_col], errors="coerce"),
            "requested_qty": pd.to_numeric(df[requested_qty_col], errors="coerce"),
            "confirmed_qty": pd.to_numeric(df[confirmed_qty_col], errors="coerce"),
            "cancelled_qty": pd.to_numeric(df[cancelled_qty_col], errors="coerce"),
        }
    )
    work["na_code"] = df[na_code_col].astype(str).str.strip() if na_code_col else None
    work["hq_confirm_date"] = parse_date_series(df[hq_confirm_date_col]) if hq_confirm_date_col else None
    work["factory_code"] = df[factory_code_col].astype(str).str.strip() if factory_code_col else None
    work["serial_range"] = df[serial_range_col].astype(str).str.strip() if serial_range_col else None
    work["factory_accept_date"] = (
        parse_date_series(df[factory_accept_date_col]) if factory_accept_date_col else None
    )
    work["note"] = df[note_col].astype(str).str.strip() if note_col else None

    total = len(work)
    valid = work.dropna(subset=["order_no", "branch", "model"])
    valid = valid[(valid["order_no"] != "") & (valid["branch"] != "") & (valid["model"] != "")].copy()
    valid["size"] = valid["size"].fillna(0).astype(int)
    for c in ("requested_qty", "confirmed_qty", "cancelled_qty"):
        valid[c] = valid[c].fillna(0).astype(int)
    valid["product_id"] = [
        make_product_id(m, c, s) for m, c, s in zip(valid["model"], valid["color"].fillna(""), valid["size"])
    ]
    dropped = total - len(valid)
    return valid, dropped


def transform_order_unit(
    df: pd.DataFrame,
    order_unit_no_col: str,
    branch_col: str,
    model_col: str,
    color_col: str,
    size_col: str,
    factory_col: str | None,
    order_type_col: str | None,
    factory_ship_date_col: str | None,
    factory_receive_date_col: str | None,
    factory_out_date_col: str | None,
    trade_in_date_col: str | None,
    trade_ship_date_col: str | None,
    stock_date_col: str,
    cancel_date_col: str | None,
    discard_date_col: str | None,
) -> tuple[pd.DataFrame, int]:
    """발주현황조회(유닛 단위 배송추적) 파일 변환. Returns (valid_rows, dropped_count).

    입고일 기준으로는 '입고일자' 대신 '재고일자'를 사용한다 (두 값이 다를 수 있고, 재고일자가
    실제 재고 반영 시점을 의미한다는 실사용자 확인에 따름).
    """
    work = pd.DataFrame(
        {
            "order_unit_no": df[order_unit_no_col].astype(str).str.strip(),
            "branch": df[branch_col].astype(str).str.strip(),
            "model": df[model_col].astype(str).str.strip(),
            "color": df[color_col].astype(str).str.strip(),
            "size": pd.to_numeric(df[size_col], errors="coerce"),
            "stock_date": parse_date_series(df[stock_date_col]),
        }
    )
    work["factory"] = df[factory_col].astype(str).str.strip() if factory_col else None
    work["order_type"] = df[order_type_col].astype(str).str.strip() if order_type_col else None
    work["factory_ship_date"] = parse_date_series(df[factory_ship_date_col]) if factory_ship_date_col else None
    work["factory_receive_date"] = (
        parse_date_series(df[factory_receive_date_col]) if factory_receive_date_col else None
    )
    work["factory_out_date"] = parse_date_series(df[factory_out_date_col]) if factory_out_date_col else None
    work["trade_in_date"] = parse_date_series(df[trade_in_date_col]) if trade_in_date_col else None
    work["trade_ship_date"] = parse_date_series(df[trade_ship_date_col]) if trade_ship_date_col else None
    work["cancel_date"] = parse_date_series(df[cancel_date_col]) if cancel_date_col else None
    work["discard_date"] = parse_date_series(df[discard_date_col]) if discard_date_col else None

    total = len(work)
    valid = work.dropna(subset=["order_unit_no", "branch", "model"])
    valid = valid[(valid["order_unit_no"] != "") & (valid["branch"] != "") & (valid["model"] != "")].copy()
    valid["size"] = valid["size"].fillna(0).astype(int)
    valid["product_id"] = [
        make_product_id(m, c, s) for m, c, s in zip(valid["model"], valid["color"].fillna(""), valid["size"])
    ]
    dropped = total - len(valid)
    return valid, dropped
