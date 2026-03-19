import { cn } from '@/lib/utils'
import type { AgentName, AgentState, FinalReport } from '@/types'
import { VerdictCard } from '@/components/VerdictCard'
import { SignalCard } from '@/components/SignalCard'
import { DummiesMode } from '@/components/DummiesMode'
import { ArrowLeft, CheckCircle, XCircle, AlertCircle, Brain } from 'lucide-react'

const AGENT_ORDER: AgentName[] = ['fundamental', 'technical', 'quant', 'sector', 'sentiment', 'synthesis']

interface ReportDashboardProps {
  ticker: string
  report: FinalReport
  agents: Partial<Record<AgentName, AgentState>>
  onReset: () => void
}

export function ReportDashboard({ ticker, report, agents, onReset }: ReportDashboardProps) {
  return (
    <div className="min-h-screen bg-[#080808]">
      {/* Top bar */}
      <div className="border-b border-white/5 px-6 py-4 sticky top-0 z-20 bg-[#080808]/95 backdrop-blur-sm">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={onReset}
              className="flex items-center gap-1.5 text-sm text-zinc-500 hover:text-white transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              New search
            </button>
            <div className="w-px h-4 bg-white/10" />
            <span className="font-mono font-bold text-white text-lg">{ticker}</span>
            <span className="text-xs text-zinc-600">
              {new Date(report.generated_at).toLocaleDateString('en-US', {
                month: 'short', day: 'numeric', year: 'numeric',
              })}
            </span>
          </div>
          <div className="flex items-center gap-2 text-xs text-zinc-500">
            <Brain className="w-3.5 h-3.5 text-purple-400" />
            StockResearch AI
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-4 py-8 space-y-8">
        {/* Verdict */}
        <VerdictCard report={report} />

        {/* Dummies mode */}
        <DummiesMode report={report} />

        {/* Signal scores bar */}
        <SignalScoreBar report={report} />

        {/* Bull / Bear / Conflicts */}
        <div className="grid md:grid-cols-3 gap-4">
          <CaseList title="Bull Case" items={report.bull_case} variant="bull" />
          <CaseList title="Bear Case" items={report.bear_case} variant="bear" />
          <CaseList title="Conflicts" items={report.conflicts} variant="conflict" />
        </div>

        {/* Agent signal cards */}
        <div>
          <h3 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider mb-4">
            Agent Signals
          </h3>
          <div className="space-y-3">
            {AGENT_ORDER.map(name => {
              const state = agents[name]
              const score = report.signal_scores[name]
              if (!state?.signal) return null
              return <SignalCard key={name} name={name} state={state} score={score} />
            })}
          </div>
        </div>
      </div>
    </div>
  )
}

function SignalScoreBar({ report }: { report: FinalReport }) {
  const agents: AgentName[] = ['fundamental', 'technical', 'quant', 'sector', 'sentiment']
  const labels: Record<string, string> = {
    fundamental: 'Fund.',
    technical: 'Tech.',
    quant: 'Quant',
    sector: 'Sector',
    sentiment: 'Sent.',
  }

  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-5">
      <p className="text-xs uppercase tracking-wider text-zinc-600 font-medium mb-5">Signal Scores</p>
      <div className="flex items-end gap-3">
        {agents.map(name => {
          const score = report.signal_scores[name]
          if (score == null) return null
          const pct = Math.round(score * 100)
          const color =
            pct >= 65 ? 'from-emerald-500 to-emerald-400' :
            pct >= 50 ? 'from-amber-500 to-amber-400' :
            'from-red-500 to-red-400'

          return (
            <div key={name} className="flex-1 flex flex-col items-center gap-2">
              <span className="text-xs font-mono text-zinc-300 font-medium">{pct}</span>
              <div className="w-full bg-white/5 rounded-full overflow-hidden" style={{ height: '80px' }}>
                <div
                  className={cn('w-full rounded-full bg-gradient-to-t transition-all duration-1000', color)}
                  style={{ height: `${pct}%`, marginTop: `${100 - pct}%` }}
                />
              </div>
              <span className="text-[11px] text-zinc-600">{labels[name]}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

type CaseVariant = 'bull' | 'bear' | 'conflict'

function CaseList({ title, items, variant }: { title: string; items: string[]; variant: CaseVariant }) {
  const config = {
    bull: {
      Icon: CheckCircle,
      iconClass: 'text-emerald-400',
      bg: 'bg-emerald-400/5 border-emerald-400/15',
      dotClass: 'bg-emerald-400',
    },
    bear: {
      Icon: XCircle,
      iconClass: 'text-red-400',
      bg: 'bg-red-400/5 border-red-400/15',
      dotClass: 'bg-red-400',
    },
    conflict: {
      Icon: AlertCircle,
      iconClass: 'text-amber-400',
      bg: 'bg-amber-400/5 border-amber-400/15',
      dotClass: 'bg-amber-400',
    },
  }[variant]

  const { Icon, iconClass, bg, dotClass } = config

  return (
    <div className={cn('rounded-xl border p-5', bg)}>
      <div className="flex items-center gap-2 mb-4">
        <Icon className={cn('w-4 h-4', iconClass)} />
        <p className="text-sm font-semibold text-white">{title}</p>
      </div>
      {items.length === 0 ? (
        <p className="text-xs text-zinc-600 italic">None identified</p>
      ) : (
        <ul className="space-y-2.5">
          {items.map((item, i) => (
            <li key={i} className="flex items-start gap-2.5 text-xs text-zinc-300 leading-relaxed">
              <span className={cn('w-1.5 h-1.5 rounded-full mt-1 flex-shrink-0', dotClass)} />
              {item}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
