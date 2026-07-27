from datetime import date

import pandas as pd
import streamlit as st

import db
import parsing
from parsing import MissingColumnError, build_lookup, require_col

st.set_page_config(page_title="기성가발 관리", page_icon="💇", layout="wide")
db.init_db()


# ── 재고 업로드 ──────────────────────────────────────────────────────────────


def page_stock_upload():
    st.header("현재고 업로드")
    st.caption(
        "ERP '재고현황' 엑셀 파일을 업로드하세요. "
        "필요 컬럼: 사업장, MODEL NAME, COLOR NAME, 둘레 SIZE, 재고수량 (gubun은 선택)."
    )

    uploaded = st.file_uploader("현재고 엑셀 파일", type=["xlsx", "xls"], key="stock_uploader")
    if not uploaded:
        return

    try:
        df = pd.read_excel(uploaded)
    except Exception as e:
        st.error(f"파일을 읽는 중 오류가 발생했습니다: {e}")
        return

    lookup = build_lookup(df)
    try:
        branch_col = require_col(lookup, "사업장", "사업장")
        model_col = require_col(lookup, "MODEL NAME", "MODEL NAME")
        color_col = require_col(lookup, "COLOR NAME", "COLOR NAME")
        size_col = require_col(lookup, "둘레 SIZE", "둘레 SIZE")
        qty_col = require_col(lookup, "재고수량", "재고수량")
        category_col = lookup.get(parsing.normalize_key("gubun"))
    except MissingColumnError as e:
        st.error(str(e))
        st.write("업로드된 파일의 컬럼:", list(df.columns))
        return

    st.subheader("미리보기")
    st.dataframe(df.head(20), width="stretch")

    snapshot_date = st.date_input("재고 기준일", value=date.today())

    if st.button("업로드 확정", type="primary", key="stock_confirm"):
        valid, dropped = parsing.transform_stock(
            df, branch_col, model_col, color_col, size_col, qty_col, category_col
        )
        if valid.empty:
            st.error("업로드할 유효한 데이터가 없습니다. 컬럼을 확인해주세요.")
            db.log_upload(uploaded.name, "inventory", 0, "실패", "유효한 행 없음")
            return
        try:
            snap_str = snapshot_date.strftime("%Y-%m-%d")
            row_count = db.save_stock_upload(valid, snap_str)
            db.log_upload(uploaded.name, "inventory", row_count, "성공", None)
            st.success(f"{row_count}건 업로드 완료 (기준일: {snap_str})")
            if dropped:
                st.warning(f"지점/모델/수량 값이 비어있는 {dropped}건은 제외되었습니다.")
        except Exception as e:
            db.log_upload(uploaded.name, "inventory", 0, "실패", str(e))
            st.error(f"업로드 처리 중 오류가 발생했습니다: {e}")


# ── 판매 업로드 ──────────────────────────────────────────────────────────────


def page_sales_upload():
    st.header("판매현황 업로드")
    st.caption(
        "ERP '판매현황' 엑셀 파일을 업로드하세요. "
        "필요 컬럼: 판매월, 지점코드, 지점명, 모델, 컬러, 사이즈, 수량, 금액."
    )

    uploaded = st.file_uploader("판매현황 엑셀 파일", type=["xlsx", "xls"], key="sales_uploader")
    if not uploaded:
        return

    try:
        df = pd.read_excel(uploaded)
    except Exception as e:
        st.error(f"파일을 읽는 중 오류가 발생했습니다: {e}")
        return

    lookup = build_lookup(df)
    try:
        month_col = require_col(lookup, "판매월", "판매월")
        branch_code_col = require_col(lookup, "지점코드", "지점코드")
        branch_name_col = require_col(lookup, "지점명", "지점명")
        model_col = require_col(lookup, "모델", "모델")
        color_col = require_col(lookup, "컬러", "컬러")
        size_col = require_col(lookup, "사이즈", "사이즈")
        qty_col = require_col(lookup, "수량", "수량")
        amount_col = require_col(lookup, "금액", "금액")
    except MissingColumnError as e:
        st.error(str(e))
        st.write("업로드된 파일의 컬럼:", list(df.columns))
        return

    st.subheader("미리보기")
    st.dataframe(df.head(20), width="stretch")

    if st.button("업로드 확정", type="primary", key="sales_confirm"):
        valid, dropped = parsing.transform_sales(
            df, month_col, branch_code_col, branch_name_col, model_col, color_col, size_col, qty_col, amount_col
        )
        if valid.empty:
            st.error("업로드할 유효한 데이터가 없습니다. 컬럼 또는 판매월 형식을 확인해주세요.")
            db.log_upload(uploaded.name, "sales", 0, "실패", "유효한 행 없음")
            return
        try:
            row_count, months = db.save_sales_upload(valid)
            db.log_upload(uploaded.name, "sales", row_count, "성공", None)
            st.success(f"{row_count}건 업로드 완료 (대상 월: {', '.join(sorted(months))})")
            if dropped:
                st.warning(f"필수 값이 비어있거나 판매월 형식이 잘못된 {dropped}건은 제외되었습니다.")
        except Exception as e:
            db.log_upload(uploaded.name, "sales", 0, "실패", str(e))
            st.error(f"업로드 처리 중 오류가 발생했습니다: {e}")


