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
