import { cn } from '@/lib/utils'
import type { FinalReport } from '@/types'
import { TrendingUp, TrendingDown, Minus, ChevronUp, ChevronDown } from 'lucide-react'

const VERDICT_CONFIG = {
  strong_buy: {
    label: 'Strong Buy',
    color: 'text-emerald-400',
    bg: 'bg-emerald-400/10',
    border: 'border-emerald-400/30',
    glow: 'shadow-[0_0_40px_rgba(52,211,153,0.12)]',
    Icon: ChevronUp,
  },
  buy: {
    label: 'Buy',
    color: 'text-green-400',
    bg: 'bg-green-400/10',
    border: 'border-green-400/30',
    glow: 'shadow-[0_0_40px_rgba(74,222,128,0.08)]',
    Icon: TrendingUp,
  },
  hold: {
    label: 'Hold',
    color: 'text-amber-400',
    bg: 'bg-amber-400/10',
    border: 'border-amber-400/30',
    glow: 'shadow-[0_0_40px_rgba(251,191,36,0.08)]',
    Icon: Minus,
  },
  sell: {
    label: 'Sell',
    color: 'text-orange-400',
    bg: 'bg-orange-400/10',
    border: 'border-orange-400/30',
    glow: 'shadow-[0_0_40px_rgba(251,146,60,0.08)]',
    Icon: TrendingDown,
  },
  strong_sell: {
    label: 'Strong Sell',
    color: 'text-red-400',
    bg: 'bg-red-400/10',
    border: 'border-red-400/30',
    glow: 'shadow-[0_0_40px_rgba(248,113,113,0.10)]',
    Icon: ChevronDown,
  },
}

const CONVICTION_CONFIG = {
  high: { label: 'High Conviction', color: 'text-zinc-200', dot: 'bg-emerald-400' },
  medium: { label: 'Medium Conviction', color: 'text-zinc-400', dot: 'bg-amber-400' },
  low: { label: 'Low Conviction', color: 'text-zinc-500', dot: 'bg-zinc-500' },
}

interface VerdictCardProps {
  report: FinalReport
}

export function VerdictCard({ report }: VerdictCardProps) {
  const cfg = VERDICT_CONFIG[report.verdict]
  const conv = CONVICTION_CONFIG[report.conviction]
  const { Icon } = cfg

  // Compute average signal score
  const scores = Object.values(report.signal_scores).filter(v => v != null)
  const avgScore = scores.length > 0 ? scores.reduce((a, b) => a + b, 0) / scores.length : 0

  return (
    <div className={cn('rounded-2xl border p-8', cfg.bg, cfg.border, cfg.glow)}>
      <div className="flex items-start justify-between gap-6 flex-wrap">
        {/* Verdict */}
        <div>
          <div className="flex items-center gap-3 mb-3">
            <div className={cn('w-12 h-12 rounded-xl flex items-center justify-center', cfg.bg, cfg.border, 'border')}>
              <Icon className={cn('w-6 h-6', cfg.color)} />
            </div>
            <div>
              <p className="text-xs text-zinc-500 uppercase tracking-wider font-medium mb-0.5">Verdict</p>
              <h2 className={cn('text-3xl font-bold tracking-tight', cfg.color)}>{cfg.label}</h2>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className={cn('w-2 h-2 rounded-full', conv.dot)} />
            <span className={cn('text-sm font-medium', conv.color)}>{conv.label}</span>
          </div>
        </div>

        {/* Score ring */}
        <div className="flex flex-col items-center gap-1">
          <ScoreRing score={avgScore} colorClass={cfg.color} />
          <p className="text-xs text-zinc-600">avg signal score</p>
        </div>
      </div>

      {/* Narrative */}
      <p className="mt-6 text-zinc-300 text-sm leading-relaxed border-t border-white/5 pt-5">
        {report.narrative}
      </p>

      {/* Generated at */}
      <p className="mt-4 text-xs text-zinc-700">
        Generated {new Date(report.generated_at).toLocaleString()}
      </p>
    </div>
  )
}

function ScoreRing({ score, colorClass }: { score: number; colorClass: string }) {
  const r = 32
  const circ = 2 * Math.PI * r
  const offset = circ * (1 - score)

  return (
    <div className="relative w-20 h-20 flex items-center justify-center">
      <svg className="absolute inset-0 -rotate-90" width="80" height="80">
        <circle cx="40" cy="40" r={r} stroke="rgba(255,255,255,0.05)" strokeWidth="6" fill="none" />
        <circle
          cx="40"
          cy="40"
          r={r}
          strokeWidth="6"
          fill="none"
          className={cn('transition-all duration-1000', colorClass)}
          stroke="currentColor"
          strokeDasharray={circ}
          strokeDashoffset={offset}
          strokeLinecap="round"
        />
      </svg>
      <span className={cn('text-lg font-bold font-mono', colorClass)}>
        {(score * 100).toFixed(0)}
      </span>
    </div>
  )
}