# ── 재고 대시보드 ────────────────────────────────────────────────────────────


def page_stock_dashboard():
    st.header("지점별 재고 현황")

    dates = db.list_snapshot_dates()
    if not dates:
        st.info("아직 업로드된 재고 데이터가 없습니다. '현재고 업로드' 메뉴에서 재고 엑셀을 업로드해주세요.")
        return

    selected_date = st.selectbox("기준일", dates, index=0)
    threshold = st.number_input("재고 부족 임계값 (이 값 미만이면 강조 표시)", min_value=0, value=5)

    pivot = db.get_inventory_pivot(selected_date)
    if pivot.empty:
        st.info("선택한 기준일에 데이터가 없습니다.")
    else:
        def highlight_low(v):
            return "background-color: #ffcdd2" if isinstance(v, (int, float)) and v < threshold else ""

        st.dataframe(pivot.style.map(highlight_low), width="stretch")

    st.divider()
    st.subheader("지점/상품별 재고 추이")
    branches = db.list_branches()
    products = db.list_products()
    if not branches or not products:
        return

    c1, c2 = st.columns(2)
    with c1:
        sel_branch = st.selectbox("지점 선택", branches, format_func=lambda b: b[1])
    with c2:
        sel_product = st.selectbox("상품 선택", products, format_func=lambda p: p[1])

    trend = db.get_inventory_trend(sel_branch[0], sel_product[0])
    if trend.empty:
        st.info("선택한 지점/상품의 재고 이력이 없습니다.")
    else:
        st.line_chart(trend.set_index("snapshot_date")["quantity"])


# ── 판매 트래커 ──────────────────────────────────────────────────────────────


def page_sales_dashboard():
    st.header("지점별 판매 트래커")

    months = db.get_sales_months()
    if not months:
        st.info("아직 업로드된 판매 데이터가 없습니다. '판매현황 업로드' 메뉴에서 판매 엑셀을 업로드해주세요.")
        return

    c1, c2 = st.columns(2)
    with c1:
        start_month = st.selectbox("시작 월", months, index=0)
    with c2:
        end_month = st.selectbox("종료 월", months, index=len(months) - 1)

    if start_month > end_month:
        st.error("시작 월이 종료 월보다 늦을 수 없습니다.")
        return

    st.subheader("지점 순위")
    ranking = db.get_branch_ranking(start_month, end_month)
    if ranking.empty:
        st.info("선택한 기간에 데이터가 없습니다.")
    else:
        st.dataframe(ranking, width="stretch")
        st.bar_chart(ranking.set_index("지점")["판매금액"])

    st.divider()
    st.subheader("기간별 추이")
    branch_options = ["전체"] + [b[0] for b in db.list_branches()]
    sel = st.selectbox("지점 선택 (추이)", branch_options)
    trend = db.get_monthly_trend(None if sel == "전체" else sel)
    if trend.empty:
        st.info("데이터가 없습니다.")
    else:
        st.line_chart(trend.set_index("sale_month")[["amount"]])

    st.divider()
    st.subheader("지점 간 비교")
    metric = st.radio(
        "지표", ["amount", "quantity"], horizontal=True, format_func=lambda m: "판매금액" if m == "amount" else "판매수량"
    )
    comparison = db.get_branch_comparison(start_month, end_month, metric)
    if comparison.empty:
        st.info("선택한 기간에 데이터가 없습니다.")
    else:
        st.line_chart(comparison)


# ── 업로드 이력 ──────────────────────────────────────────────────────────────


def page_upload_logs():
    st.header("업로드 이력")
    logs = db.list_upload_logs()
    if logs.empty:
        st.info("업로드 이력이 없습니다.")
    else:
        st.dataframe(logs, width="stretch")


PAGES = {
    "현재고 업로드": page_stock_upload,
    "판매현황 업로드": page_sales_upload,
    "재고 대시보드": page_stock_dashboard,
    "판매 트래커": page_sales_dashboard,
    "업로드 이력": page_upload_logs,
}

st.sidebar.title("하이모 기성가발 관리")
selected_page = st.sidebar.radio("메뉴", list(PAGES.keys()))
PAGES[selected_page]()
