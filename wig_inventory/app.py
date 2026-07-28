import os
from datetime import date

import altair as alt
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


def apply_database_url_from_secrets():
    """Streamlit Cloud의 secrets에 DATABASE_URL이 있으면 환경변수로 반영한다.
    (db.py는 Streamlit에 의존하지 않도록 os.environ만 바라보게 유지)"""
    if os.environ.get("DATABASE_URL"):
        return
    try:
        url = st.secrets.get("DATABASE_URL")
    except Exception:
        url = None
    if url:
        os.environ["DATABASE_URL"] = url


require_login()
apply_database_url_from_secrets()
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
        results = []
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
                results.append({"파일명": name, "상태": "실패", "비고": str(e)})
                continue

            valid, dropped = parsing.transform_stock(
                df, branch_col, model_col, color_col, size_col, qty_col, category_col
            )
            if valid.empty:
                st.error(f"'{name}': 업로드할 유효한 데이터가 없습니다.")
                db.log_upload(name, "inventory", 0, "실패", "유효한 행 없음")
                results.append({"파일명": name, "상태": "실패", "비고": "유효한 행 없음"})
                continue
            valid_frames.append(valid)
            total_dropped += dropped
            db.log_upload(name, "inventory", len(valid), "성공", None)
            results.append({"파일명": name, "상태": "성공", "비고": f"{len(valid)}건 (제외 {dropped}건)"})

        if valid_frames:
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
                for r in results:
                    if r["상태"] == "성공":
                        r["상태"] = "실패"
                        r["비고"] = f"DB 저장 오류: {e}"

        if results:
            st.subheader("업로드 결과")
            st.dataframe(pd.DataFrame(results), width="stretch")


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
        valid_frames = []
        total_dropped = 0
        results = []
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
                results.append({"파일명": name, "상태": "실패", "비고": str(e)})
                continue

            valid, dropped = parsing.transform_sales(
                df, month_col, branch_code_col, branch_name_col, model_col, color_col, size_col, qty_col,
                amount_col,
            )
            if valid.empty:
                st.error(f"'{name}': 업로드할 유효한 데이터가 없습니다. 컬럼 또는 판매월 형식을 확인해주세요.")
                db.log_upload(name, "sales", 0, "실패", "유효한 행 없음")
                results.append({"파일명": name, "상태": "실패", "비고": "유효한 행 없음"})
                continue
            valid_frames.append(valid)
            total_dropped += dropped
            db.log_upload(name, "sales", len(valid), "성공", None)
            results.append({"파일명": name, "상태": "성공", "비고": f"{len(valid)}건 (제외 {dropped}건)"})

        # 파일들을 합친 뒤 한 번에 저장해야, 같은 판매월을 포함한 여러 파일을 동시에 올릴 때
        # 파일별로 따로 저장하면서 서로의 데이터를 덮어써 사라지는 문제(월 단위 overwrite-on-reupload)를 막을 수 있다.
        if valid_frames:
            try:
                combined = pd.concat(valid_frames, ignore_index=True)
                row_count, months = db.save_sales_upload(combined)
                st.success(f"총 {row_count}건 업로드 완료 (대상 월: {', '.join(sorted(months))})")
                if total_dropped:
                    st.warning(f"필수 값이 비어있거나 판매월 형식이 잘못된 {total_dropped}건은 제외되었습니다.")
            except Exception as e:
                st.error(f"업로드 처리 중 오류가 발생했습니다: {e}")
                for r in results:
                    if r["상태"] == "성공":
                        r["상태"] = "실패"
                        r["비고"] = f"DB 저장 오류: {e}"

        if results:
            st.subheader("업로드 결과")
            st.dataframe(pd.DataFrame(results), width="stretch")


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
        valid_frames = []
        total_dropped = 0
        results = []
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
                results.append({"파일명": name, "상태": "실패", "비고": str(e)})
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
                results.append({"파일명": name, "상태": "실패", "비고": "유효한 행 없음"})
                continue
            valid_frames.append(valid)
            total_dropped += dropped
            db.log_upload(name, "order_batch", len(valid), "성공", None)
            results.append({"파일명": name, "상태": "성공", "비고": f"{len(valid)}건 (제외 {dropped}건)"})

        # 같은 발주번호가 여러 파일에 걸쳐 있을 때 파일별로 따로 저장하면 서로 덮어써 사라지므로,
        # 합친 뒤 한 번에 저장한다 (판매현황 업로드와 동일한 이유).
        if valid_frames:
            try:
                combined = pd.concat(valid_frames, ignore_index=True)
                row_count = db.save_order_batches(combined)
                st.success(f"총 {row_count}건 업로드 완료 (발주번호 {combined['order_no'].nunique()}건)")
                if total_dropped:
                    st.warning(f"필수 값이 비어있는 {total_dropped}건은 제외되었습니다.")
            except Exception as e:
                st.error(f"업로드 처리 중 오류가 발생했습니다: {e}")
                for r in results:
                    if r["상태"] == "성공":
                        r["상태"] = "실패"
                        r["비고"] = f"DB 저장 오류: {e}"

        if results:
            st.subheader("업로드 결과")
            st.dataframe(pd.DataFrame(results), width="stretch")


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
        results = []
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
                results.append({"파일명": name, "상태": "실패", "비고": str(e)})
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
                results.append({"파일명": name, "상태": "실패", "비고": "유효한 행 없음"})
                continue
            try:
                row_count = db.save_order_units(valid)
                db.log_upload(name, "order_unit", row_count, "성공", None)
                total_rows += row_count
                total_dropped += dropped
                results.append({"파일명": name, "상태": "성공", "비고": f"{row_count}건 (제외 {dropped}건)"})
            except Exception as e:
                db.log_upload(name, "order_unit", 0, "실패", str(e))
                st.error(f"'{name}' 처리 중 오류가 발생했습니다: {e}")
                results.append({"파일명": name, "상태": "실패", "비고": f"DB 저장 오류: {e}"})

        if total_rows:
            st.success(f"총 {total_rows}건 업로드(갱신) 완료")
        if total_dropped:
            st.warning(f"필수 값이 비어있는 {total_dropped}건은 제외되었습니다.")
        if results:
            st.subheader("업로드 결과")
            st.dataframe(pd.DataFrame(results), width="stretch")


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


