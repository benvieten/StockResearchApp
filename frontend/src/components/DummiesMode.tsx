import * as React from 'react'
import { cn } from '@/lib/utils'
import type { FinalReport } from '@/types'
import { Brain, TrendingUp, TrendingDown, Zap, Loader2, AlertCircle } from 'lucide-react'

interface DummiesModeProps {
  report: FinalReport
}

interface SimpleExplanation {
  summary: string
  verdict_explained: string
  bull_simple: string
  bear_simple: string
  bottom_line: string
}

export function DummiesMode({ report }: DummiesModeProps) {
  const [open, setOpen] = React.useState(false)
  const [loading, setLoading] = React.useState(false)
  const [data, setData] = React.useState<SimpleExplanation | null>(null)
  const [error, setError] = React.useState<string | null>(null)

  const handleOpen = async () => {
    setOpen(true)
    if (data) return  // already fetched

    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/research/explain-simple', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ticker: report.ticker,
          verdict: report.verdict,
          conviction: report.conviction,
          narrative: report.narrative,
          bull_case: report.bull_case,
          bear_case: report.bear_case,
          conflicts: report.conflicts,
          signal_scores: report.signal_scores,
        }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const json = await res.json() as SimpleExplanation
      setData(json)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="rounded-xl border border-purple-500/20 bg-purple-500/5 overflow-hidden">
      {/* Toggle button */}
      <button
        onClick={open ? () => setOpen(false) : handleOpen}
        className={cn(
          'w-full flex items-center gap-3 px-5 py-4 text-left transition-colors',
          'hover:bg-purple-500/10',
        )}
      >
        <span className="text-xl">🧠</span>
        <div className="flex-1">
          <p className="font-semibold text-purple-300 text-sm">Explain Like I'm Dumb</p>
          <p className="text-xs text-purple-400/60">No jargon. No charts. Just vibes.</p>
        </div>
        <span className="text-purple-400/40 text-xs">
          {open ? 'hide ▲' : 'show ▼'}
        </span>
      </button>

      {/* Content */}
      {open && (
        <div className="border-t border-purple-500/15 px-5 pb-5 pt-4">
          {loading && (
            <div className="flex items-center gap-3 text-purple-300 text-sm py-4">
              <Loader2 className="w-4 h-4 animate-spin" />
              Dumbing it down for you…
            </div>
          )}

          {error && (
            <div className="flex items-center gap-2 text-red-400 text-sm py-2">
              <AlertCircle className="w-4 h-4" />
              {error}
            </div>
          )}

          {data && (
            <div className="space-y-4">
              {/* Summary */}
              <div className="bg-white/[0.03] rounded-xl p-4 border border-white/5">
                <div className="flex items-center gap-2 mb-2">
                  <Brain className="w-4 h-4 text-purple-400" />
                  <p className="text-xs font-semibold text-purple-300 uppercase tracking-wider">
                    OK so here's the deal
                  </p>
                </div>
                <p className="text-sm text-zinc-300 leading-relaxed">{data.summary}</p>
              </div>

              {/* Verdict explained */}
              <div className="bg-white/[0.03] rounded-xl p-4 border border-white/5">
                <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-1.5">
                  What does "{report.verdict.replace(/_/g, ' ')}" even mean?
                </p>
                <p className="text-sm text-zinc-300">{data.verdict_explained}</p>
              </div>

              {/* Bull / Bear simple */}
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-emerald-500/5 border border-emerald-500/15 rounded-xl p-4">
                  <div className="flex items-center gap-1.5 mb-2">
                    <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
                    <p className="text-xs font-semibold text-emerald-400">Good news</p>
                  </div>
                  <p className="text-xs text-zinc-300 leading-relaxed">{data.bull_simple}</p>
                </div>
                <div className="bg-red-500/5 border border-red-500/15 rounded-xl p-4">
                  <div className="flex items-center gap-1.5 mb-2">
                    <TrendingDown className="w-3.5 h-3.5 text-red-400" />
                    <p className="text-xs font-semibold text-red-400">Bad news</p>
                  </div>
                  <p className="text-xs text-zinc-300 leading-relaxed">{data.bear_simple}</p>
                </div>
              </div>

              {/* Bottom line */}
              <div className="bg-gradient-to-r from-purple-500/10 to-pink-500/10 border border-purple-500/20 rounded-xl p-4 flex items-start gap-3">
                <Zap className="w-4 h-4 text-yellow-400 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-1">
                    Bottom line (for real though)
                  </p>
                  <p className="text-sm font-medium text-white">{data.bottom_line}</p>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
