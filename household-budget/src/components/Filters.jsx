import { monthLabel } from '../utils/format'

export default function Filters({ months, selectedMonth, onMonthChange, search, onSearchChange }) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-center gap-2 overflow-x-auto">
        <button
          onClick={() => onMonthChange('all')}
          className={`shrink-0 rounded-full px-3 py-1.5 text-sm font-medium transition ${
            selectedMonth === 'all'
              ? 'bg-neutral-900 text-white dark:bg-white dark:text-neutral-900'
              : 'bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300'
          }`}
        >
          전체
        </button>
        {months.map((m) => (
          <button
            key={m}
            onClick={() => onMonthChange(m)}
            className={`shrink-0 rounded-full px-3 py-1.5 text-sm font-medium transition ${
              selectedMonth === m
                ? 'bg-neutral-900 text-white dark:bg-white dark:text-neutral-900'
                : 'bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300'
            }`}
          >
            {monthLabel(m)}
          </button>
        ))}
      </div>

      <input
        type="search"
        placeholder="내용 또는 카테고리 검색"
        value={search}
        onChange={(e) => onSearchChange(e.target.value)}
        className="w-full rounded-lg border border-black/10 dark:border-white/10 bg-white dark:bg-neutral-900 px-3 py-2 text-sm dark:text-white sm:w-64"
      />
    </div>
  )
}