# ── 재고회전율 분석 ──────────────────────────────────────────────────────────


def _turnover_bucket(months: float) -> str:
    if months == float("inf"):
        return "판매없음"
    if months < 1:
        return "0~1개월"
    if months < 3:
        return "1~3개월"
    if months < 6:
        return "3~6개월"
    if months < 12:
        return "6~12개월"
    return "12개월+"


_TURNOVER_BUCKET_ORDER = ["0~1개월", "1~3개월", "3~6개월", "6~12개월", "12개월+", "판매없음"]


def _ordered_bar_chart(counts: pd.Series, x_title: str, order: list) -> alt.Chart:
    """value_counts 등으로 만든 Series를 지정한 순서 그대로(알파벳순 재정렬 없이) 막대차트로 그린다."""
    df = counts.rename("건수").rename_axis(x_title).reset_index()
    return (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X(f"{x_title}:N", sort=order, title=None),
            y=alt.Y("건수:Q"),
            tooltip=[x_title, "건수"],
        )
    )


def _top_n_hbar_chart(series: pd.Series, value_title: str, n: int = 15) -> alt.Chart:
    """지점 등 인덱스를 값 기준 내림차순 TOP N 가로 막대차트로 그린다."""
    top = series.sort_values(ascending=False).head(n)
    df = top.rename(value_title).rename_axis("지점").reset_index()
    return (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X(f"{value_title}:Q"),
            y=alt.Y("지점:N", sort="-x"),
            tooltip=["지점", value_title],
        )
    )


