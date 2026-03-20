import { useState } from 'react'
import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'
import type { AgentName, AgentState, FinalReport, RegimeInfo, TraderProfile } from '@/types'
import { VerdictCard } from '@/components/VerdictCard'
import { SignalCard } from '@/components/SignalCard'
import { DummiesMode } from '@/components/DummiesMode'
import { ExplainTab } from '@/components/ExplainTab'
import { ArrowLeft, CheckCircle, XCircle, AlertCircle, Brain, TrendingUp, TrendingDown, Minus, BookOpen, BarChart2 } from 'lucide-react'

const AGENT_ORDER: AgentName[] = ['fundamental', 'technical', 'quant', 'sector', 'sentiment', 'synthesis']

interface ReportDashboardProps {
  ticker: string
  report: FinalReport
  agents: Partial<Record<AgentName, AgentState>>
  regime: RegimeInfo | null
  traderProfile: TraderProfile | null
  onReset: () => void
}

type DashTab = 'report' | 'explain'

export function ReportDashboard({ ticker, report, agents, regime, traderProfile, onReset }: ReportDashboardProps) {
  const [activeTab, setActiveTab] = useState<DashTab>('report')

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
            {regime && <RegimeBadge regime={regime} />}
          </div>
          <div className="flex items-center gap-2 text-xs text-zinc-500">
            <Brain className="w-3.5 h-3.5 text-purple-400" />
            StockResearch AI
          </div>
        </div>

        {/* Tab switcher */}
        <div className="max-w-5xl mx-auto mt-3 flex items-center gap-1">
          <TabButton active={activeTab === 'report'} onClick={() => setActiveTab('report')}>
            <BarChart2 className="w-3.5 h-3.5" />
            Analysis
          </TabButton>
          <TabButton active={activeTab === 'explain'} onClick={() => setActiveTab('explain')}>
            <BookOpen className="w-3.5 h-3.5" />
            How to Read This
          </TabButton>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-4 py-8">
        {activeTab === 'report' && (
          <div className="space-y-8">
            {traderProfile && <TraderProfileChip profile={traderProfile} />}
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
        )}

        {activeTab === 'explain' && <ExplainTab />}
      </div>
    </div>
  )
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
        active
          ? 'bg-white/10 text-white'
          : 'text-zinc-500 hover:text-zinc-300 hover:bg-white/5',
      )}
    >
      {children}
    </button>
  )
}

function RegimeBadge({ regime }: { regime: RegimeInfo }) {
  const configs = {
    bull:         { Icon: TrendingUp,   color: 'text-emerald-400', bg: 'bg-emerald-400/10 border-emerald-400/20' },
    bear:         { Icon: TrendingDown, color: 'text-red-400',     bg: 'bg-red-400/10 border-red-400/20' },
    transitional: { Icon: Minus,        color: 'text-amber-400',   bg: 'bg-amber-400/10 border-amber-400/20' },
  }
  const { Icon, color, bg } = configs[regime.regime]
  const confPct = Math.round(regime.confidence * 100)

  return (
    <span className={cn('flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium', bg, color)}>
      <Icon className="w-3 h-3" />
      {regime.regime.charAt(0).toUpperCase() + regime.regime.slice(1)} market · {confPct}%
      {regime.vix != null && <span className="text-inherit opacity-60 ml-1">VIX {regime.vix.toFixed(0)}</span>}
    </span>
  )
}

const PROFILE_LABELS = {
  risk_tolerance: { conservative: 'Conservative', moderate: 'Moderate', aggressive: 'Aggressive' },
  time_horizon:   { short_term: 'Short-term', medium_term: 'Medium-term', long_term: 'Long-term' },
  goal:           { growth: 'Growth', income: 'Income', preservation: 'Preservation', speculation: 'Speculation' },
  experience:     { beginner: 'Beginner', intermediate: 'Intermediate', experienced: 'Experienced' },
} as const

function TraderProfileChip({ profile }: { profile: TraderProfile }) {
  const items = [
    PROFILE_LABELS.risk_tolerance[profile.risk_tolerance],
    PROFILE_LABELS.time_horizon[profile.time_horizon],
    PROFILE_LABELS.goal[profile.goal],
    PROFILE_LABELS.experience[profile.experience],
  ]
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <span className="text-xs text-zinc-600 uppercase tracking-wider font-medium">Profile</span>
      {items.map(label => (
        <span key={label} className="text-xs px-2.5 py-1 rounded-full bg-purple-500/10 border border-purple-500/20 text-purple-300">
          {label}
        </span>
      ))}
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
