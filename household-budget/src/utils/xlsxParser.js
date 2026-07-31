import * as XLSX from 'xlsx'
import { CATEGORIES, DEFAULT_CATEGORY } from '../constants/categories'
import { formatDateToMonth } from './format'

// 뱅크샐러드 내보내기 컬럼 순서
// 0:날짜 1:시간 2:타입 3:대분류 4:소분류 5:내용 6:금액 7:화폐 8:결제수단 9:메모
const COL = {
  DATE: 0,
  TIME: 1,
  TYPE: 2,
  MAIN_CATEGORY: 3,
  SUB_CATEGORY: 4,
  DESCRIPTION: 5,
  AMOUNT: 6,
}

function parseDateCell(value) {
  if (value instanceof Date) return value
  if (typeof value === 'number') {
    // Excel serial date number
    const parsed = XLSX.SSF.parse_date_code(value)
    return new Date(parsed.y, parsed.m - 1, parsed.d)
  }
  if (typeof value === 'string') {
    const normalized = value.trim().replace(/\./g, '-').replace(/\//g, '-')
    const d = new Date(normalized)
    if (!Number.isNaN(d.getTime())) return d
  }
  return null
}

function parseAmountCell(value) {
  if (typeof value === 'number') return value
  if (typeof value === 'string') {
    const cleaned = value.replace(/,/g, '').trim()
    const n = Number(cleaned)
    return Number.isNaN(n) ? 0 : n
  }
  return 0
}

function resolveCategory(type, mainCategory, subCategory, description) {
  const list = CATEGORIES[type]
  if (type === 'savings' && description && description.includes('청약')) {
    return '청약저축'
  }
  if (subCategory && list.includes(subCategory)) return subCategory
  if (mainCategory && list.includes(mainCategory)) return mainCategory
  return DEFAULT_CATEGORY[type]
}

/**
 * 뱅크샐러드 xlsx 파일을 읽어 transactions 배열로 변환합니다.
 * @param {File} file
 * @returns {Promise<Array<{date: string, month: string, type: string, category: string, description: string, amount: number}>>}
 */
export async function parseBankSaladFile(file) {
  const buffer = await file.arrayBuffer()
  const workbook = XLSX.read(buffer, { type: 'array', cellDates: true })
  const sheetName = workbook.SheetNames[0]
  const sheet = workbook.Sheets[sheetName]
  const rows = XLSX.utils.sheet_to_json(sheet, { header: 1, defval: '', raw: true })

  const results = []

  for (let i = 1; i < rows.length; i++) {
    const row = rows[i]
    if (!row || row.length === 0) continue

    const rawType = String(row[COL.TYPE] ?? '').trim()
    if (!rawType) continue

    const mainCategory = String(row[COL.MAIN_CATEGORY] ?? '').trim()
    const subCategory = String(row[COL.SUB_CATEGORY] ?? '').trim()
    const description = String(row[COL.DESCRIPTION] ?? '').trim()
    const amount = parseAmountCell(row[COL.AMOUNT])
    const dateValue = parseDateCell(row[COL.DATE])
    if (!dateValue) continue

    let type = null

    if (rawType === '수입' && amount > 0) {
      type = 'income'
    } else if (rawType === '지출' && amount < 0) {
      type = 'expense'
    } else if (
      rawType === '이체' &&
      amount < 0 &&
      (mainCategory === '저축' || description.includes('청약'))
    ) {
      type = 'savings'
    }

    if (!type) continue

    results.push({
      date: dateValue.toISOString().slice(0, 10),
      month: formatDateToMonth(dateValue),
      type,
      category: resolveCategory(type, mainCategory, subCategory, description),
      description,
      amount: Math.abs(amount),
    })
  }

  return results
}
