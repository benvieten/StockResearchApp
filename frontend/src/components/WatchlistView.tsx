import { useState, useEffect } from 'react'
import type { FinalReport, WatchlistResult } from '@/types'

// ── Verdict helpers ───────────────────────────────────────────────────────────

const VERDICT_COLORS: Record<string, string> = {
  strong_buy: 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40',
  buy:        'bg-green-500/20  text-green-300  border border-green-500/40',
  hold:       'bg-amber-500/20  text-amber-300  border border-amber-500/40',
  sell:       'bg-orange-500/20 text-orange-300 border border-orange-500/40',
  strong_sell:'bg-red-500/20    text-red-300    border border-red-500/40',
}

const CONVICTION_COLORS: Record<string, string> = {
  high:   'text-emerald-400',
  medium: 'text-amber-400',
  low:    'text-slate-400',
}

function verdictLabel(v: string): string {
  return v.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function avgScore(report: FinalReport): number {
  const vals = Object.values(report.signal_scores)
  return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0
}

// ── Stock card ────────────────────────────────────────────────────────────────

function StockCard({
  report,
  onAnalyze,
}: {
  report: FinalReport
  onAnalyze: (ticker: string) => void
}) {
  const score = avgScore(report)
  const pct = Math.round(score * 100)

  return (
    <div className="bg-[#111] border border-white/8 rounded-xl p-4 flex flex-col gap-3 hover:border-white/20 transition-colors">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <button
          onClick={() => onAnalyze(report.ticker)}
          className="text-lg font-bold text-white hover:text-violet-300 transition-colors"
        >
          {report.ticker}
        </button>
        <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${VERDICT_COLORS[report.verdict] ?? ''}`}>
          {verdictLabel(report.verdict)}
        </span>
      </div>

      {/* Composite score bar */}
      <div>
        <div className="flex justify-between text-xs text-slate-400 mb-1">
          <span>Composite</span>
          <span className="font-medium text-white">{pct}%</span>
        </div>
        <div className="h-1.5 bg-white/8 rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all"
            style={{
              width: `${pct}%`,
              backgroundColor: pct >= 70 ? '#34d399' : pct >= 50 ? '#fbbf24' : '#f87171',
            }}
          />
        </div>
      </div>

      {/* Conviction */}
      <div className="flex gap-4 text-xs">
        <span className="text-slate-500">Conviction</span>
        <span className={`font-semibold capitalize ${CONVICTION_COLORS[report.conviction] ?? ''}`}>
          {report.conviction}
        </span>
      </div>

      {/* Narrative */}
      <p className="text-xs text-slate-400 leading-relaxed line-clamp-3">
        {report.narrative}
      </p>

      {/* Horizon rationale */}
      <p className="text-xs text-violet-300/80 italic line-clamp-2">
        {report.horizon_rationale}
      </p>

      {/* Deep-dive button */}
      <button
        onClick={() => onAnalyze(report.ticker)}
        className="mt-auto text-xs text-violet-400 hover:text-violet-200 underline underline-offset-2 text-left transition-colors"
      >
        Run full analysis →
      </button>
    </div>
  )
}

// ── Column ────────────────────────────────────────────────────────────────────

const HORIZON_META: Record<string, { label: string; subtitle: string; accent: string }> = {
  short_term:  { label: 'Short Term',  subtitle: 'Days to weeks',    accent: 'border-t-sky-500' },
  medium_term: { label: 'Medium Term', subtitle: 'Weeks to months',  accent: 'border-t-violet-500' },
  long_term:   { label: 'Long Term',   subtitle: '1+ year',          accent: 'border-t-emerald-500' },
}

function HorizonColumn({
  horizon,
  reports,
  onAnalyze,
}: {
  horizon: string
  reports: FinalReport[]
  onAnalyze: (ticker: string) => void
}) {
  const meta = HORIZON_META[horizon] ?? { label: horizon, subtitle: '', accent: 'border-t-white/20' }

  return (
    <div className={`flex flex-col gap-3 bg-white/3 border border-white/8 border-t-2 ${meta.accent} rounded-xl p-4`}>
      <div className="mb-1">
        <h3 className="text-sm font-bold text-white">{meta.label}</h3>
        <p className="text-xs text-slate-500">{meta.subtitle}</p>
      </div>

      {reports.length === 0 ? (
        <p className="text-xs text-slate-600 italic">No picks in this horizon</p>
      ) : (
        reports.map(r => (
          <StockCard key={r.ticker} report={r} onAnalyze={onAnalyze} />
        ))
      )}
    </div>
  )
}

// ── Main view ─────────────────────────────────────────────────────────────────

interface Props {
  onAnalyze: (ticker: string) => void
  onBack: () => void
}

type LoadState = 'idle' | 'loading' | 'done' | 'error'

export function WatchlistView({ onAnalyze, onBack }: Props) {
  const [loadState, setLoadState] = useState<LoadState>('idle')
  const [result, setResult] = useState<WatchlistResult | null>(null)
  const [tickers, setTickers] = useState<string[]>([])
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  // Fetch ticker list on mount to show user what will be analyzed
  useEffect(() => {
    fetch('/api/watchlist/tickers')
      .then(r => r.json() as Promise<{ tickers: string[] }>)
      .then(d => setTickers(d.tickers))
      .catch(() => {})
  }, [])

  const runWatchlist = async () => {
    setLoadState('loading')
    setErrorMsg(null)
    try {
      const res = await fetch('/api/watchlist', { method: 'POST' })
      if (!res.ok) {
        const j = await res.json().catch(() => ({})) as { detail?: string }
        throw new Error(j.detail ?? `HTTP ${res.status}`)
      }
      const data = await res.json() as WatchlistResult
      setResult(data)
      setLoadState('done')
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Unknown error')
      setLoadState('error')
    }
  }

  const totalResults = result
    ? result.short_term.length + result.medium_term.length + result.long_term.length
    : 0

  return (
    <div className="min-h-screen bg-[#080808] text-white px-4 py-10 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-4 mb-8">
        <button
          onClick={onBack}
          className="text-slate-400 hover:text-white text-sm transition-colors"
        >
          ← Back
        </button>
        <div>
          <h1 className="text-2xl font-bold">Agent-Curated Watchlist</h1>
          <p className="text-sm text-slate-400 mt-0.5">
            Discovered today from Yahoo Finance trending, market screeners, and Reddit
            {tickers.length > 0 ? ` · ${tickers.length} candidates` : ''}
          </p>
        </div>
      </div>

      {/* Ticker chips */}
      {tickers.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-8">
          {tickers.map(t => (
            <span key={t} className="text-xs bg-white/6 border border-white/10 rounded-full px-3 py-1 text-slate-300">
              {t}
            </span>
          ))}
        </div>
      )}

      {/* Idle state — run button */}
      {loadState === 'idle' && (
        <div className="flex flex-col items-center gap-4 py-20">
          <p className="text-slate-400 text-sm text-center max-w-md">
            Runs today's {tickers.length > 0 ? tickers.length : 'discovered'} tickers through the full
            6-agent pipeline and groups them by best investment time horizon.
            Discovery and data are cached daily — same-day re-runs are fast.
          </p>
          <button
            onClick={runWatchlist}
            className="px-8 py-3 bg-violet-600 hover:bg-violet-500 rounded-xl font-semibold text-white transition-colors"
          >
            Analyze Watchlist
          </button>
        </div>
      )}

      {/* Loading state */}
      {loadState === 'loading' && (
        <div className="flex flex-col items-center gap-4 py-20">
          <div className="w-10 h-10 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-slate-400 text-sm">
            Running {tickers.length} tickers through the pipeline…
          </p>
          <p className="text-slate-600 text-xs">This may take 1–3 minutes on first run</p>
        </div>
      )}

      {/* Error state */}
      {loadState === 'error' && (
        <div className="flex flex-col items-center gap-4 py-20">
          <p className="text-red-400 text-sm">{errorMsg}</p>
          <button
            onClick={runWatchlist}
            className="px-6 py-2 bg-white/8 hover:bg-white/12 rounded-lg text-sm transition-colors"
          >
            Retry
          </button>
        </div>
      )}

      {/* Results */}
      {loadState === 'done' && result && (
        <>
          <div className="flex items-center justify-between mb-6">
            <p className="text-sm text-slate-400">
              {totalResults} of {tickers.length} tickers analyzed successfully
            </p>
            <button
              onClick={runWatchlist}
              className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
            >
              Re-run analysis
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            {(['short_term', 'medium_term', 'long_term'] as const).map(h => (
              <HorizonColumn
                key={h}
                horizon={h}
                reports={result[h]}
                onAnalyze={onAnalyze}
              />
            ))}
          </div>
        </>
      )}
    </div>
  )
}
