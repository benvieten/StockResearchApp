import { useEffect, useState } from 'react'
import { ArrowLeft, Bookmark, Trash2, TrendingUp } from 'lucide-react'
import type { SavedTicker } from '@/types'

interface MySavedWatchlistProps {
  onAnalyze: (ticker: string) => void
  onBack: () => void
}

export function MySavedWatchlist({ onAnalyze, onBack }: MySavedWatchlistProps) {
  const [tickers, setTickers] = useState<SavedTicker[]>([])
  const [loading, setLoading] = useState(true)
  const [removing, setRemoving] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/saved-tickers')
      .then(r => r.json())
      .then(d => setTickers(d.tickers ?? []))
      .catch(() => setTickers([]))
      .finally(() => setLoading(false))
  }, [])

  async function handleRemove(ticker: string) {
    setRemoving(ticker)
    try {
      await fetch(`/api/saved-tickers/${ticker}`, { method: 'DELETE' })
      setTickers(prev => prev.filter(t => t.ticker !== ticker))
    } finally {
      setRemoving(null)
    }
  }

  return (
    <div className="min-h-screen bg-[#080808] text-white">
      {/* Header */}
      <div className="border-b border-white/5 px-6 py-4 sticky top-0 z-20 bg-[#080808]/95 backdrop-blur-sm">
        <div className="max-w-3xl mx-auto flex items-center gap-4">
          <button
            onClick={onBack}
            className="flex items-center gap-1.5 text-sm text-zinc-500 hover:text-white transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back
          </button>
          <div className="w-px h-4 bg-white/10" />
          <div className="flex items-center gap-2">
            <Bookmark className="w-4 h-4 text-violet-400" />
            <span className="font-semibold text-white">My Watchlist</span>
          </div>
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-6 py-10">
        {loading ? (
          <div className="flex items-center gap-3 text-zinc-500">
            <div className="w-4 h-4 border-2 border-zinc-700 border-t-violet-500 rounded-full animate-spin" />
            Loading...
          </div>
        ) : tickers.length === 0 ? (
          <div className="text-center py-20">
            <Bookmark className="w-10 h-10 text-zinc-700 mx-auto mb-4" />
            <p className="text-zinc-400 font-medium mb-1">No saved tickers yet</p>
            <p className="text-zinc-600 text-sm">
              After running an analysis, click <span className="text-violet-400">Save</span> to add it here.
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <p className="text-xs text-zinc-600 mb-2">{tickers.length} saved ticker{tickers.length !== 1 ? 's' : ''}</p>
            {tickers.map(({ ticker, added_at }) => (
              <div
                key={ticker}
                className="flex items-center justify-between bg-white/[0.03] border border-white/8 rounded-xl px-5 py-4 hover:border-white/15 transition-colors"
              >
                <div className="flex items-center gap-4">
                  <span className="font-mono font-bold text-white text-lg">{ticker}</span>
                  <span className="text-xs text-zinc-600">
                    Added {new Date(added_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => onAnalyze(ticker)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-violet-600/20 text-violet-300 border border-violet-500/30 hover:bg-violet-600/30 transition-colors"
                  >
                    <TrendingUp className="w-3.5 h-3.5" />
                    Analyze
                  </button>
                  <button
                    onClick={() => handleRemove(ticker)}
                    disabled={removing === ticker}
                    className="p-1.5 rounded-lg text-zinc-600 hover:text-red-400 hover:bg-red-500/10 transition-colors disabled:opacity-40"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
