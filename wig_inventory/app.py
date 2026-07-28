import os
from datetime import date

import pandas as pd
import streamlit as st

import db
import parsing
from parsing import MissingColumnError, build_lookup, require_col

st.set_page_config(page_title="기성가발 관리", page_icon="💇", layout="wide")


def get_configured_password() -> str | None:
    try:
        pw = st.secrets.get("APP_PASSWORD")
    except Exception:
        pw = None
    return pw or os.environ.get("WIG_APP_PASSWORD")


def require_login():
    if st.session_state.get("authenticated"):
        return

    configured_password = get_configured_password()
    if not configured_password:
        st.title("하이모 기성가발 관리")
        st.error(
            "접근 비밀번호가 설정되지 않았습니다. "
            "`.streamlit/secrets.toml`에 APP_PASSWORD를 설정하거나 WIG_APP_PASSWORD 환경변수를 지정해주세요."
        )
        st.stop()

    st.title("하이모 기성가발 관리")
    pwd = st.text_input("비밀번호", type="password", key="login_password")
    if st.button("입장", key="login_button"):
        if pwd == configured_password:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("비밀번호가 올바르지 않습니다.")
    st.stop()


require_login()
db.init_db()


# ── 재고 업로드 ──────────────────────────────────────────────────────────────


def page_stock_upload():
    st.header("현재고 업로드")
    st.caption(
        "ERP '재고현황' 엑셀 파일을 업로드하세요 (여러 개 동시 선택 가능). "
        "필요 컬럼: 사업장, MODEL NAME, COLOR NAME, 둘레 SIZE, 재고수량 (gubun은 선택)."
    )

    uploaded_files = st.file_uploader(
        "현재고 엑셀 파일", type=["xlsx", "xls"], key="stock_uploader", accept_multiple_files=True
    )
    if not uploaded_files:
        return

    dfs = {}
    for f in uploaded_files:
        try:
            dfs[f.name] = pd.read_excel(f)
        except Exception as e:
            st.error(f"'{f.name}' 파일을 읽는 중 오류가 발생했습니다: {e}")
            return

    st.subheader("업로드할 파일")
    st.dataframe(
        pd.DataFrame({"파일명": list(dfs.keys()), "행 수": [len(d) for d in dfs.values()]}), width="stretch"
    )

    snapshot_date = st.date_input("재고 기준일 (선택한 모든 파일에 공통 적용)", value=date.today())

    if st.button("업로드 확정", type="primary", key="stock_confirm"):
        snap_str = snapshot_date.strftime("%Y-%m-%d")
        valid_frames = []
        total_dropped = 0
        for name, df in dfs.items():
            lookup = build_lookup(df)
            try:
                branch_col = require_col(lookup, "사업장", "사업장")
                model_col = require_col(lookup, "MODEL NAME", "MODEL NAME")
                color_col = require_col(lookup, "COLOR NAME", "COLOR NAME")
                size_col = require_col(lookup, "둘레 SIZE", "둘레 SIZE")
                qty_col = require_col(lookup, "재고수량", "재고수량")
                category_col = lookup.get(parsing.normalize_key("gubun"))
            except MissingColumnError as e:
                st.error(f"'{name}': {e}")
                db.log_upload(name, "inventory", 0, "실패", str(e))
                continue

            valid, dropped = parsing.transform_stock(
                df, branch_col, model_col, color_col, size_col, qty_col, category_col
            )
            if valid.empty:
                st.error(f"'{name}': 업로드할 유효한 데이터가 없습니다.")
                db.log_upload(name, "inventory", 0, "실패", "유효한 행 없음")
                continue
            valid_frames.append(valid)
            total_dropped += dropped
            db.log_upload(name, "inventory", len(valid), "성공", None)

        if not valid_frames:
            return

        try:
            combined = pd.concat(valid_frames, ignore_index=True)
            combined = combined.groupby(["branch", "product_id"], as_index=False).agg(
                {"model": "first", "color": "first", "size": "first", "category": "first", "quantity": "sum"}
            )
            row_count = db.save_stock_upload(combined, snap_str)
            st.success(f"총 {row_count}건 업로드 완료 (기준일: {snap_str}, 파일 {len(valid_frames)}개)")
            if total_dropped:
                st.warning(f"지점/모델/수량 값이 비어있는 {total_dropped}건은 제외되었습니다.")
        except Exception as e:
            st.error(f"업로드 처리 중 오류가 발생했습니다: {e}")


