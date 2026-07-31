import { TYPE_LABELS } from '../constants/categories'
import { formatCurrency } from '../utils/format'

const TYPE_BADGE = {
  income: 'bg-[#e6f4ea] text-[#006300] dark:bg-[#0ca30c]/15 dark:text-[#3fd93f]',
  expense: 'bg-[#fbe9e9] text-[#d03b3b] dark:bg-[#e66767]/15 dark:text-[#f08a8a]',
  savings: 'bg-[#e8f0fc] text-[#2a78d6] dark:bg-[#3987e5]/15 dark:text-[#7ab0ee]',
}

const AMOUNT_SIGN = { income: '+', expense: '-', savings: '-' }

export default function TransactionList({ transactions, onDelete }) {
  if (transactions.length === 0) {
    return (
      <div className="rounded-xl border border-black/10 dark:border-white/10 bg-white dark:bg-neutral-900 p-8 text-center text-sm text-neutral-400">
        내역이 없습니다
      </div>
    )
  }

  return (
    <div className="overflow-hidden rounded-xl border border-black/10 dark:border-white/10 bg-white dark:bg-neutral-900 shadow-sm">
      <ul className="divide-y divide-black/5 dark:divide-white/5">
        {transactions.map((t) => (
          <li key={t.id} className="flex items-center justify-between gap-3 px-4 py-3">
            <div className="flex min-w-0 items-center gap-3">
              <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${TYPE_BADGE[t.type]}`}>
                {TYPE_LABELS[t.type]}
              </span>
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-neutral-800 dark:text-neutral-100">
                  {t.description || t.category}
                </p>
                <p className="text-xs text-neutral-400">
                  {t.date} · {t.category}
                </p>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-3">
              <span className="tabular-nums text-sm font-semibold text-neutral-800 dark:text-neutral-100">
                {AMOUNT_SIGN[t.type]}
                {formatCurrency(t.amount)}
              </span>
              <button
                onClick={() => onDelete(t.id)}
                aria-label="삭제"
                className="rounded-md p-1 text-neutral-400 transition hover:bg-neutral-100 hover:text-red-500 dark:hover:bg-neutral-800"
              >
                ✕
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
