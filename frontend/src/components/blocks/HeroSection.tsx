import * as React from 'react'
import { cn } from '@/lib/utils'
import { Search, TrendingUp, Brain, BarChart2, Activity, Globe, MessageSquare } from 'lucide-react'

interface HeroSectionProps {
  onAnalyze: (ticker: string) => void
}

const RetroGrid = ({
  angle = 65,
  cellSize = 60,
  opacity = 0.35,
  lineColor = '#1a2a1a',
}: {
  angle?: number
  cellSize?: number
  opacity?: number
  lineColor?: string
}) => {
  return (
    <div
      className="pointer-events-none absolute inset-0 overflow-hidden [perspective:200px]"
      style={{ opacity }}
    >
      <div
        className="absolute inset-0"
        style={{ transform: `rotateX(${angle}deg)` }}
      >
        <div
          className="animate-grid [height:300vh] [inset:0%_0px] [margin-left:-200%] [transform-origin:100%_0_0] [width:600vw]"
          style={{
            backgroundImage: `linear-gradient(to right, ${lineColor} 1px, transparent 0), linear-gradient(to bottom, ${lineColor} 1px, transparent 0)`,
            backgroundRepeat: 'repeat',
            backgroundSize: `${cellSize}px ${cellSize}px`,
          }}
        />
      </div>
      <div className="absolute inset-0 bg-gradient-to-t from-[#080808] to-transparent to-90%" />
    </div>
  )
}

const AGENTS = [
  { icon: BarChart2, label: 'Fundamental' },
  { icon: Activity, label: 'Technical' },
  { icon: TrendingUp, label: 'Quant' },
  { icon: Globe, label: 'Sector' },
  { icon: MessageSquare, label: 'Sentiment' },
  { icon: Brain, label: 'Synthesis' },
]

export function HeroSection({ onAnalyze }: HeroSectionProps) {
  const [ticker, setTicker] = React.useState('')
  const [error, setError] = React.useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const t = ticker.trim().toUpperCase()
    if (!t) {
      setError('Enter a ticker symbol')
      return
    }
    if (!/^[A-Z]{1,5}$/.test(t)) {
      setError('Ticker must be 1–5 letters (e.g. AAPL)')
      return
    }
    setError('')
    onAnalyze(t)
  }

  return (
    <div className="relative min-h-screen flex flex-col overflow-hidden bg-[#080808]">
      {/* Radial purple glow */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_60%_50%_at_50%_-10%,rgba(120,60,220,0.18),transparent)]" />

      <RetroGrid />

      {/* Nav */}
      <nav className="relative z-10 flex items-center justify-between px-8 py-6 max-w-7xl mx-auto w-full">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-purple-500 to-purple-700 flex items-center justify-center">
            <Brain className="w-4 h-4 text-white" />
          </div>
          <span className="font-semibold text-white tracking-tight">StockResearch AI</span>
        </div>
        <div className="flex items-center gap-1.5 text-xs text-zinc-500">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
          6 agents ready
        </div>
      </nav>

      {/* Hero content */}
      <div className="relative z-10 flex-1 flex flex-col items-center justify-center px-4 py-20 text-center">
        {/* Badge */}
        <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white/5 border border-white/10 text-xs text-zinc-400 mb-8">
          <span className="w-1.5 h-1.5 rounded-full bg-purple-400" />
          Powered by 6 parallel AI agents · Free data sources only
        </div>

        {/* Headline */}
        <h1 className="text-5xl md:text-7xl font-bold tracking-tighter leading-[1.05] mb-6 max-w-3xl">
          <span className="text-white">Research any stock</span>
          <br />
          <span className="bg-gradient-to-r from-purple-400 via-purple-300 to-pink-400 bg-clip-text text-transparent">
            in seconds.
          </span>
        </h1>

        <p className="text-zinc-400 text-lg md:text-xl max-w-xl mb-12 leading-relaxed">
          Six specialized AI agents analyze fundamentals, technicals, quant factors, sector
          dynamics, and market sentiment — then synthesize a single verdict.
        </p>

        {/* Ticker input */}
        <form onSubmit={handleSubmit} className="w-full max-w-md mb-4">
          <div className="relative group">
            {/* Animated border */}
            <span className="absolute inset-[-1px] rounded-2xl overflow-hidden pointer-events-none">
              <span
                className="absolute inset-[-200%] animate-[spin_3s_linear_infinite] bg-[conic-gradient(from_90deg_at_50%_50%,#7c3aed_0%,#1e1e2e_40%,#7c3aed_100%)]"
                style={{ opacity: 0.6 }}
              />
            </span>
            <div className="relative flex items-center bg-[#0f0f0f] rounded-2xl border border-white/10">
              <Search className="absolute left-4 w-5 h-5 text-zinc-500" />
              <input
                type="text"
                value={ticker}
                onChange={e => {
                  setTicker(e.target.value.toUpperCase())
                  setError('')
                }}
                placeholder="Enter ticker symbol  (e.g. AAPL)"
                maxLength={5}
                className={cn(
                  'w-full bg-transparent pl-12 pr-4 py-4 text-white placeholder-zinc-600',
                  'text-lg font-mono tracking-widest focus:outline-none rounded-2xl',
                )}
                autoComplete="off"
                spellCheck={false}
              />
              <button
                type="submit"
                className={cn(
                  'mr-2 px-6 py-2.5 rounded-xl font-semibold text-sm whitespace-nowrap',
                  'bg-gradient-to-r from-purple-600 to-purple-500 text-white',
                  'hover:from-purple-500 hover:to-purple-400 transition-all duration-200',
                  'focus:outline-none focus:ring-2 focus:ring-purple-500/50',
                )}
              >
                Analyze
              </button>
            </div>
          </div>
          {error && (
            <p className="mt-2 text-sm text-red-400 text-left pl-1">{error}</p>
          )}
        </form>

        <p className="text-xs text-zinc-600 mb-16">
          Try: AAPL · MSFT · NVDA · TSLA · ONDS
        </p>

        {/* Agent grid */}
        <div className="grid grid-cols-3 md:grid-cols-6 gap-3 max-w-2xl w-full">
          {AGENTS.map(({ icon: Icon, label }) => (
            <div
              key={label}
              className="flex flex-col items-center gap-2 p-3 rounded-xl bg-white/[0.03] border border-white/5 hover:border-white/10 transition-colors"
            >
              <Icon className="w-5 h-5 text-purple-400/70" />
              <span className="text-[11px] text-zinc-500 font-medium">{label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Bottom fade */}
      <div className="absolute bottom-0 inset-x-0 h-32 bg-gradient-to-t from-[#080808] to-transparent pointer-events-none" />
    </div>
  )
}
