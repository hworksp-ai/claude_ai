import os
import streamlit as st
import requests
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

st.set_page_config(
    page_title="실뭉치 🧶 뜨개 도안 찾기",
    page_icon="🧶",
    layout="wide",
)

# ── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Gowun+Dodum&display=swap');

:root {
  --cream: #FAF6F1; --ivory: #FFF8F0; --beige: #EDE0D4;
  --rose: #C9897A; --rose-light: #F2D9D3; --sage: #8FAF8A; --sage-light: #D6E8D4;
  --brown: #3D2B1F; --brown-mid: #7A5C4E; --brown-light: #B89880;
}

/* ── 전체 배경 & 기본 폰트 ── */
html, body, [class*="css"], .stApp {
  font-family: 'Gowun Dodum', sans-serif !important;
  background-color: var(--cream) !important;
}
.stApp { background-color: var(--cream) !important; }
section[data-testid="stSidebar"] > div:first-child {
  background-color: var(--ivory) !important;
  border-right: 1.5px solid var(--beige);
}

/* ── 헤더 폰트 ── */
h1, h2, h3, .page-title {
  font-family: 'Gowun Dodum', sans-serif !important;
  color: var(--brown) !important;
}

/* ── 사이드바 로고 ── */
.sidebar-logo {
  font-family: 'Gowun Dodum', sans-serif;
  font-size: 26px;
  color: var(--rose); letter-spacing: .5px;
  margin-bottom: 2px;
}
.sidebar-sub {
  font-size: 12px; color: var(--brown-light); letter-spacing: .6px;
}

/* ── 실뭉치 로딩 애니메이션 ── */
@keyframes yarn-spin {
  0%   { transform: rotate(0deg) scale(1); }
  25%  { transform: rotate(90deg) scale(1.08); }
  50%  { transform: rotate(180deg) scale(1); }
  75%  { transform: rotate(270deg) scale(1.08); }
  100% { transform: rotate(360deg) scale(1); }
}
@keyframes yarn-trail {
  0%, 100% { opacity: .3; transform: scaleX(.6); }
  50%       { opacity: .9; transform: scaleX(1); }
}
@keyframes yarn-bounce {
  0%, 100% { transform: translateY(0); }
  50%       { transform: translateY(-6px); }
}
.yarn-loader {
  display: flex; flex-direction: column; align-items: center;
  gap: 10px; padding: 32px 0;
}
.yarn-ball {
  width: 56px; height: 56px; position: relative;
  animation: yarn-spin 1.4s ease-in-out infinite, yarn-bounce 1.4s ease-in-out infinite;
}
.yarn-ball svg { width: 100%; height: 100%; }
.yarn-label {
  font-size: 13px; color: var(--brown-mid); letter-spacing: .4px;
  animation: yarn-trail 1.4s ease-in-out infinite;
}

