import { useEffect, useState } from 'react'
import { ArrowLeft, Bookmark, ChevronDown, ChevronUp, Trash2, TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { cn } from '@/lib/utils'
import { StockChart } from '@/components/StockChart'

interface SavedTickerDetail {
  ticker: string
  added_at: string
  last_verdict: string | null
  last_conviction: string | null
  last_score: number | null
  last_analyzed_at: string | null
  price_at_analysis: number | null
  current_price: number | null
  price_change: number | null
  price_change_pct: number | null
}

const VERDICT_STYLES: Record<string, string> = {
  strong_buy: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
  buy:        'bg-green-500/20  text-green-300  border-green-500/30',
  hold:       'bg-amber-500/20  text-amber-300  border-amber-500/30',
  sell:       'bg-orange-500/20 text-orange-300 border-orange-500/30',
  strong_sell:'bg-red-500/20    text-red-300    border-red-500/30',
}

function verdictLabel(v: string) {
  return v.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function fmt(n: number | null, decimals = 2): string {
  return n != null ? n.toFixed(decimals) : '—'
}

interface Props {
  onAnalyze: (ticker: string) => void
  onBack: () => void
}

export function MySavedWatchlist({ onAnalyze, onBack }: Props) {
  const [tickers, setTickers] = useState<SavedTickerDetail[]>([])
  const [loading, setLoading] = useState(true)
  const [removing, setRemoving] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/saved-tickers/details')
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
        <div className="max-w-4xl mx-auto flex items-center gap-4">
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

      <div className="max-w-4xl mx-auto px-6 py-10">
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
            <p className="text-xs text-zinc-600 mb-2">
              {tickers.length} saved ticker{tickers.length !== 1 ? 's' : ''} · prices update daily
            </p>

            {tickers.map((t) => {
              const pctUp = t.price_change_pct != null && t.price_change_pct > 0
              const pctDown = t.price_change_pct != null && t.price_change_pct < 0
              const PriceIcon = pctUp ? TrendingUp : pctDown ? TrendingDown : Minus

              return (
                <div
                  key={t.ticker}
                  className="bg-white/[0.03] border border-white/8 rounded-xl px-5 py-4 hover:border-white/15 transition-colors"
                >
                  <div className="flex items-start justify-between gap-4">
                    {/* Left: ticker + verdict */}
                    <div className="flex items-center gap-3 min-w-0">
                      <span className="font-mono font-bold text-white text-xl">{t.ticker}</span>
                      {t.last_verdict && (
                        <span className={cn(
                          'px-2 py-0.5 rounded-md text-xs font-medium border',
                          VERDICT_STYLES[t.last_verdict] ?? 'bg-white/5 text-zinc-400 border-white/10'
                        )}>
                          {verdictLabel(t.last_verdict)}
                        </span>
                      )}
                      {t.last_conviction && (
                        <span className="text-xs text-zinc-500 capitalize">{t.last_conviction} conviction</span>
                      )}
                    </div>

                    {/* Right: actions */}
                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        onClick={() => onAnalyze(t.ticker)}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-violet-600/20 text-violet-300 border border-violet-500/30 hover:bg-violet-600/30 transition-colors"
                      >
                        <TrendingUp className="w-3.5 h-3.5" />
                        Analyze
                      </button>
                      <button
                        onClick={() => handleRemove(t.ticker)}
                        disabled={removing === t.ticker}
                        className="p-1.5 rounded-lg text-zinc-600 hover:text-red-400 hover:bg-red-500/10 transition-colors disabled:opacity-40"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>

                  {/* Price row */}
                  <div className="mt-3 flex items-center gap-6 flex-wrap">
                    {/* Current price */}
                    <div>
                      <p className="text-[11px] text-zinc-600 mb-0.5">Current price</p>
                      <p className="text-lg font-semibold text-white">
                        {t.current_price != null ? `$${fmt(t.current_price)}` : '—'}
                      </p>
                    </div>

                    {/* Price at analysis */}
                    <div>
                      <p className="text-[11px] text-zinc-600 mb-0.5">At last analysis</p>
                      <p className="text-sm text-zinc-400">
                        {t.price_at_analysis != null ? `$${fmt(t.price_at_analysis)}` : '—'}
                      </p>
                    </div>

                    {/* Change since analysis */}
                    {t.price_change_pct != null && (
                      <div>
                        <p className="text-[11px] text-zinc-600 mb-0.5">Since analysis</p>
                        <div className={cn(
                          'flex items-center gap-1 text-sm font-semibold',
                          pctUp ? 'text-emerald-400' : pctDown ? 'text-red-400' : 'text-zinc-500'
                        )}>
                          <PriceIcon className="w-3.5 h-3.5" />
                          {pctUp ? '+' : ''}{(t.price_change_pct * 100).toFixed(2)}%
                          <span className="font-normal text-xs opacity-70">
                            ({pctUp ? '+' : ''}${fmt(t.price_change)})
                          </span>
                        </div>
                      </div>
                    )}

                    {/* Score */}
                    {t.last_score != null && (
                      <div>
                        <p className="text-[11px] text-zinc-600 mb-0.5">Signal score</p>
                        <p className="text-sm text-zinc-300">{Math.round(t.last_score * 100)}</p>
                      </div>
                    )}

                    {/* Last analyzed */}
                    {t.last_analyzed_at && (
                      <div>
                        <p className="text-[11px] text-zinc-600 mb-0.5">Last analyzed</p>
                        <p className="text-xs text-zinc-500">
                          {new Date(t.last_analyzed_at).toLocaleDateString('en-US', {
                            month: 'short', day: 'numeric', year: 'numeric'
                          })}
                        </p>
                      </div>
                    )}

                    {/* Chart toggle */}
                    <button
                      onClick={() => setExpanded(expanded === t.ticker ? null : t.ticker)}
                      className="ml-auto flex items-center gap-1 text-xs text-zinc-600 hover:text-zinc-400 transition-colors"
                    >
                      {expanded === t.ticker ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                      {expanded === t.ticker ? 'Hide chart' : 'Show chart'}
                    </button>
                  </div>

                  {/* Expandable chart */}
                  {expanded === t.ticker && (
                    <StockChart ticker={t.ticker} priceAtAnalysis={t.price_at_analysis} />
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
