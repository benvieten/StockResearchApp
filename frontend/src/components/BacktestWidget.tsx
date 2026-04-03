import { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'
import { History, TrendingUp, TrendingDown, Clock } from 'lucide-react'

interface Prediction {
  verdict: string
  conviction: string
  composite_score: number | null
  horizon: string | null
  price_at_prediction: number | null
  predicted_at: string
  status: 'matured' | 'pending'
  elapsed_days: number
  target_days: number
  current_price?: number | null
  actual_return?: number | null
}

interface BacktestWidgetProps {
  ticker: string
}

export function BacktestWidget({ ticker }: BacktestWidgetProps) {
  const [predictions, setPredictions] = useState<Prediction[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`http://localhost:8000/backtest/${ticker}`)
      .then(r => r.json())
      .then(data => setPredictions(data.predictions ?? []))
      .catch(() => setPredictions([]))
      .finally(() => setLoading(false))
  }, [ticker])

  if (loading || predictions.length === 0) return null

  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-5">
      <div className="flex items-center gap-2 mb-4">
        <History className="w-4 h-4 text-zinc-400" />
        <p className="text-xs uppercase tracking-wider text-zinc-600 font-medium">
          Prior Predictions
        </p>
        <span className="text-xs text-zinc-700 ml-auto">{predictions.length} record{predictions.length !== 1 ? 's' : ''}</span>
      </div>

      <div className="space-y-2">
        {predictions.map((p, i) => (
          <PredictionRow key={i} p={p} />
        ))}
      </div>
    </div>
  )
}

function PredictionRow({ p }: { p: Prediction }) {
  const date = new Date(p.predicted_at).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
  })

  const verdictColor =
    p.verdict === 'strong_buy'  ? 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20' :
    p.verdict === 'buy'         ? 'text-emerald-300 bg-emerald-300/10 border-emerald-300/20' :
    p.verdict === 'hold'        ? 'text-amber-400 bg-amber-400/10 border-amber-400/20' :
    p.verdict === 'sell'        ? 'text-red-400 bg-red-400/10 border-red-400/20' :
                                  'text-red-500 bg-red-500/10 border-red-500/20'

  const returnVal = p.actual_return
  const returnDisplay =
    returnVal == null
      ? null
      : `${returnVal >= 0 ? '+' : ''}${(returnVal * 100).toFixed(1)}%`

  const returnColor =
    returnVal == null ? '' :
    returnVal >= 0.05  ? 'text-emerald-400' :
    returnVal >= 0     ? 'text-emerald-300' :
    returnVal >= -0.05 ? 'text-red-300' :
                         'text-red-400'

  const horizonLabel: Record<string, string> = {
    short_term: '30d', medium_term: '60d', long_term: '90d',
  }

  return (
    <div className="flex items-center gap-3 text-xs py-2 border-b border-white/5 last:border-0">
      {/* Date */}
      <span className="text-zinc-500 w-24 flex-shrink-0">{date}</span>

      {/* Verdict badge */}
      <span className={cn('px-2 py-0.5 rounded border font-medium flex-shrink-0', verdictColor)}>
        {p.verdict.replace('_', ' ')}
      </span>

      {/* Horizon */}
      <span className="text-zinc-600 flex-shrink-0">
        {p.horizon ? horizonLabel[p.horizon] ?? p.horizon : '—'}
      </span>

      {/* Entry price */}
      {p.price_at_prediction != null && (
        <span className="text-zinc-500 flex-shrink-0">
          @ ${p.price_at_prediction.toFixed(2)}
        </span>
      )}

      <div className="flex-1" />

      {/* Outcome */}
      {p.status === 'matured' ? (
        <div className="flex items-center gap-1.5">
          {returnDisplay != null ? (
            <>
              {(p.actual_return ?? 0) >= 0
                ? <TrendingUp className="w-3 h-3 text-emerald-400" />
                : <TrendingDown className="w-3 h-3 text-red-400" />}
              <span className={cn('font-mono font-medium', returnColor)}>{returnDisplay}</span>
              {p.current_price != null && (
                <span className="text-zinc-600">→ ${p.current_price.toFixed(2)}</span>
              )}
            </>
          ) : (
            <span className="text-zinc-600 italic">price unavailable</span>
          )}
        </div>
      ) : (
        <div className="flex items-center gap-1.5 text-zinc-600">
          <Clock className="w-3 h-3" />
          <span>{p.elapsed_days}/{p.target_days}d</span>
        </div>
      )}
    </div>
  )
}
