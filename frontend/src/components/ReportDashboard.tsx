import { useState, useEffect } from 'react'
import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'
import type { AgentName, AgentState, FinalReport, RegimeInfo, TraderProfile } from '@/types'
import { VerdictCard } from '@/components/VerdictCard'
import { SignalCard } from '@/components/SignalCard'
import { DummiesMode } from '@/components/DummiesMode'
import { ExplainTab } from '@/components/ExplainTab'
import { ArrowLeft, Bookmark, BookmarkCheck, CheckCircle, XCircle, AlertCircle, Brain, TrendingUp, TrendingDown, Minus, BookOpen, BarChart2 } from 'lucide-react'
import { BacktestWidget } from '@/components/BacktestWidget'

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
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    fetch(`/api/saved-tickers`)
      .then(r => r.json())
      .then(d => setSaved((d.tickers ?? []).some((t: { ticker: string }) => t.ticker === ticker)))
      .catch(() => {})
  }, [ticker])

  async function handleToggleSave() {
    setSaving(true)
    try {
      if (saved) {
        await fetch(`/api/saved-tickers/${ticker}`, { method: 'DELETE' })
        setSaved(false)
      } else {
        await fetch(`/api/saved-tickers/${ticker}`, { method: 'POST' })
        setSaved(true)
      }
    } finally {
      setSaving(false)
    }
  }

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
          <div className="flex items-center gap-3">
            <button
              onClick={handleToggleSave}
              disabled={saving}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors disabled:opacity-50',
                saved
                  ? 'bg-violet-600/20 text-violet-300 border-violet-500/30 hover:bg-red-500/10 hover:text-red-400 hover:border-red-500/30'
                  : 'bg-white/5 text-zinc-400 border-white/10 hover:bg-violet-600/20 hover:text-violet-300 hover:border-violet-500/30',
              )}
            >
              {saved ? <BookmarkCheck className="w-3.5 h-3.5" /> : <Bookmark className="w-3.5 h-3.5" />}
              {saved ? 'Saved' : 'Save'}
            </button>
            <div className="flex items-center gap-2 text-xs text-zinc-500">
              <Brain className="w-3.5 h-3.5 text-purple-400" />
              StockResearch AI
            </div>
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

            {/* Prior predictions track record */}
            <BacktestWidget ticker={ticker} />

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
    fundamental: 'Fundamental',
    technical: 'Technical',
    quant: 'Quantitative',
    sector: 'Sector',
    sentiment: 'Sentiment',
  }

  const scores = agents
    .map(name => ({ name, pct: Math.round((report.signal_scores[name] ?? 0) * 100) }))
    .filter(({ pct }) => pct > 0)

  const avg = Math.round(scores.reduce((s, x) => s + x.pct, 0) / scores.length)

  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-5">
      <div className="flex items-center justify-between mb-5">
        <p className="text-xs uppercase tracking-wider text-zinc-600 font-medium">Signal Scores</p>
        <span className="text-xs text-zinc-500 font-mono">avg <span className="text-zinc-300 font-semibold">{avg}</span></span>
      </div>

      <div className="space-y-3">
        {scores.map(({ name, pct }) => {
          const barColor =
            pct >= 65 ? 'bg-emerald-500' :
            pct >= 50 ? 'bg-amber-500' :
            'bg-red-500'
          const textColor =
            pct >= 65 ? 'text-emerald-400' :
            pct >= 50 ? 'text-amber-400' :
            'text-red-400'
          const badgeBg =
            pct >= 65 ? 'bg-emerald-500/10 border-emerald-500/20' :
            pct >= 50 ? 'bg-amber-500/10 border-amber-500/20' :
            'bg-red-500/10 border-red-500/20'

          return (
            <div key={name} className="flex items-center gap-3">
              <span className="text-xs text-zinc-400 w-24 flex-shrink-0">{labels[name]}</span>
              <div className="flex-1 h-1.5 bg-white/5 rounded-full overflow-hidden">
                <div
                  className={cn('h-full rounded-full transition-all duration-700', barColor)}
                  style={{ width: `${pct}%` }}
                />
              </div>
              {/* neutral midpoint tick */}
              <span className={cn('text-xs font-mono font-semibold w-8 text-right flex-shrink-0 border rounded px-1', textColor, badgeBg)}>
                {pct}
              </span>
            </div>
          )
        })}
      </div>

      {/* reference line labels */}
      <div className="mt-3 ml-[6.5rem] flex justify-between text-[10px] text-zinc-700 font-mono">
        <span>0</span>
        <span>25</span>
        <span>50</span>
        <span>75</span>
        <span>100</span>
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
