// dataviz 스킬의 검증된 기본 팔레트 (categorical, light/dark)
export const CATEGORICAL_LIGHT = [
  '#2a78d6', // blue
  '#eb6834', // orange
  '#1baf7a', // aqua
  '#eda100', // yellow
  '#e87ba4', // magenta
  '#008300', // green
  '#4a3aa7', // violet
  '#898781', // 기타(회색)
]

export const CATEGORICAL_DARK = [
  '#3987e5',
  '#d95926',
  '#199e70',
  '#c98500',
  '#d55181',
  '#008300',
  '#9085e9',
  '#898781',
]

export const CHART_TEXT_LIGHT = { primary: '#0b0b0b', secondary: '#52514e', muted: '#898781', grid: '#e1e0d9' }
export const CHART_TEXT_DARK = { primary: '#ffffff', secondary: '#c3c2b7', muted: '#898781', grid: '#2c2c2a' }

export function prefersDarkMode() {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches
}

// 카테고리별 항목이 8개를 넘으면 상위 항목만 남기고 나머지는 "기타"로 묶습니다.
export const MAX_DONUT_SLICES = 7

export function foldIntoOther(entries, maxSlices = MAX_DONUT_SLICES) {
  const sorted = [...entries].sort((a, b) => b.value - a.value)
  if (sorted.length <= maxSlices) return sorted

  const top = sorted.slice(0, maxSlices)
  const rest = sorted.slice(maxSlices)
  const otherValue = rest.reduce((sum, e) => sum + e.value, 0)
  return [...top, { label: '기타', value: otherValue }]
}
