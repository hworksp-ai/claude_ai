import { useMemo } from 'react'
import { Chart as ChartJS, ArcElement, Tooltip, Legend } from 'chart.js'
import { Doughnut } from 'react-chartjs-2'
import {
  CATEGORICAL_LIGHT,
  CATEGORICAL_DARK,
  CHART_TEXT_LIGHT,
  CHART_TEXT_DARK,
  foldIntoOther,
} from '../constants/chartColors'
import { useIsDarkMode } from '../hooks/useIsDarkMode'
import { formatCurrency } from '../utils/format'

ChartJS.register(ArcElement, Tooltip, Legend)

export default function CategoryDonutChart({ title, transactions }) {
  const isDark = useIsDarkMode()
  const colors = isDark ? CATEGORICAL_DARK : CATEGORICAL_LIGHT
  const text = isDark ? CHART_TEXT_DARK : CHART_TEXT_LIGHT

  const slices = useMemo(() => {
    const totals = new Map()
    for (const t of transactions) {
      totals.set(t.category, (totals.get(t.category) ?? 0) + t.amount)
    }
    const entries = Array.from(totals.entries()).map(([label, value]) => ({ label, value }))
    return foldIntoOther(entries)
  }, [transactions])

  const total = slices.reduce((sum, s) => sum + s.value, 0)

  const data = {
    labels: slices.map((s) => s.label),
    datasets: [
      {
        data: slices.map((s) => s.value),
        backgroundColor: slices.map((_, i) => colors[i % colors.length]),
        borderColor: isDark ? '#1a1a19' : '#fcfcfb',
        borderWidth: 2,
        hoverOffset: 4,
      },
    ],
  }

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    cutout: '62%',
    plugins: {
      legend: {
        position: 'bottom',
        labels: {
          color: text.secondary,
          padding: 12,
          boxWidth: 12,
          boxHeight: 12,
          font: { size: 12 },
        },
      },
      tooltip: {
        callbacks: {
          label: (ctx) => {
            const value = ctx.parsed
            const pct = total > 0 ? ((value / total) * 100).toFixed(1) : '0.0'
            return ` ${ctx.label}: ${formatCurrency(value)} (${pct}%)`
          },
        },
      },
    },
  }

  return (
    <div className="rounded-xl border border-black/10 dark:border-white/10 bg-white dark:bg-neutral-900 p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-neutral-700 dark:text-neutral-200">{title}</h3>
      {total === 0 ? (
        <p className="flex h-56 items-center justify-center text-sm text-neutral-400">데이터가 없습니다</p>
      ) : (
        <div className="h-64">
          <Doughnut data={data} options={options} />
        </div>
      )}
    </div>
  )
}
