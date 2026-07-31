export const TRANSACTION_TYPES = ['income', 'expense', 'savings']

export const TYPE_LABELS = {
  income: '수입',
  expense: '지출',
  savings: '저축',
}

export const CATEGORIES = {
  income: ['급여', '부업', '투자', '용돈', '보험금', '금융수입', '아르바이트', '중고거래', '기타수입'],
  expense: [
    '식비',
    '교통',
    '온라인쇼핑',
    '문화/여가',
    '의료/건강',
    '주거/통신',
    '금융',
    '생활',
    '뷰티/미용',
    '카페/간식',
    '패션/쇼핑',
    '교육/학습',
    '경조/선물',
    '자동차',
    '여행/숙박',
    '술/유흥',
    '기타지출',
  ],
  savings: ['저축', '청약저축', '적금', '펀드', '주식', '비상금'],
}

export const DEFAULT_CATEGORY = {
  income: '기타수입',
  expense: '기타지출',
  savings: '저축',
}
