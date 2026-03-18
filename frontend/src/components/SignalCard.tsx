import * as React from 'react'
import { cn } from '@/lib/utils'
import type { AgentName, AgentState } from '@/types'
import {
  BarChart2, Activity, TrendingUp, Globe, MessageSquare, Brain,
  ChevronDown, ChevronUp, AlertTriangle,
} from 'lucide-react'

const AGENT_META: Record<AgentName, { label: string; Icon: React.ElementType }> = {
  fundamental: { label: 'Fundamental Analysis', Icon: BarChart2 },
  technical: { label: 'Technical Analysis', Icon: Activity },
  quant: { label: 'Quantitative Factors', Icon: TrendingUp },
  sector: { label: 'Sector & Peers', Icon: Globe },
  sentiment: { label: 'Market Sentiment', Icon: MessageSquare },
  synthesis: { label: 'Synthesis', Icon: Brain },
}

interface SignalCardProps {
  name: AgentName
  state: AgentState
  score?: number
}

export function SignalCard({ name, state, score }: SignalCardProps) {
  const [open, setOpen] = React.useState(false)
  const { label, Icon } = AGENT_META[name]
  const signal = state.signal as Record<string, unknown> | undefined

  if (!signal) return null

  const isPartial = (signal.data_quality as string) === 'partial'

  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] overflow-hidden">
      {/* Header */}
      <button
        className="w-full flex items-center gap-4 p-5 text-left hover:bg-white/[0.02] transition-colors"
        onClick={() => setOpen(o => !o)}
      >
        <div className="w-9 h-9 rounded-lg bg-white/5 flex items-center justify-center flex-shrink-0">
          <Icon className="w-4 h-4 text-purple-400" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-sm text-white">{label}</span>
            {isPartial && (
              <span className="flex items-center gap-1 text-[10px] text-amber-400/80 bg-amber-400/10 border border-amber-400/20 rounded-full px-2 py-0.5">
                <AlertTriangle className="w-2.5 h-2.5" />
                Partial data
              </span>
            )}
          </div>
          <p className="text-xs text-zinc-500 mt-0.5 truncate">
            {getSignalSummary(name, signal)}
          </p>
        </div>
        <div className="flex items-center gap-3 flex-shrink-0">
          {score != null && (
            <ScorePill score={score} name={name} signal={signal} />
          )}
          {open ? (
            <ChevronUp className="w-4 h-4 text-zinc-600" />
          ) : (
            <ChevronDown className="w-4 h-4 text-zinc-600" />
          )}
        </div>
      </button>

      {/* Expanded content */}
      {open && (
        <div className="border-t border-white/5 px-5 pb-5 pt-4">
          {/* Reasoning */}
          {typeof signal.reasoning === 'string' && signal.reasoning && (
            <div className="mb-4">
              <p className="text-xs uppercase tracking-wider text-zinc-600 font-medium mb-2">Reasoning</p>
              <p className="text-sm text-zinc-300 leading-relaxed">{signal.reasoning}</p>
            </div>
          )}

          <AgentDetails name={name} signal={signal} />
        </div>
      )}
    </div>
  )
}

function ScorePill({ score, name, signal }: { score: number; name: AgentName; signal: Record<string, unknown> }) {
  let color = 'text-zinc-400'
  if (name === 'technical') {
    const dir = signal.direction as string
    color = dir === 'bullish' ? 'text-emerald-400' : dir === 'bearish' ? 'text-red-400' : 'text-amber-400'
  } else {
    color = score >= 0.65 ? 'text-emerald-400' : score >= 0.45 ? 'text-amber-400' : 'text-red-400'
  }

  return (
    <span className={cn('font-mono font-bold text-sm tabular-nums', color)}>
      {(score * 100).toFixed(0)}
    </span>
  )
}

function getSignalSummary(name: AgentName, signal: Record<string, unknown>): string {
  switch (name) {
    case 'fundamental': {
      const q = signal.quality_score as number | undefined
      const v = signal.valuation_verdict as string | undefined
      const flags = signal.key_flags as string[] | undefined
      return `Quality ${q != null ? (q * 100).toFixed(0) + '%' : '—'} · ${v ?? '—'}${flags?.length ? ' · ' + flags.slice(0, 2).join(', ') : ''}`
    }
    case 'technical': {
      const dir = signal.direction as string | undefined
      const conf = signal.confidence as number | undefined
      const summary = signal.indicator_summary as string | undefined
      return summary ?? `${dir ?? '—'} · ${conf != null ? (conf * 100).toFixed(0) + '% confidence' : ''}`
    }
    case 'quant': {
      const c = signal.composite_score as number | undefined
      return `Composite score ${c != null ? (c * 100).toFixed(0) + '%' : '—'}`
    }
    case 'sector': {
      const s = signal.sector as string | undefined
      const r = signal.relative_performance as string | undefined
      const etf = signal.sector_etf as string | undefined
      return `${s ?? '—'} · ${r ?? '—'} vs ${etf ?? 'ETF'}`
    }
    case 'sentiment': {
      const adj = signal.adjusted_score as number | undefined
      const vol = signal.mention_volume as number | undefined
      const risk = signal.bot_risk as string | undefined
      return `Score ${adj != null ? (adj > 0 ? '+' : '') + adj.toFixed(2) : '—'} · ${vol ?? 0} mentions · bot risk: ${risk ?? '—'}`
    }
    case 'synthesis': {
      const c = signal.composite_score as number | undefined
      return `Composite ${c != null ? (c * 100).toFixed(0) + '%' : '—'}`
    }
  }
}

