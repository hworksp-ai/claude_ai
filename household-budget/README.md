# 가계부 (Household Budget Webapp)

React + Vite + Supabase 기반의 개인 가계부 웹앱입니다. 수입/지출/저축 내역을 기록하고,
월별 필터링, 카테고리별/월별 차트, 뱅크샐러드 엑셀 파일 자동 업로드 기능을 제공합니다.

## 주요 기능

- 수입 / 지출 / 저축 내역 추가 및 삭제
- 월별 필터링 및 전체 보기
- 카테고리별 도넛 차트 (지출, 수입)
- 월별 수입/지출 막대 차트 (추이)
- 뱅크샐러드 xlsx 파일 업로드 → DB 자동 적재
- 내역 검색 (내용, 카테고리)
- 상단 요약 카드 (수입 / 지출 / 저축 / 잔액)

## 기술 스택

- React 18 + Vite
- Supabase (`@supabase/supabase-js`)
- Chart.js + react-chartjs-2
- xlsx (SheetJS)
- Tailwind CSS
- Vercel 배포

## 1. Supabase 설정

1. [supabase.com](https://supabase.com)에서 새 프로젝트를 생성합니다.
2. 프로젝트 대시보드의 **SQL Editor**로 이동합니다.
3. 이 저장소의 [`supabase/schema.sql`](./supabase/schema.sql) 내용을 복사해서 실행합니다.
   - `transactions` 테이블과 인덱스, RLS 정책이 생성됩니다.
   - 기본 정책은 익명(anon) 키로 select/insert/delete가 가능하도록 설정되어 있습니다.
     (개인용 단일 사용자 앱을 가정한 설정입니다. 여러 사용자를 지원하려면
     `user_id` 컬럼을 추가하고 `auth.uid()` 기반 정책으로 교체하세요.)
4. **Project Settings → API**에서 다음 값을 확인합니다.
   - `Project URL` → `VITE_SUPABASE_URL`
   - `anon public` 키 → `VITE_SUPABASE_ANON_KEY`

## 2. 로컬 개발 환경 설정

```bash
# 1. 의존성 설치
npm install

# 2. 환경변수 파일 생성
cp .env.example .env.local
```

`.env.local` 파일을 열어 Supabase 값으로 채웁니다.

```
VITE_SUPABASE_URL=https://your-project-ref.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key
```

```bash
# 3. 개발 서버 실행
npm run dev
```

`http://localhost:5173` 에서 앱을 확인할 수 있습니다.

## 3. 뱅크샐러드 xlsx 업로드

뱅크샐러드 앱에서 내보낸 거래내역 엑셀 파일을 업로드하면 아래 규칙에 따라 자동으로 분류/저장됩니다.

| 뱅크샐러드 조건 | 저장 타입 | 저장 금액 |
|---|---|---|
| 타입 = 수입, 금액 > 0 | `income` | 금액 그대로 |
| 타입 = 지출, 금액 < 0 | `expense` | 절댓값 |
| 타입 = 이체, (대분류 = 저축 또는 내용에 "청약" 포함), 금액 < 0 | `savings` | 절댓값 |
| 그 외 이체 | 무시 | - |

파일의 컬럼 순서는 `날짜, 시간, 타입, 대분류, 소분류, 내용, 금액, 화폐, 결제수단, 메모` 로 고정되어 있어야 합니다.

## 4. Vercel 배포

1. GitHub 저장소를 [Vercel](https://vercel.com)에 Import 합니다.
2. Framework Preset은 **Vite**로 자동 인식됩니다 (`vercel.json`에 명시되어 있습니다).
3. **Environment Variables**에 아래 값을 등록합니다.
   - `VITE_SUPABASE_URL`
   - `VITE_SUPABASE_ANON_KEY`
4. Deploy를 실행합니다. 이후 커밋을 푸시할 때마다 자동으로 재배포됩니다.

### Vercel CLI로 배포하는 경우

```bash
npm i -g vercel
vercel login
vercel            # 프로젝트 연결 및 미리보기 배포
vercel --prod     # 프로덕션 배포
```

CLI 배포 시에는 `vercel env add VITE_SUPABASE_URL`, `vercel env add VITE_SUPABASE_ANON_KEY` 명령으로
환경변수를 등록하세요.

## 프로젝트 구조

```
household-budget/
├── src/
│   ├── components/       # UI 컴포넌트 (폼, 리스트, 차트, 업로드 등)
│   ├── constants/        # 카테고리 목록, 차트 색상
│   ├── hooks/            # useTransactions (Supabase CRUD), useIsDarkMode
│   ├── utils/            # 포맷 유틸, 뱅크샐러드 xlsx 파서
│   ├── supabaseClient.js
│   └── App.jsx
├── supabase/
│   └── schema.sql        # transactions 테이블 + RLS 정책
├── vercel.json
├── .env.example
└── README.md
```
