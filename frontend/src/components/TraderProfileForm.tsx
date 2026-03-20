import * as React from 'react'
import { cn } from '@/lib/utils'
import type { TraderProfile, RiskTolerance, TimeHorizon, TraderGoal, Experience } from '@/types'

interface TraderProfileFormProps {
  ticker: string
  onSubmit: (profile: TraderProfile) => void
  onBack: () => void
}

interface Question<T extends string> {
  id: string
  label: string
  options: { value: T; label: string; sub: string }[]
}

const RISK_QUESTION: Question<RiskTolerance> = {
  id: 'risk_tolerance',
  label: 'What is your risk tolerance?',
  options: [
    { value: 'conservative', label: 'Conservative', sub: 'I prioritise protecting my capital over chasing gains' },
    { value: 'moderate',     label: 'Moderate',     sub: 'I can handle some swings in exchange for decent returns' },
    { value: 'aggressive',   label: 'Aggressive',   sub: 'I accept big drawdowns for the chance at big upside' },
  ],
}

const HORIZON_QUESTION: Question<TimeHorizon> = {
  id: 'time_horizon',
  label: 'How long do you plan to hold?',
  options: [
    { value: 'short_term',  label: 'Short-term',  sub: 'Days to a few weeks' },
    { value: 'medium_term', label: 'Medium-term', sub: 'A few months up to a year' },
    { value: 'long_term',   label: 'Long-term',   sub: 'One year or more' },
  ],
}

const GOAL_QUESTION: Question<TraderGoal> = {
  id: 'goal',
  label: 'What is your primary goal?',
  options: [
    { value: 'growth',       label: 'Capital Growth',       sub: 'Grow the value of my investment over time' },
    { value: 'income',       label: 'Income',               sub: 'Dividends and steady cash returns' },
    { value: 'preservation', label: 'Capital Preservation', sub: "Don't lose what I already have" },
    { value: 'speculation',  label: 'Speculation',          sub: 'High-risk, high-reward — I know what I am doing' },
  ],
}

const EXPERIENCE_QUESTION: Question<Experience> = {
  id: 'experience',
  label: 'How experienced are you?',
  options: [
    { value: 'beginner',      label: 'Beginner',      sub: 'Still learning the basics' },
    { value: 'intermediate',  label: 'Intermediate',  sub: 'Comfortable with markets and common strategies' },
    { value: 'experienced',   label: 'Experienced',   sub: 'I have been investing or trading for years' },
  ],
}

function OptionButton<T extends string>({
  option,
  selected,
  onSelect,
}: {
  option: { value: T; label: string; sub: string }
  selected: boolean
  onSelect: (v: T) => void
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(option.value)}
      className={cn(
        'w-full text-left px-4 py-3.5 rounded-xl border transition-all duration-150',
        'focus:outline-none focus:ring-2 focus:ring-purple-500/40',
        selected
          ? 'border-purple-500 bg-purple-500/10 text-white'
          : 'border-white/10 bg-white/[0.03] text-zinc-300 hover:border-white/20 hover:bg-white/[0.06]',
      )}
    >
      <div className="flex items-center gap-3">
        <span
          className={cn(
            'w-4 h-4 rounded-full border-2 flex-shrink-0 transition-colors',
            selected ? 'border-purple-400 bg-purple-400' : 'border-zinc-600',
          )}
        />
        <div>
          <div className="font-medium text-sm">{option.label}</div>
          <div className="text-xs text-zinc-500 mt-0.5">{option.sub}</div>
        </div>
      </div>
    </button>
  )
}

export function TraderProfileForm({ ticker, onSubmit, onBack }: TraderProfileFormProps) {
  const [risk, setRisk] = React.useState<RiskTolerance | null>(null)
  const [horizon, setHorizon] = React.useState<TimeHorizon | null>(null)
  const [goal, setGoal] = React.useState<TraderGoal | null>(null)
  const [experience, setExperience] = React.useState<Experience | null>(null)

  const allAnswered = risk && horizon && goal && experience

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!allAnswered) return
    onSubmit({ risk_tolerance: risk, time_horizon: horizon, goal, experience })
  }

  return (
    <div className="min-h-screen bg-[#080808] flex flex-col items-center justify-center px-4 py-16">
      {/* Subtle radial glow */}
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(ellipse_60%_40%_at_50%_0%,rgba(120,60,220,0.12),transparent)]" />

      <div className="relative z-10 w-full max-w-xl">
        {/* Header */}
        <div className="mb-8 text-center">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/5 border border-white/10 text-xs text-zinc-500 mb-4">
            <span className="font-mono text-purple-400">{ticker}</span>
            <span>·</span>
            <span>Trader profile</span>
          </div>
          <h2 className="text-2xl font-bold text-white tracking-tight">
            Tell us about yourself
          </h2>
          <p className="mt-2 text-sm text-zinc-500">
            Your answers shape how the agents weight their signals and frame the final verdict.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Risk tolerance */}
          <div>
            <p className="text-sm font-medium text-zinc-300 mb-2.5">{RISK_QUESTION.label}</p>
            <div className="space-y-2">
              {RISK_QUESTION.options.map(opt => (
                <OptionButton key={opt.value} option={opt} selected={risk === opt.value} onSelect={setRisk} />
              ))}
            </div>
          </div>

          {/* Time horizon */}
          <div>
            <p className="text-sm font-medium text-zinc-300 mb-2.5">{HORIZON_QUESTION.label}</p>
            <div className="space-y-2">
              {HORIZON_QUESTION.options.map(opt => (
                <OptionButton key={opt.value} option={opt} selected={horizon === opt.value} onSelect={setHorizon} />
              ))}
            </div>
          </div>

          {/* Goal */}
          <div>
            <p className="text-sm font-medium text-zinc-300 mb-2.5">{GOAL_QUESTION.label}</p>
            <div className="space-y-2">
              {GOAL_QUESTION.options.map(opt => (
                <OptionButton key={opt.value} option={opt} selected={goal === opt.value} onSelect={setGoal} />
              ))}
            </div>
          </div>

          {/* Experience */}
          <div>
            <p className="text-sm font-medium text-zinc-300 mb-2.5">{EXPERIENCE_QUESTION.label}</p>
            <div className="space-y-2">
              {EXPERIENCE_QUESTION.options.map(opt => (
                <OptionButton key={opt.value} option={opt} selected={experience === opt.value} onSelect={setExperience} />
              ))}
            </div>
          </div>

          {/* Actions */}
          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onBack}
              className="px-5 py-3 rounded-xl text-sm font-medium text-zinc-400 border border-white/10 hover:border-white/20 hover:text-zinc-300 transition-all"
            >
              Back
            </button>
            <button
              type="submit"
              disabled={!allAnswered}
              className={cn(
                'flex-1 py-3 rounded-xl text-sm font-semibold transition-all duration-200',
                allAnswered
                  ? 'bg-gradient-to-r from-purple-600 to-purple-500 text-white hover:from-purple-500 hover:to-purple-400'
                  : 'bg-white/5 text-zinc-600 cursor-not-allowed border border-white/5',
              )}
            >
              {allAnswered ? 'Run Analysis' : 'Answer all questions to continue'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