# ── 판매 업로드 ──────────────────────────────────────────────────────────────


def page_sales_upload():
    st.header("판매현황 업로드")
    st.caption(
        "ERP '판매현황' 엑셀 파일을 업로드하세요 (여러 개 동시 선택 가능, 예: 2025년/2026년 파일을 함께). "
        "필요 컬럼: 판매월, 지점코드, 지점명, 모델, 컬러, 사이즈, 수량, 금액."
    )

    uploaded_files = st.file_uploader(
        "판매현황 엑셀 파일", type=["xlsx", "xls"], key="sales_uploader", accept_multiple_files=True
    )
    if not uploaded_files:
        return

    dfs = {}
    for f in uploaded_files:
        try:
            dfs[f.name] = pd.read_excel(f)
        except Exception as e:
            st.error(f"'{f.name}' 파일을 읽는 중 오류가 발생했습니다: {e}")
            return

    st.subheader("업로드할 파일")
    st.dataframe(
        pd.DataFrame({"파일명": list(dfs.keys()), "행 수": [len(d) for d in dfs.values()]}), width="stretch"
    )

    if st.button("업로드 확정", type="primary", key="sales_confirm"):
        total_rows = 0
        total_dropped = 0
        all_months = set()
        for name, df in dfs.items():
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
                st.error(f"'{name}': {e}")
                db.log_upload(name, "sales", 0, "실패", str(e))
                continue

            valid, dropped = parsing.transform_sales(
                df, month_col, branch_code_col, branch_name_col, model_col, color_col, size_col, qty_col,
                amount_col,
            )
            if valid.empty:
                st.error(f"'{name}': 업로드할 유효한 데이터가 없습니다. 컬럼 또는 판매월 형식을 확인해주세요.")
                db.log_upload(name, "sales", 0, "실패", "유효한 행 없음")
                continue
            try:
                row_count, months = db.save_sales_upload(valid)
                db.log_upload(name, "sales", row_count, "성공", None)
                total_rows += row_count
                total_dropped += dropped
                all_months |= months
            except Exception as e:
                db.log_upload(name, "sales", 0, "실패", str(e))
                st.error(f"'{name}' 처리 중 오류가 발생했습니다: {e}")

        if total_rows:
            st.success(f"총 {total_rows}건 업로드 완료 (대상 월: {', '.join(sorted(all_months))})")
        if total_dropped:
            st.warning(f"필수 값이 비어있거나 판매월 형식이 잘못된 {total_dropped}건은 제외되었습니다.")


# ── 발주 업로드 ──────────────────────────────────────────────────────────────


