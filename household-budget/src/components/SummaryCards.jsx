import { formatCurrency } from '../utils/format'

function Card({ label, value, tone }) {
  const toneClasses = {
    income: 'text-[#006300] dark:text-[#0ca30c]',
    expense: 'text-[#d03b3b] dark:text-[#e66767]',
    savings: 'text-[#2a78d6] dark:text-[#3987e5]',
    balance: 'text-neutral-900 dark:text-white',
  }
  return (
    <div className="rounded-xl border border-black/10 dark:border-white/10 bg-white dark:bg-neutral-900 p-4 shadow-sm">
      <p className="text-xs font-medium text-neutral-500 dark:text-neutral-400">{label}</p>
      <p className={`mt-1 text-xl font-bold tabular-nums ${toneClasses[tone]}`}>{formatCurrency(value)}</p>
    </div>
  )
}

export default function SummaryCards({ transactions }) {
  const totals = transactions.reduce(
    (acc, t) => {
      acc[t.type] += t.amount
      return acc
    },
    { income: 0, expense: 0, savings: 0 }
  )

  const balance = totals.income - totals.expense - totals.savings

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <Card label="수입" value={totals.income} tone="income" />
      <Card label="지출" value={totals.expense} tone="expense" />
      <Card label="저축" value={totals.savings} tone="savings" />
      <Card label="잔액" value={balance} tone="balance" />
    </div>
  )
}
