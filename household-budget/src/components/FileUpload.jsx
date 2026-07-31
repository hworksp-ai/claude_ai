import { useRef, useState } from 'react'
import { parseBankSaladFile } from '../utils/xlsxParser'

export default function FileUpload({ onImport }) {
  const inputRef = useRef(null)
  const [status, setStatus] = useState(null) // { type: 'success' | 'error', message }
  const [loading, setLoading] = useState(false)

  async function handleFileChange(e) {
    const file = e.target.files?.[0]
    if (!file) return

    setLoading(true)
    setStatus(null)
    try {
      const rows = await parseBankSaladFile(file)
      if (rows.length === 0) {
        setStatus({ type: 'error', message: '가져올 내역이 없습니다. 파일 형식을 확인하세요.' })
        return
      }
      const { inserted } = await onImport(rows)
      setStatus({ type: 'success', message: `${inserted}건의 내역을 가져왔습니다.` })
    } catch (err) {
      setStatus({ type: 'error', message: `업로드 실패: ${err.message}` })
    } finally {
      setLoading(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  return (
    <div className="rounded-xl border border-dashed border-black/20 dark:border-white/20 bg-white dark:bg-neutral-900 p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-neutral-700 dark:text-neutral-200">뱅크샐러드 xlsx 업로드</p>
          <p className="text-xs text-neutral-400">내보낸 거래내역 파일을 업로드하면 자동으로 등록됩니다.</p>
        </div>
        <label className="shrink-0 cursor-pointer rounded-lg bg-neutral-900 px-3 py-2 text-sm font-medium text-white transition hover:bg-neutral-700 dark:bg-white dark:text-neutral-900 dark:hover:bg-neutral-200">
          {loading ? '처리 중...' : '파일 선택'}
          <input
            ref={inputRef}
            type="file"
            accept=".xlsx,.xls"
            className="hidden"
            onChange={handleFileChange}
            disabled={loading}
          />
        </label>
      </div>
      {status && (
        <p className={`mt-2 text-xs ${status.type === 'error' ? 'text-red-500' : 'text-[#006300] dark:text-[#0ca30c]'}`}>
          {status.message}
        </p>
      )}
    </div>
  )
}