function AgentDetails({ name, signal }: { name: AgentName; signal: Record<string, unknown> }) {
  switch (name) {
    case 'fundamental':
      return <FundamentalDetails signal={signal} />
    case 'technical':
      return <TechnicalDetails signal={signal} />
    case 'quant':
      return <QuantDetails signal={signal} />
    case 'sector':
      return <SectorDetails signal={signal} />
    case 'sentiment':
      return <SentimentDetails signal={signal} />
    case 'synthesis':
      return <KVTable data={(signal.factor_breakdown as Record<string, unknown>) ?? {}} label="Breakdown" />
    default:
      return null
  }
}

function FundamentalDetails({ signal }: { signal: Record<string, unknown> }) {
  const metrics = signal.metrics as Record<string, number | null> | undefined
  const flags = signal.key_flags as string[] | undefined
  return (
    <div className="space-y-4">
      {flags && flags.length > 0 && (
        <div>
          <p className="text-xs uppercase tracking-wider text-zinc-600 font-medium mb-2">Key Flags</p>
          <div className="flex flex-wrap gap-1.5">
            {flags.map(f => (
              <span key={f} className="text-xs bg-white/5 border border-white/10 rounded-full px-2.5 py-1 text-zinc-300">
                {f}
              </span>
            ))}
          </div>
        </div>
      )}
      {metrics && <KVTable data={metrics} label="Metrics" />}
    </div>
  )
}

function TechnicalDetails({ signal }: { signal: Record<string, unknown> }) {
  const levels = signal.key_levels as Record<string, number> | undefined
  const indicators = signal.raw_indicators as Record<string, number | null> | undefined
  return (
    <div className="space-y-4">
      {levels && Object.keys(levels).length > 0 && <KVTable data={levels} label="Key Levels" prefix="$" />}
      {indicators && <KVTable data={indicators} label="Indicators" />}
    </div>
  )
}

function QuantDetails({ signal }: { signal: Record<string, unknown> }) {
  const breakdown = signal.factor_breakdown as Record<string, number | null> | undefined
  return <div className="space-y-4">{breakdown && <KVTable data={breakdown} label="Factor Breakdown" />}</div>
}

function SectorDetails({ signal }: { signal: Record<string, unknown> }) {
  const peers = signal.peer_comparison as Record<string, number> | undefined
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 text-sm">
        <Stat label="Sector" value={signal.sector as string} />
        <Stat label="ETF" value={signal.sector_etf as string} />
        <Stat label="Performance" value={signal.relative_performance as string} />
      </div>
      {peers && Object.keys(peers).length > 0 && <KVTable data={peers} label="Peer Comparison" />}
    </div>
  )
}

function SentimentDetails({ signal }: { signal: Record<string, unknown> }) {
  const themes = signal.narrative_themes as string[] | undefined
  const sources = signal.source_breakdown as Record<string, number> | undefined
  const botRisk = signal.bot_risk as string | undefined

  const botColor = botRisk === 'low' ? 'text-emerald-400' : botRisk === 'medium' ? 'text-amber-400' : 'text-red-400'

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <Stat label="Raw Score" value={`${((signal.raw_score as number) > 0 ? '+' : '')}${(signal.raw_score as number)?.toFixed(2)}`} />
        <Stat label="Adj. Score" value={`${((signal.adjusted_score as number) > 0 ? '+' : '')}${(signal.adjusted_score as number)?.toFixed(2)}`} />
        <Stat label="Bot Risk" value={botRisk ?? '—'} valueClass={botColor} />
      </div>
      {sources && <KVTable data={sources} label="Source Breakdown" />}
      {themes && themes.length > 0 && (
        <div>
          <p className="text-xs uppercase tracking-wider text-zinc-600 font-medium mb-2">Narrative Themes</p>
          <div className="flex flex-wrap gap-1.5">
            {themes.map(t => (
              <span key={t} className="text-xs bg-purple-500/10 border border-purple-500/20 rounded-full px-2.5 py-1 text-purple-300">
                {t}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, valueClass }: { label: string; value: string | undefined; valueClass?: string }) {
  return (
    <div className="bg-white/[0.03] rounded-lg p-3">
      <p className="text-xs text-zinc-600 mb-1">{label}</p>
      <p className={cn('text-sm font-medium text-white capitalize', valueClass)}>{value ?? '—'}</p>
    </div>
  )
}

function KVTable({ data, label, prefix = '' }: { data: Record<string, unknown>; label: string; prefix?: string }) {
  const entries = Object.entries(data).filter(([, v]) => v != null)
  if (entries.length === 0) return null
  return (
    <div>
      <p className="text-xs uppercase tracking-wider text-zinc-600 font-medium mb-2">{label}</p>
      <div className="rounded-lg border border-white/5 overflow-hidden">
        {entries.map(([k, v], i) => (
          <div
            key={k}
            className={cn(
              'flex items-center justify-between px-3 py-2 text-xs',
              i % 2 === 0 ? 'bg-white/[0.02]' : 'bg-transparent',
            )}
          >
            <span className="text-zinc-500 capitalize">{k.replace(/_/g, ' ')}</span>
            <span className="font-mono text-zinc-200">
              {prefix}{typeof v === 'number' ? v.toFixed(4).replace(/\.?0+$/, '') : String(v)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