def page_turnover_dashboard():
    st.header("재고회전율 분석")
    st.caption(
        "재고소진개월 = 최신 재고수량 ÷ 판매 이력 전체 기간의 월평균 판매수량 "
        "(판매 이력이 없는 조합은 '판매없음'으로 분류)"
    )

    turnover = db.get_turnover_detail()
    if turnover.empty:
        st.info("재고 또는 판매 데이터가 없습니다. '현재고 업로드'와 '판매현황 업로드' 메뉴에서 먼저 데이터를 업로드해주세요.")
        return

    st.subheader("재고회전율(재고소진개월) 분포")
    categories = ["전체"] + sorted(turnover["카테고리"].dropna().unique().tolist())
    sel_category = st.selectbox("카테고리", categories, key="turnover_category_filter")
    filtered = turnover if sel_category == "전체" else turnover[turnover["카테고리"] == sel_category]

    filtered = filtered.copy()
    filtered["구간"] = filtered["재고소진개월"].apply(_turnover_bucket)
    counts = filtered["구간"].value_counts().reindex(_TURNOVER_BUCKET_ORDER, fill_value=0)

    c1, c2 = st.columns([1, 2])
    with c1:
        st.dataframe(counts.rename("건수"), width="stretch")
    with c2:
        st.altair_chart(_ordered_bar_chart(counts, "구간", _TURNOVER_BUCKET_ORDER), width='stretch')

    total = int(counts.sum())
    finite = filtered[filtered["재고소진개월"] != float("inf")]
    if total:
        dead_share = counts.get("판매없음", 0) / total
        dominant_bucket = counts.idxmax()
        st.markdown(
            f"- 전체 {total:,}개 조합 중 가장 많은 구간은 **{dominant_bucket}** ({counts[dominant_bucket]:,}건)입니다.\n"
            f"- 판매 이력이 없는 조합이 **{counts.get('판매없음', 0):,}건 ({dead_share:.1%})** 있습니다."
        )
    if not finite.empty:
        st.caption(
            f"판매 이력이 있는 {len(finite)}개 조합 기준 — 평균 {finite['재고소진개월'].mean():.1f}개월, "
            f"중앙값 {finite['재고소진개월'].median():.1f}개월"
        )

    st.divider()
    st.subheader("지점 간 비교 / 군집")
    st.caption("지점별 총재고수량, 월평균판매합계, 평균재고소진개월을 기준으로 유사한 지점을 그룹화합니다.")

    branch_agg = (
        turnover.groupby("지점")
        .agg(총재고수량=("재고수량", "sum"), 월평균판매합계=("월평균판매", "sum"), 취급모델수=("모델", "count"))
        .reset_index()
    )
    finite_all = turnover[turnover["재고소진개월"] != float("inf")]
    turnover_mean = finite_all.groupby("지점")["재고소진개월"].mean().rename("평균재고소진개월")
    branch_agg = branch_agg.merge(turnover_mean, on="지점", how="left")
    branch_agg["평균재고소진개월"] = branch_agg["평균재고소진개월"].fillna(branch_agg["평균재고소진개월"].median())

    if len(branch_agg) < 4:
        st.info("군집 분석을 하기에 지점 수가 너무 적습니다 (최소 4개 지점 필요).")
        return

    max_k = min(6, len(branch_agg) - 1)
    k = st.slider("군집 수", min_value=2, max_value=max_k, value=min(3, max_k), key="turnover_cluster_k")

    feature_cols = ["총재고수량", "월평균판매합계", "평균재고소진개월"]
    features = branch_agg[feature_cols]
    scaled = (features - features.mean()) / features.std().replace(0, 1)

    from sklearn.cluster import KMeans

    model = KMeans(n_clusters=k, random_state=42, n_init=10)
    branch_agg["군집"] = model.fit_predict(scaled).astype(str)

    c1, c2 = st.columns(2)
    with c1:
        st.dataframe(
            branch_agg.sort_values("군집")[["지점", "군집"] + feature_cols],
            width="stretch",
        )
    with c2:
        st.scatter_chart(branch_agg, x="월평균판매합계", y="평균재고소진개월", color="군집")


# ── 지점별 재고·판매·발주 분석 ────────────────────────────────────────────────

_REORDER_STATUS_ORDER = ["품절(긴급발주)", "재고부족(발주필요)", "정상", "재고과잉(저회전)", "데드스톡(판매없음)"]


def _classify_reorder_status(row) -> str:
    if row["월평균판매"] == 0:
        return "데드스톡(판매없음)"
    if row["재고수량"] == 0:
        return "품절(긴급발주)"
    if row["재고소진개월"] < 1:
        return "재고부족(발주필요)"
    if row["재고소진개월"] <= 12:
        return "정상"
    return "재고과잉(저회전)"