def page_order_batch_upload():
    st.header("발주 업로드")
    st.caption(
        "ERP '발주' 엑셀 파일을 업로드하세요 (여러 개 동시 선택 가능, 예: 2025년/2026년 파일을 함께). "
        "필요 컬럼: 사업장, 발주일자, 발주번호, MODEL NO, COLOR CODE, 둘레 SIZE, 신청 수량, 확정 수량, 발주 취소수량."
    )

    uploaded_files = st.file_uploader(
        "발주 엑셀 파일", type=["xlsx", "xls"], key="order_batch_uploader", accept_multiple_files=True
    )
    if not uploaded_files:
        return

    dfs = {}
    for f in uploaded_files:
        try:
            dfs[f.name] = pd.read_excel(f)
        except Exception as e:
            st.error(f"'{f.name}' 파일을 읽는 중 오류가 발생했습니다: {e}")
            return

    st.subheader("업로드할 파일")
    st.dataframe(
        pd.DataFrame({"파일명": list(dfs.keys()), "행 수": [len(d) for d in dfs.values()]}), width="stretch"
    )

    if st.button("업로드 확정", type="primary", key="order_batch_confirm"):
        total_rows = 0
        total_dropped = 0
        total_order_nos = set()
        for name, df in dfs.items():
            lookup = build_lookup(df)
            try:
                order_no_col = require_col(lookup, "발주번호", "발주번호")
                branch_col = require_col(lookup, "사업장", "사업장")
                order_date_col = require_col(lookup, "발주일자", "발주일자")
                model_col = require_col(lookup, "MODEL NO", "MODEL NO")
                color_col = require_col(lookup, "COLOR CODE", "COLOR CODE")
                size_col = require_col(lookup, "둘레 SIZE", "둘레 SIZE")
                requested_qty_col = require_col(lookup, "신청 수량", "신청 수량")
                confirmed_qty_col = require_col(lookup, "확정 수량", "확정 수량")
                cancelled_qty_col = require_col(lookup, "발주 취소수량", "발주 취소수량")
            except MissingColumnError as e:
                st.error(f"'{name}': {e}")
                db.log_upload(name, "order_batch", 0, "실패", str(e))
                continue

            na_code_col = lookup.get(parsing.normalize_key("NA CODE"))
            hq_confirm_date_col = lookup.get(parsing.normalize_key("본사 확정일자"))
            factory_code_col = lookup.get(parsing.normalize_key("fact_cd"))
            serial_range_col = lookup.get(parsing.normalize_key("compute_2"))
            factory_accept_date_col = lookup.get(parsing.normalize_key("fact_acpt_dt"))
            note_col = lookup.get(parsing.normalize_key("비 고"))

            valid, dropped = parsing.transform_order_batch(
                df, order_no_col, branch_col, order_date_col, model_col, color_col, size_col,
                requested_qty_col, confirmed_qty_col, cancelled_qty_col, na_code_col, hq_confirm_date_col,
                factory_code_col, serial_range_col, factory_accept_date_col, note_col,
            )
            if valid.empty:
                st.error(f"'{name}': 업로드할 유효한 데이터가 없습니다.")
                db.log_upload(name, "order_batch", 0, "실패", "유효한 행 없음")
                continue
            try:
                row_count = db.save_order_batches(valid)
                db.log_upload(name, "order_batch", row_count, "성공", None)
                total_rows += row_count
                total_dropped += dropped
                total_order_nos |= set(valid["order_no"])
            except Exception as e:
                db.log_upload(name, "order_batch", 0, "실패", str(e))
                st.error(f"'{name}' 처리 중 오류가 발생했습니다: {e}")

        if total_rows:
            st.success(f"총 {total_rows}건 업로드 완료 (발주번호 {len(total_order_nos)}건)")
        if total_dropped:
            st.warning(f"필수 값이 비어있는 {total_dropped}건은 제외되었습니다.")


# ── 입고현황 업로드 ──────────────────────────────────────────────────────────


