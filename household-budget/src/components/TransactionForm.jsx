import { useMemo, useState } from 'react'
import { CATEGORIES, TYPE_LABELS } from '../constants/categories'
import { formatDateToMonth } from '../utils/format'

const today = new Date().toISOString().slice(0, 10)

const initialState = {
  date: today,
  type: 'expense',
  category: CATEGORIES.expense[0],
  description: '',
  amount: '',
}

export default function TransactionForm({ onAdd }) {
  const [form, setForm] = useState(initialState)
  const [submitting, setSubmitting] = useState(false)

  const categoryOptions = useMemo(() => CATEGORIES[form.type], [form.type])

  function handleTypeChange(type) {
    setForm((prev) => ({ ...prev, type, category: CATEGORIES[type][0] }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const amount = Number(form.amount)
    if (!form.date || !amount || amount <= 0) return

    setSubmitting(true)
    try {
      await onAdd({
        date: form.date,
        month: formatDateToMonth(form.date),
        type: form.type,
        category: form.category,
        description: form.description.trim(),
        amount: Math.round(amount),
      })
      setForm({ ...initialState, type: form.type, category: form.category })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="grid grid-cols-2 gap-3 rounded-xl border border-black/10 dark:border-white/10 bg-white dark:bg-neutral-900 p-4 shadow-sm sm:grid-cols-6"
    >
      <div className="col-span-2 flex gap-1 sm:col-span-6">
        {Object.entries(TYPE_LABELS).map(([type, label]) => (
          <button
            type="button"
            key={type}
            onClick={() => handleTypeChange(type)}
            className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium transition ${
              form.type === type
                ? 'bg-neutral-900 text-white dark:bg-white dark:text-neutral-900'
                : 'bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <input
        type="date"
        value={form.date}
        onChange={(e) => setForm((p) => ({ ...p, date: e.target.value }))}
        className="col-span-1 rounded-lg border border-black/10 dark:border-white/10 bg-transparent px-2 py-2 text-sm dark:text-white"
        required
      />

      <select
        value={form.category}
        onChange={(e) => setForm((p) => ({ ...p, category: e.target.value }))}
        className="col-span-1 rounded-lg border border-black/10 dark:border-white/10 bg-transparent px-2 py-2 text-sm dark:text-white sm:col-span-2"
      >
        {categoryOptions.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>

      <input
        type="text"
        placeholder="내용"
        value={form.description}
        onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))}
        className="col-span-2 rounded-lg border border-black/10 dark:border-white/10 bg-transparent px-2 py-2 text-sm dark:text-white sm:col-span-2"
      />

      <input
        type="number"
        min="1"
        placeholder="금액"
        value={form.amount}
        onChange={(e) => setForm((p) => ({ ...p, amount: e.target.value }))}
        className="col-span-1 rounded-lg border border-black/10 dark:border-white/10 bg-transparent px-2 py-2 text-sm dark:text-white"
        required
      />

      <button
        type="submit"
        disabled={submitting}
        className="col-span-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:opacity-50 sm:col-span-1"
      >
        추가
      </button>
    </form>
  )
}
