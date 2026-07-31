export function formatCurrency(amount) {
  const value = Number(amount) || 0
  return `${value.toLocaleString('ko-KR')}원`
}

export function formatDateToMonth(date) {
  const d = date instanceof Date ? date : new Date(date)
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  return `${year}-${month}`
}

export function currentMonth() {
  return formatDateToMonth(new Date())
}

export function monthLabel(month) {
  const [year, m] = month.split('-')
  return `${year}년 ${Number(m)}월`
}