def page_reorder_dashboard():
    st.header("지점별 재고·판매·발주 분석")
    st.caption(
        "지점 x 모델별 재고 상태를 분류하고 권장발주수량을 계산합니다. "
        "목표재고 = 월평균판매 x 2개월 · 권장발주수량 = MAX(0, 목표재고 − 현재고). "
        "월평균판매는 판매 이력이 있는 전체 기간의 평균입니다."
    )

    data = db.get_turnover_detail()
    if data.empty:
        st.info("재고 또는 판매 데이터가 없습니다. '현재고 업로드'와 '판매현황 업로드' 메뉴에서 먼저 데이터를 업로드해주세요.")
        return

    data = data.copy()
    data["상태"] = data.apply(_classify_reorder_status, axis=1)
    data["목표재고"] = (data["월평균판매"] * 2).round(1)
    data["권장발주수량"] = (data["목표재고"] - data["재고수량"]).clip(lower=0).round().astype(int)
    data.loc[data["상태"] == "데드스톡(판매없음)", "권장발주수량"] = 0

    detail_cols = ["지점", "모델", "컬러", "사이즈", "카테고리", "재고수량", "월평균판매", "재고소진개월", "목표재고", "권장발주수량"]

    counts = data["상태"].value_counts().reindex(_REORDER_STATUS_ORDER, fill_value=0)
    total = len(data)
    urgent_cnt = int(counts["품절(긴급발주)"] + counts["재고부족(발주필요)"])
    dead_cnt = int(counts["데드스톡(판매없음)"])
    excess_cnt = int(counts["재고과잉(저회전)"])
    total_reorder_qty = int(data["권장발주수량"].sum())

    branch_summary = (
        data.groupby("지점")
        .agg(
            취급모델수=("모델", "count"),
            총재고수량=("재고수량", "sum"),
            권장발주수량_합계=("권장발주수량", "sum"),
            긴급발주_필요건수=("상태", lambda s: s.isin(["품절(긴급발주)", "재고부족(발주필요)"]).sum()),
            데드스톡_건수=("상태", lambda s: (s == "데드스톡(판매없음)").sum()),
        )
        .reset_index()
        .sort_values("권장발주수량_합계", ascending=False)
    )

    st.subheader("핵심 인사이트")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("전체 지점x모델", f"{total:,}")
    m2.metric("긴급발주 필요", f"{urgent_cnt:,}", f"{urgent_cnt / total:.1%}" if total else None)
    m3.metric("재고과잉", f"{excess_cnt:,}", f"{excess_cnt / total:.1%}" if total else None)
    m4.metric("데드스톡", f"{dead_cnt:,}", f"{dead_cnt / total:.1%}" if total else None)

    insights = []
    if urgent_cnt:
        insights.append(
            f"- 품절/재고부족 **{urgent_cnt:,}건**에 대해 총 **{total_reorder_qty:,}개** 발주가 필요합니다."
        )
    if not branch_summary.empty and branch_summary.iloc[0]["권장발주수량_합계"] > 0:
        top_row = branch_summary.iloc[0]
        insights.append(
            f"- 발주가 가장 시급한 지점은 **{top_row['지점']}**로, 권장발주수량 합계가 "
            f"**{int(top_row['권장발주수량_합계']):,}개**입니다."
        )
    if dead_cnt:
        insights.append(
            f"- **{dead_cnt:,}건 ({dead_cnt / total:.1%})**은 판매 이력이 없는 데드스톡입니다. "
            "재고 재배치나 프로모션·폐기를 검토해보세요."
        )
    if excess_cnt:
        insights.append(
            f"- **{excess_cnt:,}건 ({excess_cnt / total:.1%})**은 재고소진 예상 12개월을 초과하는 저회전 재고입니다."
        )
    if insights:
        st.markdown("\n".join(insights))
    else:
        st.info("특이사항 없이 대부분 정상 재고 범위입니다.")

    st.divider()
    st.subheader("상태별 비중")
    c1, c2 = st.columns([1, 1])
    with c1:
        st.dataframe(counts.rename("건수"), width="stretch")
    with c2:
        status_df = counts.rename("건수").rename_axis("상태").reset_index()
        donut = (
            alt.Chart(status_df)
            .mark_arc(innerRadius=60)
            .encode(
                theta="건수:Q",
                color=alt.Color("상태:N", sort=_REORDER_STATUS_ORDER),
                tooltip=["상태", "건수"],
            )
        )
        st.altair_chart(donut, width='stretch')

    st.divider()
    st.subheader("권장발주수량 TOP 15 지점")
    if total_reorder_qty == 0:
        st.info("발주가 필요한 지점이 없습니다.")
    else:
        st.altair_chart(
            _top_n_hbar_chart(branch_summary.set_index("지점")["권장발주수량_합계"], "권장발주수량_합계"),
            width='stretch',
        )

    st.divider()
    st.subheader("데드스톡 재고량 TOP 15 지점")
    dead_by_branch = data[data["상태"] == "데드스톡(판매없음)"].groupby("지점")["재고수량"].sum()
    if dead_by_branch.empty:
        st.info("데드스톡 재고가 없습니다.")
    else:
        st.altair_chart(_top_n_hbar_chart(dead_by_branch, "재고수량"), width='stretch')

    st.divider()
    st.subheader("지점별 요약 (권장발주수량 합계 내림차순)")
    st.dataframe(branch_summary, width="stretch")

    st.divider()
    st.subheader("긴급발주 상세 (품절 + 재고부족)")
    branch_options = ["전체"] + sorted(data["지점"].unique().tolist())
    sel_branch = st.selectbox("지점", branch_options, key="reorder_branch_filter")
    urgent = data[data["상태"].isin(["품절(긴급발주)", "재고부족(발주필요)"])]
    if sel_branch != "전체":
        urgent = urgent[urgent["지점"] == sel_branch]
    if urgent.empty:
        st.info("긴급발주가 필요한 항목이 없습니다.")
    else:
        st.dataframe(urgent[detail_cols].sort_values("권장발주수량", ascending=False), width="stretch")

    st.divider()
    st.subheader("재고과잉 상세 (저회전, 재고소진예상 12개월 초과)")
    excess = data[data["상태"] == "재고과잉(저회전)"]
    if excess.empty:
        st.info("재고과잉 항목이 없습니다.")
    else:
        st.dataframe(excess[detail_cols].sort_values("재고소진개월", ascending=False), width="stretch")

    st.divider()
    st.subheader("데드스톡 상세 (판매 이력 없음)")
    dead = data[data["상태"] == "데드스톡(판매없음)"]
    if dead.empty:
        st.info("데드스톡 항목이 없습니다.")
    else:
        st.dataframe(dead[["지점", "모델", "컬러", "사이즈", "카테고리", "재고수량"]], width="stretch")

    st.divider()
    st.subheader("전체 상세 데이터")
    st.caption(f"{len(data)}건")
    st.dataframe(data[detail_cols + ["상태"]], width="stretch")
    csv = data[detail_cols + ["상태"]].to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "전체 상세 데이터 CSV 다운로드", data=csv, file_name="지점별_재고판매발주_분석.csv", mime="text/csv"
    )


