import { useMemo, useState } from 'react'
import { useTransactions } from './hooks/useTransactions'
import SummaryCards from './components/SummaryCards'
import TransactionForm from './components/TransactionForm'
import FileUpload from './components/FileUpload'
import Filters from './components/Filters'
import TransactionList from './components/TransactionList'
import CategoryDonutChart from './components/CategoryDonutChart'
import MonthlyTrendChart from './components/MonthlyTrendChart'

export default function App() {
  const { transactions, loading, error, months, addTransaction, addTransactionsBulk, deleteTransaction } =
    useTransactions()

  const [selectedMonth, setSelectedMonth] = useState('all')
  const [search, setSearch] = useState('')

  const searched = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return transactions
    return transactions.filter(
      (t) => t.description?.toLowerCase().includes(q) || t.category?.toLowerCase().includes(q)
    )
  }, [transactions, search])

  const filtered = useMemo(() => {
    if (selectedMonth === 'all') return searched
    return searched.filter((t) => t.month === selectedMonth)
  }, [searched, selectedMonth])

  const expenseTransactions = useMemo(() => filtered.filter((t) => t.type === 'expense'), [filtered])
  const incomeTransactions = useMemo(() => filtered.filter((t) => t.type === 'income'), [filtered])

  return (
    <div className="mx-auto min-h-screen max-w-4xl px-4 py-6 sm:px-6">
      <header className="mb-6">
        <h1 className="text-2xl font-bold">가계부</h1>
        <p className="text-sm text-neutral-400">수입, 지출, 저축 내역을 관리하세요</p>
      </header>

      {error && (
        <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-600 dark:bg-red-900/20 dark:text-red-300">
          데이터를 불러오지 못했습니다: {error}
        </div>
      )}

      <div className="mb-6">
        <SummaryCards transactions={filtered} />
      </div>

      <div className="mb-6 grid gap-4 sm:grid-cols-2">
        <TransactionForm onAdd={addTransaction} />
        <FileUpload onImport={addTransactionsBulk} />
      </div>

      <div className="mb-6 grid gap-4 sm:grid-cols-2">
        <CategoryDonutChart title="지출 카테고리별 비중" transactions={expenseTransactions} />
        <CategoryDonutChart title="수입 카테고리별 비중" transactions={incomeTransactions} />
      </div>

      <div className="mb-6">
        <MonthlyTrendChart transactions={searched} />
      </div>

      <div className="mb-4">
        <Filters
          months={months}
          selectedMonth={selectedMonth}
          onMonthChange={setSelectedMonth}
          search={search}
          onSearchChange={setSearch}
        />
      </div>

      {loading ? (
        <p className="py-8 text-center text-sm text-neutral-400">불러오는 중...</p>
      ) : (
        <TransactionList transactions={filtered} onDelete={deleteTransaction} />
      )}
    </div>
  )
}
