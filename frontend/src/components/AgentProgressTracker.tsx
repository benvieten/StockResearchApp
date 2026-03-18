import { cn } from '@/lib/utils'
import type { AgentName, AgentState } from '@/types'
import {
  BarChart2,
  Activity,
  TrendingUp,
  Globe,
  MessageSquare,
  Brain,
  CheckCircle,
  Clock,
  AlertCircle,
  Loader2,
} from 'lucide-react'

const AGENT_META: Record<AgentName, { label: string; description: string; Icon: React.ElementType }> = {
  fundamental: {
    label: 'Fundamental',
    description: 'P/E, EPS, revenue growth, balance sheet quality',
    Icon: BarChart2,
  },
  technical: {
    label: 'Technical',
    description: 'EMA, RSI, MACD, Bollinger Bands, support/resistance',
    Icon: Activity,
  },
  quant: {
    label: 'Quantitative',
    description: 'Momentum, value, quality, low-volatility factors',
    Icon: TrendingUp,
  },
  sector: {
    label: 'Sector',
    description: 'Relative sector performance and peer comparison',
    Icon: Globe,
  },
  sentiment: {
    label: 'Sentiment',
    description: 'Reddit, news, social media — bot-adjusted scoring',
    Icon: MessageSquare,
  },
  synthesis: {
    label: 'Synthesis',
    description: 'Combining all signals into a final verdict',
    Icon: Brain,
  },
}

const AGENT_ORDER: AgentName[] = ['fundamental', 'technical', 'quant', 'sector', 'sentiment', 'synthesis']

interface AgentCardProps {
  name: AgentName
  state: AgentState
  index: number
}

function AgentCard({ name, state, index }: AgentCardProps) {
  const { label, description, Icon } = AGENT_META[name]
  const { status } = state

  return (
    <div
      className={cn(
        'relative flex items-start gap-4 p-5 rounded-xl border transition-all duration-500',
        status === 'pending' && 'bg-white/[0.02] border-white/5 opacity-50',
        status === 'running' && 'bg-purple-950/20 border-purple-500/30 shadow-[0_0_20px_rgba(124,58,237,0.1)]',
        status === 'complete' && 'bg-white/[0.04] border-white/10',
        status === 'error' && 'bg-red-950/20 border-red-500/30',
      )}
      style={{ animationDelay: `${index * 60}ms` }}
    >
      {/* Icon */}
      <div
        className={cn(
          'flex-shrink-0 w-10 h-10 rounded-lg flex items-center justify-center',
          status === 'pending' && 'bg-white/5',
          status === 'running' && 'bg-purple-500/20',
          status === 'complete' && 'bg-emerald-500/15',
          status === 'error' && 'bg-red-500/15',
        )}
      >
        <Icon
          className={cn(
            'w-5 h-5',
            status === 'pending' && 'text-zinc-600',
            status === 'running' && 'text-purple-400',
            status === 'complete' && 'text-emerald-400',
            status === 'error' && 'text-red-400',
          )}
        />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2 mb-1">
          <span
            className={cn(
              'font-semibold text-sm',
              status === 'pending' && 'text-zinc-500',
              status === 'running' && 'text-white',
              status === 'complete' && 'text-white',
              status === 'error' && 'text-red-300',
            )}
          >
            {label}
          </span>
          <StatusIcon status={status} />
        </div>
        <p className="text-xs text-zinc-600 leading-relaxed">{description}</p>

        {/* Signal preview on complete */}
        {status === 'complete' && state.signal && (
          <SignalPreview name={name} signal={state.signal} />
        )}
        {status === 'error' && state.error && (
          <p className="mt-1.5 text-xs text-red-400">{state.error}</p>
        )}
      </div>

      {/* Running shimmer */}
      {status === 'running' && (
        <div className="absolute inset-0 rounded-xl overflow-hidden pointer-events-none">
          <div className="absolute inset-0 bg-gradient-to-r from-transparent via-purple-500/5 to-transparent animate-[shimmer_2s_infinite]" />
        </div>
      )}
    </div>
  )
}

