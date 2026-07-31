import { useCallback, useEffect, useMemo, useState } from 'react'
import { supabase } from '../supabaseClient'

const TABLE = 'transactions'
const BULK_INSERT_CHUNK_SIZE = 500

export function useTransactions() {
  const [transactions, setTransactions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchTransactions = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const { data, error: fetchError } = await supabase
        .from(TABLE)
        .select('*')
        .order('date', { ascending: false })
        .order('created_at', { ascending: false })

      if (fetchError) throw new Error(fetchError.message)
      setTransactions(data ?? [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchTransactions()
  }, [fetchTransactions])

  const addTransaction = useCallback(async (transaction) => {
    const { data, error: insertError } = await supabase
      .from(TABLE)
      .insert([transaction])
      .select()

    if (insertError) throw new Error(insertError.message)
    setTransactions((prev) => [...(data ?? []), ...prev])
    return data
  }, [])

  const addTransactionsBulk = useCallback(async (rows) => {
    if (rows.length === 0) return { inserted: 0 }

    for (let i = 0; i < rows.length; i += BULK_INSERT_CHUNK_SIZE) {
      const chunk = rows.slice(i, i + BULK_INSERT_CHUNK_SIZE)
      const { error: insertError } = await supabase.from(TABLE).insert(chunk)
      if (insertError) throw new Error(insertError.message)
    }

    await fetchTransactions()
    return { inserted: rows.length }
  }, [fetchTransactions])

  const deleteTransaction = useCallback(async (id) => {
    const { error: deleteError } = await supabase.from(TABLE).delete().eq('id', id)
    if (deleteError) throw new Error(deleteError.message)
    setTransactions((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const months = useMemo(() => {
    const set = new Set(transactions.map((t) => t.month))
    return Array.from(set).sort((a, b) => b.localeCompare(a))
  }, [transactions])

  return {
    transactions,
    loading,
    error,
    months,
    refresh: fetchTransactions,
    addTransaction,
    addTransactionsBulk,
    deleteTransaction,
  }
}