def page_order_unit_upload():
    st.header("입고현황(발주현황조회) 업로드")
    st.caption(
        "ERP '발주현황조회' 엑셀 파일을 업로드하세요 (여러 개 동시 선택 가능, 예: 2025년/2026년 파일을 함께). "
        "필요 컬럼: 오더번호, 사업장, MODEL NO, COLOR CODE, 둘레 SIZE, 재고일자. "
        "입고일은 '입고일자'가 아닌 '재고일자' 컬럼을 기준으로 인식합니다."
    )

    uploaded_files = st.file_uploader(
        "발주현황조회 엑셀 파일", type=["xlsx", "xls"], key="order_unit_uploader", accept_multiple_files=True
    )
    if not uploaded_files:
        return

    dfs = {}
    for f in uploaded_files:
        try:
            dfs[f.name] = pd.read_excel(f)
        except Exception as e:
            st.error(f"'{f.name}' 파일을 읽는 중 오류가 발생했습니다: {e}")
            return

    st.subheader("업로드할 파일")
    st.dataframe(
        pd.DataFrame({"파일명": list(dfs.keys()), "행 수": [len(d) for d in dfs.values()]}), width="stretch"
    )

    if st.button("업로드 확정", type="primary", key="order_unit_confirm"):
        total_rows = 0
        total_dropped = 0
        for name, df in dfs.items():
            lookup = build_lookup(df)
            try:
                order_unit_no_col = require_col(lookup, "오더번호", "오더번호")
                branch_col = require_col(lookup, "사업장", "사업장")
                model_col = require_col(lookup, "MODEL NO", "MODEL NO")
                color_col = require_col(lookup, "COLOR CODE", "COLOR CODE")
                size_col = require_col(lookup, "둘레 SIZE", "둘레 SIZE")
                stock_date_col = require_col(lookup, "재고일자", "재고일자")
            except MissingColumnError as e:
                st.error(f"'{name}': {e}")
                db.log_upload(name, "order_unit", 0, "실패", str(e))
                continue

            factory_col = lookup.get(parsing.normalize_key("발주공장"))
            order_type_col = lookup.get(parsing.normalize_key("오더구분"))
            factory_ship_date_col = lookup.get(parsing.normalize_key("공장 발송일자"))
            factory_receive_date_col = lookup.get(parsing.normalize_key("공장 접수일자"))
            factory_out_date_col = lookup.get(parsing.normalize_key("공장 출고일자"))
            trade_in_date_col = lookup.get(parsing.normalize_key("무역부 입고일자"))
            trade_ship_date_col = lookup.get(parsing.normalize_key("무역부 선적일자"))
            cancel_date_col = lookup.get(parsing.normalize_key("취소일자"))
            discard_date_col = lookup.get(parsing.normalize_key("폐기일자"))

            valid, dropped = parsing.transform_order_unit(
                df, order_unit_no_col, branch_col, model_col, color_col, size_col, factory_col, order_type_col,
                factory_ship_date_col, factory_receive_date_col, factory_out_date_col, trade_in_date_col,
                trade_ship_date_col, stock_date_col, cancel_date_col, discard_date_col,
            )
            if valid.empty:
                st.error(f"'{name}': 업로드할 유효한 데이터가 없습니다.")
                db.log_upload(name, "order_unit", 0, "실패", "유효한 행 없음")
                continue
            try:
                row_count = db.save_order_units(valid)
                db.log_upload(name, "order_unit", row_count, "성공", None)
                total_rows += row_count
                total_dropped += dropped
            except Exception as e:
                db.log_upload(name, "order_unit", 0, "실패", str(e))
                st.error(f"'{name}' 처리 중 오류가 발생했습니다: {e}")

        if total_rows:
            st.success(f"총 {total_rows}건 업로드(갱신) 완료")
        if total_dropped:
            st.warning(f"필수 값이 비어있는 {total_dropped}건은 제외되었습니다.")


# ── 발주 관리 대시보드 ────────────────────────────────────────────────────────


def page_order_dashboard():
    st.header("발주 관리")

    st.subheader("진행상태별 집계")
    summary = db.get_order_status_summary()
    if summary.empty:
        st.info("아직 업로드된 입고현황 데이터가 없습니다. '입고현황 업로드' 메뉴에서 발주현황조회 엑셀을 업로드해주세요.")
    else:
        c1, c2 = st.columns([1, 2])
        with c1:
            st.dataframe(summary, width="stretch")
        with c2:
            st.bar_chart(summary.set_index("진행상태")["건수"])

    st.divider()
    st.subheader("입고현황 목록")
    branch_options = ["전체"] + [b[0] for b in db.list_branches()]
    status_options = ["전체", "발주대기", "공장발송", "공장접수(생산중)", "공장출고", "무역부입고",
                       "무역부선적(배송중)", "입고완료", "취소", "폐기"]
    c1, c2 = st.columns(2)
    with c1:
        sel_branch = st.selectbox("지점", branch_options, key="order_unit_branch_filter")
    with c2:
        sel_status = st.selectbox("진행상태", status_options, key="order_unit_status_filter")
    units = db.list_order_units(
        None if sel_branch == "전체" else sel_branch, None if sel_status == "전체" else sel_status
    )
    st.dataframe(units, width="stretch")

    st.divider()
    st.subheader("발주 리드타임 (공장 발송 → 입고, 발주공장별 평균)")
    lead = db.get_lead_time_stats()
    if lead.empty:
        st.info("리드타임을 계산할 입고 완료 데이터가 없습니다.")
    else:
        st.dataframe(lead, width="stretch")

    st.divider()
    st.subheader("발주 목록 (배치 단위)")
    branch_sel2 = st.selectbox("지점 ", branch_options, key="order_batch_branch_filter")
    batches = db.list_order_batches(None if branch_sel2 == "전체" else branch_sel2)
    if batches.empty:
        st.info("아직 업로드된 발주 데이터가 없습니다. '발주 업로드' 메뉴에서 발주 엑셀을 업로드해주세요.")
    else:
        st.dataframe(batches, width="stretch")