function StatusIcon({ status }: { status: AgentState['status'] }) {
  if (status === 'pending') return <Clock className="w-4 h-4 text-zinc-700" />
  if (status === 'running') return <Loader2 className="w-4 h-4 text-purple-400 animate-spin" />
  if (status === 'complete') return <CheckCircle className="w-4 h-4 text-emerald-400" />
  return <AlertCircle className="w-4 h-4 text-red-400" />
}

function SignalPreview({ name, signal }: { name: AgentName; signal: AgentState['signal'] }) {
  if (!signal) return null

  let preview = ''

  if (name === 'fundamental') {
    const s = signal as { quality_score?: number; valuation_verdict?: string }
    preview = `Quality ${((s.quality_score ?? 0) * 100).toFixed(0)}% · ${s.valuation_verdict ?? ''}`
  } else if (name === 'technical') {
    const s = signal as { direction?: string; confidence?: number }
    preview = `${s.direction ?? ''} · ${((s.confidence ?? 0) * 100).toFixed(0)}% confidence`
  } else if (name === 'quant') {
    const s = signal as { composite_score?: number }
    preview = `Composite score ${((s.composite_score ?? 0) * 100).toFixed(0)}%`
  } else if (name === 'sector') {
    const s = signal as { sector?: string; relative_performance?: string }
    preview = `${s.sector ?? ''} · ${s.relative_performance ?? ''}`
  } else if (name === 'sentiment') {
    const s = signal as { adjusted_score?: number; mention_volume?: number }
    const score = s.adjusted_score ?? 0
    preview = `Score ${score > 0 ? '+' : ''}${score.toFixed(2)} · ${s.mention_volume ?? 0} mentions`
  } else if (name === 'synthesis') {
    const s = signal as { composite_score?: number }
    preview = `Composite ${((s.composite_score ?? 0) * 100).toFixed(0)}%`
  }

  return (
    <p className="mt-2 text-xs font-mono text-emerald-400/80 bg-emerald-500/5 rounded-md px-2 py-1 inline-block">
      {preview}
    </p>
  )
}

interface AgentProgressTrackerProps {
  ticker: string
  agents: Partial<Record<AgentName, AgentState>>
  error: string | null
}

export function AgentProgressTracker({ ticker, agents, error }: AgentProgressTrackerProps) {
  const completedCount = AGENT_ORDER.filter(a => agents[a]?.status === 'complete').length
  const progress = (completedCount / AGENT_ORDER.length) * 100

  return (
    <div className="min-h-screen bg-[#080808] flex flex-col">
      {/* Header */}
      <div className="border-b border-white/5 px-8 py-5">
        <div className="max-w-3xl mx-auto flex items-center justify-between">
          <div>
            <div className="flex items-center gap-3">
              <span className="font-mono text-2xl font-bold text-white">{ticker}</span>
              <span className="text-xs text-zinc-500 bg-white/5 border border-white/10 rounded-full px-3 py-1">
                Analyzing
              </span>
            </div>
            <p className="text-sm text-zinc-500 mt-0.5">
              {completedCount} of {AGENT_ORDER.length} agents complete
            </p>
          </div>
          <div className="text-right">
            <div className="text-2xl font-bold text-white">
              {completedCount}/{AGENT_ORDER.length}
            </div>
            <div className="text-xs text-zinc-600">agents done</div>
          </div>
        </div>

        {/* Progress bar */}
        <div className="max-w-3xl mx-auto mt-4">
          <div className="h-1 bg-white/5 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-purple-600 to-purple-400 rounded-full transition-all duration-700 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      </div>

      {/* Agent cards */}
      <div className="flex-1 max-w-3xl mx-auto w-full px-4 py-8">
        {error && (
          <div className="mb-6 p-4 rounded-xl bg-red-950/30 border border-red-500/30 text-red-300 text-sm">
            <AlertCircle className="inline w-4 h-4 mr-2" />
            {error}
          </div>
        )}

        <div className="flex flex-col gap-3">
          {AGENT_ORDER.map((name, i) => (
            <AgentCard
              key={name}
              name={name}
              index={i}
              state={agents[name] ?? { status: 'pending' }}
            />
          ))}
        </div>

        {/* Waiting note */}
        {completedCount === 0 && !error && (
          <p className="text-center text-zinc-600 text-sm mt-8">
            Fetching market data and starting agents…
          </p>
        )}
      </div>
    </div>
  )
}
