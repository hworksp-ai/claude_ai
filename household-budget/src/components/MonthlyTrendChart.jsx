import { useMemo } from 'react'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Tooltip,
  Legend,
} from 'chart.js'
import { Bar } from 'react-chartjs-2'
import { CATEGORICAL_LIGHT, CATEGORICAL_DARK, CHART_TEXT_LIGHT, CHART_TEXT_DARK } from '../constants/chartColors'
import { useIsDarkMode } from '../hooks/useIsDarkMode'
import { formatCurrency, monthLabel } from '../utils/format'

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend)

export default function MonthlyTrendChart({ transactions }) {
  const isDark = useIsDarkMode()
  const colors = isDark ? CATEGORICAL_DARK : CATEGORICAL_LIGHT
  const text = isDark ? CHART_TEXT_DARK : CHART_TEXT_LIGHT

  const { months, income, expense } = useMemo(() => {
    const byMonth = new Map()
    for (const t of transactions) {
      if (t.type !== 'income' && t.type !== 'expense') continue
      if (!byMonth.has(t.month)) byMonth.set(t.month, { income: 0, expense: 0 })
      byMonth.get(t.month)[t.type] += t.amount
    }
    const sortedMonths = Array.from(byMonth.keys()).sort((a, b) => a.localeCompare(b))
    return {
      months: sortedMonths,
      income: sortedMonths.map((m) => byMonth.get(m).income),
      expense: sortedMonths.map((m) => byMonth.get(m).expense),
    }
  }, [transactions])

  const data = {
    labels: months.map(monthLabel),
    datasets: [
      {
        label: '수입',
        data: income,
        backgroundColor: colors[0],
        borderRadius: 4,
        maxBarThickness: 28,
      },
      {
        label: '지출',
        data: expense,
        backgroundColor: colors[1],
        borderRadius: 4,
        maxBarThickness: 28,
      },
    ],
  }

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    scales: {
      x: {
        grid: { display: false },
        ticks: { color: text.muted, font: { size: 11 } },
      },
      y: {
        grid: { color: text.grid },
        ticks: {
          color: text.muted,
          font: { size: 11 },
          callback: (value) => `${(value / 10000).toLocaleString('ko-KR')}만`,
        },
      },
    },
    plugins: {
      legend: {
        position: 'top',
        align: 'end',
        labels: { color: text.secondary, boxWidth: 12, boxHeight: 12, font: { size: 12 } },
      },
      tooltip: {
        callbacks: {
          label: (ctx) => ` ${ctx.dataset.label}: ${formatCurrency(ctx.parsed.y)}`,
        },
      },
    },
  }

  return (
    <div className="rounded-xl border border-black/10 dark:border-white/10 bg-white dark:bg-neutral-900 p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-neutral-700 dark:text-neutral-200">월별 수입/지출 추이</h3>
      {months.length === 0 ? (
        <p className="flex h-64 items-center justify-center text-sm text-neutral-400">데이터가 없습니다</p>
      ) : (
        <div className="h-72">
          <Bar data={data} options={options} />
        </div>
      )}
    </div>
  )
}