# ── 업로드 이력 ──────────────────────────────────────────────────────────────


def page_upload_logs():
    st.header("업로드 이력")
    logs = db.list_upload_logs()
    if logs.empty:
        st.info("업로드 이력이 없습니다.")
    else:
        st.dataframe(logs, width="stretch")


UPLOAD_PAGES = {
    "현재고 업로드": page_stock_upload,
    "판매현황 업로드": page_sales_upload,
    "발주 업로드": page_order_batch_upload,
    "입고현황 업로드": page_order_unit_upload,
}
DASHBOARD_PAGES = {
    "재고 대시보드": page_stock_dashboard,
    "판매 트래커": page_sales_dashboard,
    "재고회전율 분석": page_turnover_dashboard,
    "지점별 재고·판매·발주 분석": page_reorder_dashboard,
    "발주 관리": page_order_dashboard,
    "업로드 이력": page_upload_logs,
}
PAGES = {**UPLOAD_PAGES, **DASHBOARD_PAGES}

if st.session_state.get("current_page") not in PAGES:
    st.session_state.current_page = "재고 대시보드"


def _on_upload_select():
    st.session_state.current_page = st.session_state.upload_nav
    st.session_state.dashboard_nav = None


def _on_dashboard_select():
    st.session_state.current_page = st.session_state.dashboard_nav
    st.session_state.upload_nav = None


st.sidebar.title("하이모 기성가발 관리")

st.sidebar.markdown("#### 📤 업로드")
st.sidebar.radio(
    "업로드",
    list(UPLOAD_PAGES.keys()),
    index=list(UPLOAD_PAGES.keys()).index(st.session_state.current_page)
    if st.session_state.current_page in UPLOAD_PAGES
    else None,
    key="upload_nav",
    on_change=_on_upload_select,
    label_visibility="collapsed",
)

st.sidebar.divider()
st.sidebar.markdown("#### 📊 대시보드")
st.sidebar.radio(
    "대시보드",
    list(DASHBOARD_PAGES.keys()),
    index=list(DASHBOARD_PAGES.keys()).index(st.session_state.current_page)
    if st.session_state.current_page in DASHBOARD_PAGES
    else None,
    key="dashboard_nav",
    on_change=_on_dashboard_select,
    label_visibility="collapsed",
)

PAGES[st.session_state.current_page]()