# ── 재고 대시보드 ────────────────────────────────────────────────────────────


def page_stock_dashboard():
    st.header("지점별 재고 현황")

    dates = db.list_snapshot_dates()
    if not dates:
        st.info("아직 업로드된 재고 데이터가 없습니다. '현재고 업로드' 메뉴에서 재고 엑셀을 업로드해주세요.")
        return

    selected_date = st.selectbox("기준일", dates, index=0)
    threshold = st.number_input("재고 부족 임계값 (이 값 미만이면 강조 표시)", min_value=0, value=5)

    def highlight_low(v):
        return "background-color: #ffcdd2" if isinstance(v, (int, float)) and v < threshold else ""

    st.subheader("지점별 총 재고")
    totals = db.get_inventory_branch_totals(selected_date)
    if totals.empty:
        st.info("선택한 기준일에 데이터가 없습니다.")
    else:
        c1, c2 = st.columns([1, 2])
        with c1:
            st.dataframe(totals.style.map(highlight_low, subset=["총재고수량"]), width="stretch")
        with c2:
            st.bar_chart(totals.set_index("지점")["총재고수량"])

    st.divider()
    st.subheader("카테고리별 지점 재고")
    cat_pivot = db.get_inventory_category_pivot(selected_date)
    if cat_pivot.empty:
        st.info("데이터가 없습니다.")
    else:
        st.dataframe(cat_pivot.style.map(highlight_low), width="stretch")

    st.divider()
    st.subheader("모델 검색으로 상세 재고 조회")
    st.caption("상품 종류가 많아 (2,000개 이상 SKU) 전체를 한 번에 보여주지 않습니다. 카테고리/모델명으로 좁혀서 조회하세요.")
    categories = ["전체"] + db.list_categories()
    c1, c2 = st.columns(2)
    with c1:
        sel_category = st.selectbox("카테고리", categories, key="stock_category_filter")
    with c2:
        model_search = st.text_input("모델명 검색 (부분 일치)", key="stock_model_search")

    detail_pivot = db.get_inventory_pivot(
        selected_date, None if sel_category == "전체" else sel_category, model_search or None
    )
    if detail_pivot.empty:
        st.info("조건에 맞는 재고 데이터가 없습니다. 카테고리 또는 모델명을 지정해보세요.")
    elif detail_pivot.shape[1] > 60:
        st.warning(f"조건에 맞는 상품이 {detail_pivot.shape[1]}개로 너무 많습니다. 모델명을 더 좁혀서 검색해주세요.")
    else:
        st.dataframe(detail_pivot.style.map(highlight_low), width="stretch")

    st.divider()
    st.subheader("지점/상품별 재고 추이")
    branches = db.list_branches()
    products = db.list_products(None if sel_category == "전체" else sel_category, model_search or None)
    if not branches or not products:
        st.info("추이를 조회할 상품이 없습니다. 위에서 카테고리/모델명을 지정해주세요.")
        return
    if len(products) > 200:
        st.caption("상품이 많아 목록이 길 수 있습니다. 모델명을 좁혀서 검색하면 더 편리합니다.")

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
    "발주 업로드": page_order_batch_upload,
    "입고현황 업로드": page_order_unit_upload,
    "재고 대시보드": page_stock_dashboard,
    "판매 트래커": page_sales_dashboard,
    "발주 관리": page_order_dashboard,
    "업로드 이력": page_upload_logs,
}

st.sidebar.title("하이모 기성가발 관리")
selected_page = st.sidebar.radio("메뉴", list(PAGES.keys()))
PAGES[selected_page]()