/* ── 카드 ── */
.knit-card {
  background: var(--ivory); border-radius: 18px; border: 1.5px solid var(--beige);
  overflow: hidden; transition: transform .2s, box-shadow .2s;
  box-shadow: 0 2px 8px rgba(61,43,31,.05); margin-bottom: 4px;
}
.knit-card:hover { transform: translateY(-3px); box-shadow: 0 10px 28px rgba(61,43,31,.12); }
.card-thumb { width: 100%; aspect-ratio: 16/9; object-fit: cover; display: block; }
.card-body { padding: 10px 12px 12px; }
.card-title {
  font-size: 13px; font-weight: 600; color: var(--brown); line-height: 1.4;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden; margin-bottom: 4px;
}
.card-channel { font-size: 11px; color: var(--brown-light); margin-bottom: 8px; }
.card-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.tag { padding: 2px 8px; border-radius: 10px; font-size: 10px; font-weight: 500; }
.cat-기법    { background: #E0D4F0; color: #6B5A9E; }
.cat-아이템  { background: #F9DDD4; color: #9E5A4A; }
.cat-캐릭터  { background: #F5D4E4; color: #9E4A78; }
.cat-동물    { background: #D4EDE8; color: #3A8A78; }
.cat-난이도  { background: #F9EDD4; color: #8A7030; }
.cat-도안    { background: #D4E4F0; color: #3A6A8A; }
.status-not      { background: rgba(0,0,0,.08); color: var(--brown-mid); }
.status-progress { background: #FFF3C0; color: #7A6000; }
.status-done     { background: var(--sage-light); color: #2A5A2A; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 10px; margin-bottom: 6px; }

/* ── 타이머 ── */
.timer-display {
  font-size: 40px; font-weight: 700; letter-spacing: 4px;
  color: var(--brown); text-align: center; padding: 12px 0; font-family: monospace;
  background: var(--ivory); border-radius: 12px; border: 1.5px solid var(--beige);
}

/* ── 카운터 ── */
.counter-val { font-size: 26px; font-weight: 700; color: var(--brown); min-width: 40px; text-align: center; }

/* ── 섹션 레이블 ── */
.sec-label { font-size: 11px; color: var(--brown-light); letter-spacing: .4px; margin-bottom: 6px; }

/* ── 페이지 제목 장식선 ── */
.page-heading {
  font-family: 'Gowun Dodum', sans-serif;
  font-size: 28px;
  color: var(--brown);
  border-bottom: 2px solid var(--beige);
  padding-bottom: 10px; margin-bottom: 20px;
}

/* ── Streamlit 기본 버튼 톤 조정 ── */
.stButton > button {
  border-radius: 10px !important;
  font-family: 'Gowun Dodum', sans-serif !important;
}

/* ── 검색창 ── */
.stTextInput > div > div > input {
  border-radius: 12px !important;
  border: 1.5px solid var(--beige) !important;
  background: var(--ivory) !important;
  color: var(--brown) !important;
  font-family: 'Gowun Dodum', sans-serif !important;
}

/* ── 카드 클릭 ── */
.knit-card { cursor: pointer; }
/* 카드 바로 다음 트리거 버튼 숨김 (JS가 대신 클릭) */
.element-container:has(.knit-card) + .element-container {
  height: 0 !important;
  overflow: hidden !important;
  margin: 0 !important;
  padding: 0 !important;
}
</style>
""", unsafe_allow_html=True)

# ── TAG MAP ───────────────────────────────────────────────────────────────────
TAG_MAP = {
    "기법": {
        "color": "cat-기법",
        "keywords": {
            "대바늘": ["대바늘", "knitting", "knit"],
            "코바늘": ["코바늘", "크로셰", "crochet"],
            "펀치니들": ["펀치니들", "punch needle"],
            "태피스트리": ["태피스트리", "tapestry"],
        },
    },
    "난이도": {
        "color": "cat-난이도",
        "keywords": {
            "입문·초보": ["입문", "초보", "beginner", "쉬운"],
            "중급": ["중급", "intermediate"],
            "고급": ["고급", "advanced"],
        },
    },
    "아이템": {
        "color": "cat-아이템",
        "keywords": {
            "가방": ["가방", "bag", "파우치", "pouch"],
            "모자": ["모자", "hat", "비니", "beanie"],
            "스웨터": ["스웨터", "sweater", "니트"],
            "양말": ["양말", "sock"],
            "숄·목도리": ["숄", "목도리", "shawl", "scarf"],
            "인형": ["인형", "amigurumi", "아미구루미"],
            "카디건": ["카디건", "cardigan"],
        },
    },
    "캐릭터": {
        "color": "cat-캐릭터",
        "keywords": {
            "플레이브": ["플레이브", "plave", "노아", "은호", "밤비", "하민", "예준"],
            "므메미무": ["므메미무"],
            "산리오": ["산리오", "sanrio", "헬로키티", "시나모롤"],
            "포켓몬": ["포켓몬", "pokemon", "피카츄"],
            "지브리": ["지브리", "ghibli", "토토로"],
            "디즈니": ["디즈니", "disney"],
        },
    },
    "동물": {
        "color": "cat-동물",
        "keywords": {
            "강아지": ["강아지", "dog", "puppy"],
            "고양이": ["고양이", "cat", "kitty"],
            "토끼": ["토끼", "bunny", "rabbit"],
            "곰": ["곰", "bear", "테디"],
            "개구리": ["개구리", "frog"],
            "문어": ["문어", "octopus"],
            "공룡": ["공룡", "dinosaur"],
        },
    },
    "도안": {
        "color": "cat-도안",
        "keywords": {
            "무료도안": ["무료도안", "free pattern", "무료 도안"],
            "도안공유": ["도안공유", "도안 공유", "패턴"],
            "유료도안": ["유료도안", "유료 도안"],
        },
    },
}

# ── API 키 자동 로드 (st.secrets → .env 순) ──────────────────────────────────
def _load_api_key() -> str:
    try:
        return st.secrets["YOUTUBE_API_KEY"]
    except Exception:
        return os.getenv("YOUTUBE_API_KEY", "")

# ── Session state init ────────────────────────────────────────────────────────
DEFAULTS = {
    "api_key": _load_api_key(),
    "bookmarks": [],
    "progress": {},
    "search_results": [],
    "current_video": None,
    "view": "search",
    "active_filters": [],
    "timer_start": None,
    "timer_accumulated": 0,
    "timer_running": False,
    "counters": [0, 0, 0],
    "search_query": "",
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ── Helpers ───────────────────────────────────────────────────────────────────
def extract_tags(text: str) -> list[dict]:
    low = text.lower()
    found = []
    for cat, data in TAG_MAP.items():
        for tag, kws in data["keywords"].items():
            if any(k.lower() in low for k in kws):
                found.append({"tag": tag, "color": data["color"]})
    return found


def search_youtube(query: str, api_key: str) -> list[dict]:
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "type": "video",
        "maxResults": 24,
        "q": query + " 뜨개 도안",
        "key": api_key,
        "relevanceLanguage": "ko",
        "videoEmbeddable": "true",
    }
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise ValueError(data["error"]["message"])
    return [
        {
            "id": item["id"]["videoId"],
            "title": item["snippet"]["title"],
            "channel": item["snippet"]["channelTitle"],
            "thumb": item["snippet"]["thumbnails"]["medium"]["url"],
            "description": item["snippet"]["description"],
            "tags": extract_tags(item["snippet"]["title"] + " " + item["snippet"]["description"]),
        }
        for item in data.get("items", [])
    ]


def get_elapsed() -> int:
    acc = st.session_state.timer_accumulated
    if st.session_state.timer_running and st.session_state.timer_start:
        acc += int(time.time() - st.session_state.timer_start)
    return acc


def fmt_time(secs: int) -> str:
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def status_badge_html(vid_id: str) -> str:
    s = st.session_state.progress.get(vid_id, {}).get("status", "not")
    labels = {"not": "시작 전", "progress": "🪡 진행 중", "done": "✅ 완성"}
    return f'<span class="badge status-{s}">{labels[s]}</span>'


def tag_html(tags: list[dict], limit: int = 4) -> str:
    return "".join(
        f'<span class="tag {t["color"]}">{t["tag"]}</span>'
        for t in tags[:limit]
    )


_CLICK_JS = """
(function(card){
  var el = card.closest('.element-container');
  var sib = el ? el.nextElementSibling : null;
  while(sib){
    var btn = sib.querySelector('button');
    if(btn){ btn.click(); return; }
    sib = sib.nextElementSibling;
  }
})(this)
""".replace("\n", " ").strip()


def card_html(v: dict) -> str:
    bm = "🔖" if any(b["id"] == v["id"] for b in st.session_state.bookmarks) else "🤍"
    return f"""
<div class="knit-card" onclick="{_CLICK_JS}">
  <img class="card-thumb" src="{v['thumb']}" alt="" />
  <div class="card-body">
    {status_badge_html(v['id'])}
    <div class="card-title">{v['title']}</div>
    <div class="card-channel">{v['channel']} {bm}</div>
    <div class="card-tags">{tag_html(v['tags'])}</div>
  </div>
</div>"""


def is_bookmarked(vid_id: str) -> bool:
    return any(b["id"] == vid_id for b in st.session_state.bookmarks)


def toggle_bookmark(v: dict):
    bms = st.session_state.bookmarks
    idx = next((i for i, b in enumerate(bms) if b["id"] == v["id"]), -1)
    if idx >= 0:
        bms.pop(idx)
    else:
        bms.append(v)


# ── Sidebar ───────────────────────────────────────────────────────────────────
YARN_SVG = """
<div class="yarn-loader">
  <div class="yarn-ball">
    <svg viewBox="0 0 56 56" xmlns="http://www.w3.org/2000/svg">
      <circle cx="28" cy="28" r="26" fill="#F2D9D3" stroke="#C9897A" stroke-width="2"/>
      <path d="M10 28 Q20 14 28 28 Q36 42 46 28" fill="none" stroke="#C9897A" stroke-width="2.5" stroke-linecap="round"/>
      <path d="M14 18 Q28 8 42 18" fill="none" stroke="#8FAF8A" stroke-width="2" stroke-linecap="round"/>
      <path d="M14 38 Q28 48 42 38" fill="none" stroke="#8FAF8A" stroke-width="2" stroke-linecap="round"/>
      <path d="M10 28 Q28 22 46 28" fill="none" stroke="#C9897A" stroke-width="1.5" stroke-linecap="round"/>
      <circle cx="44" cy="22" r="3" fill="#C9897A"/>
      <path d="M44 22 Q50 16 54 20" fill="none" stroke="#C9897A" stroke-width="1.5" stroke-linecap="round"/>
    </svg>
  </div>
  <div class="yarn-label">실 풀어오는 중… 🧶</div>
</div>
"""

with st.sidebar:
    st.markdown('<div class="sidebar-logo">🧶 실뭉치</div>', unsafe_allow_html=True)
    st.markdown('<div class="sidebar-sub">뜨개 도안 찾기</div>', unsafe_allow_html=True)
    st.divider()

    if not st.session_state.api_key:
        st.markdown("**🔑 YouTube API 키**")
        api_input = st.text_input("API 키", type="password", label_visibility="collapsed", placeholder="AIza...")
        if st.button("저장", use_container_width=True):
            if api_input.strip():
                st.session_state.api_key = api_input.strip()
                st.rerun()
    else:
        st.success("✅ API 키 연결됨")
        if st.button("🔑 키 변경", use_container_width=True):
            st.session_state.api_key = ""
            st.rerun()

    st.divider()
    nav = st.radio("메뉴", ["🔍 검색", "🔖 북마크"], label_visibility="collapsed")
    if "북마크" in nav and st.session_state.view != "bookmarks" and st.session_state.view != "detail":
        st.session_state.view = "bookmarks"
    elif "검색" in nav and st.session_state.view not in ("search", "detail"):
        st.session_state.view = "search"

    bm_count = len(st.session_state.bookmarks)
    if bm_count:
        st.caption(f"북마크 {bm_count}개")

    # ── 태그 필터 (검색 뷰에서만) ─────────────────────────────────────────
    if st.session_state.view in ("search", None):
        st.divider()
        st.markdown("**🏷 태그로 필터링**")
        selected_tags = []
        for cat, data in TAG_MAP.items():
            tags_in_cat = list(data["keywords"].keys())
            chosen = st.multiselect(cat, tags_in_cat, key=f"filter_{cat}")
            selected_tags.extend(chosen)
        st.session_state.active_filters = selected_tags
    else:
        # detail/bookmarks 뷰에서는 필터 상태만 유지
        selected_tags = st.session_state.get("active_filters", [])


# ── DETAIL VIEW ───────────────────────────────────────────────────────────────
if st.session_state.view == "detail" and st.session_state.current_video:
    v = st.session_state.current_video
    vid_id = v["id"]

    if st.button("← 목록으로"):
        st.session_state.view = st.session_state.get("prev_view", "search")
        if st.session_state.timer_running:
            st.session_state.timer_accumulated = get_elapsed()
            st.session_state.timer_running = False
            st.session_state.timer_start = None
        st.rerun()

    left, right = st.columns([3, 2])

    with left:
        st.video(f"https://www.youtube.com/watch?v={vid_id}")

    with right:
        st.markdown(f"**{v['title']}**")
        st.caption(v["channel"])
        st.markdown(tag_html(v["tags"]), unsafe_allow_html=True)
        st.divider()

        # Status
        prog = st.session_state.progress.setdefault(vid_id, {})
        st.markdown('<div class="sec-label">진행 상태</div>', unsafe_allow_html=True)
        cur_status = prog.get("status", "not")
        sc1, sc2, sc3 = st.columns(3)
        if sc1.button("⬜ 시작 전", use_container_width=True, type="primary" if cur_status == "not" else "secondary"):
            prog["status"] = "not"
        if sc2.button("🪡 진행 중", use_container_width=True, type="primary" if cur_status == "progress" else "secondary"):
            prog["status"] = "progress"
        if sc3.button("✅ 완성!", use_container_width=True, type="primary" if cur_status == "done" else "secondary"):
            prog["status"] = "done"
        st.divider()

        # Timer
        elapsed = get_elapsed()
        st.markdown('<div class="sec-label">⏱ 뜨개 시간</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="timer-display">{fmt_time(elapsed)}</div>', unsafe_allow_html=True)
        prog["timerSec"] = elapsed
        tc1, tc2 = st.columns(2)
        if st.session_state.timer_running:
            if tc1.button("⏸ 일시정지", use_container_width=True):
                st.session_state.timer_accumulated = get_elapsed()
                st.session_state.timer_running = False
                st.session_state.timer_start = None
                st.rerun()
        else:
            if tc1.button("▶ 시작", use_container_width=True):
                st.session_state.timer_start = time.time()
                st.session_state.timer_running = True
                st.rerun()
        if tc2.button("↺ 초기화", use_container_width=True):
            st.session_state.timer_accumulated = 0
            st.session_state.timer_running = False
            st.session_state.timer_start = None
            prog["timerSec"] = 0
            st.rerun()
        st.divider()

        # Counters
        st.markdown('<div class="sec-label">단수 · 코 수 카운터</div>', unsafe_allow_html=True)
        counter_labels = ["단수 1", "단수 2", "코 수"]
        saved_counters = prog.get("counters", [0, 0, 0])
        if len(st.session_state.counters) != 3:
            st.session_state.counters = saved_counters[:]

        for i, label in enumerate(counter_labels):
            col_lbl, col_minus, col_val, col_plus, col_rst = st.columns([2, 1, 1, 1, 1])
            col_lbl.markdown(f"**{label}**")
            if col_minus.button("−", key=f"minus_{i}"):
                st.session_state.counters[i] = max(0, st.session_state.counters[i] - 1)
                prog["counters"] = st.session_state.counters[:]
                st.rerun()
            col_val.markdown(f'<div class="counter-val">{st.session_state.counters[i]}</div>', unsafe_allow_html=True)
            if col_plus.button("+", key=f"plus_{i}"):
                st.session_state.counters[i] += 1
                prog["counters"] = st.session_state.counters[:]
                st.rerun()
            if col_rst.button("↺", key=f"rst_{i}"):
                st.session_state.counters[i] = 0
                prog["counters"] = st.session_state.counters[:]
                st.rerun()

        st.divider()

        # Notes
        st.markdown('<div class="sec-label">📝 메모</div>', unsafe_allow_html=True)
        notes = st.text_area("메모", value=prog.get("notes", ""), placeholder="실 종류, 바늘 호수, 특이사항...", label_visibility="collapsed", height=80)
        prog["notes"] = notes

        # Actions
        ac1, ac2 = st.columns(2)
        ac1.link_button("▶ YouTube에서 보기", f"https://www.youtube.com/watch?v={vid_id}", use_container_width=True, type="primary")
        bm_label = "🔖 저장됨" if is_bookmarked(vid_id) else "🤍 북마크"
        if ac2.button(bm_label, use_container_width=True):
            toggle_bookmark(v)
            st.rerun()

    # Auto-refresh timer while running
    if st.session_state.timer_running:
        time.sleep(1)
        st.rerun()


# ── SEARCH VIEW ───────────────────────────────────────────────────────────────
elif st.session_state.view in ("search", None):
    st.markdown('<div class="page-heading">🧶 뜨개 도안 찾기</div>', unsafe_allow_html=True)

    # Search bar
    sc1, sc2 = st.columns([5, 1])
    query = sc1.text_input("검색어", placeholder="코바늘 가방, 플레이브 인형, 강아지 뜨개...", label_visibility="collapsed")
    search_clicked = sc2.button("검색 🧶", use_container_width=True)

    selected_tags = st.session_state.get("active_filters", [])
    prev_filters = st.session_state.get("prev_filters", [])
    filters_changed = sorted(selected_tags) != sorted(prev_filters)

    should_search = (
        search_clicked
        or (query and query != st.session_state.get("search_query"))
        or (filters_changed and (query or selected_tags))
    )

    if should_search:
        if not st.session_state.api_key:
            st.error("먼저 사이드바에서 API 키를 저장해주세요 🔑")
        else:
            full_query = (query + " " + " ".join(selected_tags)).strip() or "뜨개"
            yarn_ph = st.empty()
            yarn_ph.markdown(YARN_SVG, unsafe_allow_html=True)
            try:
                results = search_youtube(full_query, st.session_state.api_key)
                st.session_state.search_results = results
                st.session_state.search_query = query
                st.session_state.prev_filters = selected_tags[:]
            except Exception as e:
                st.error(f"검색 실패: {e}")
            yarn_ph.empty()

    results = st.session_state.search_results
    if selected_tags and results:
        results = [v for v in results if any(t["tag"] in selected_tags for t in v["tags"])]

    if results:
        st.caption(f"영상 {len(results)}개")
        cols_per_row = 4
        for row_start in range(0, len(results), cols_per_row):
            row_vids = results[row_start : row_start + cols_per_row]
            cols = st.columns(cols_per_row)
            for col, v in zip(cols, row_vids):
                with col:
                    st.markdown(card_html(v), unsafe_allow_html=True)
                    if st.button(f"__open__{v['id']}", key=f"open_{v['id']}", use_container_width=True):
                        st.session_state.current_video = v
                        st.session_state.prev_view = "search"
                        st.session_state.view = "detail"
                        saved = st.session_state.progress.get(v["id"], {})
                        st.session_state.counters = saved.get("counters", [0, 0, 0])
                        st.session_state.timer_accumulated = saved.get("timerSec", 0)
                        st.session_state.timer_running = False
                        st.session_state.timer_start = None
                        st.rerun()
                    bm_label = "🔖" if is_bookmarked(v["id"]) else "🤍"
                    if st.button(bm_label, key=f"bm_{v['id']}", use_container_width=True):
                        toggle_bookmark(v)
                        st.rerun()
    elif not query:
        st.info("검색어를 입력하거나 태그를 선택해보세요 🧶")
    else:
        st.info("결과가 없어요. 다른 검색어를 시도해보세요.")


# ── BOOKMARKS VIEW ────────────────────────────────────────────────────────────
elif st.session_state.view == "bookmarks":
    st.markdown('<div class="page-heading">🔖 북마크</div>', unsafe_allow_html=True)
    bms = st.session_state.bookmarks
    if not bms:
        st.info("저장된 도안이 없어요. 마음에 드는 영상에 북마크를 눌러보세요.")
    else:
        st.caption(f"총 {len(bms)}개")
        cols_per_row = 4
        for row_start in range(0, len(bms), cols_per_row):
            row_vids = bms[row_start : row_start + cols_per_row]
            cols = st.columns(cols_per_row)
            for col, v in zip(cols, row_vids):
                with col:
                    st.markdown(card_html(v), unsafe_allow_html=True)
                    if st.button(f"__open__{v['id']}", key=f"bm_open_{v['id']}", use_container_width=True):
                        st.session_state.current_video = v
                        st.session_state.prev_view = "bookmarks"
                        st.session_state.view = "detail"
                        saved = st.session_state.progress.get(v["id"], {})
                        st.session_state.counters = saved.get("counters", [0, 0, 0])
                        st.session_state.timer_accumulated = saved.get("timerSec", 0)
                        st.session_state.timer_running = False
                        st.session_state.timer_start = None
                        st.rerun()
                    if st.button("🗑 삭제", key=f"del_bm_{v['id']}", use_container_width=True):
                        toggle_bookmark(v)
                        st.rerun()
