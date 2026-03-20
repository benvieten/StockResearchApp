import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'
import {
  BarChart2, Activity, TrendingUp, Globe, MessageSquare, Brain,
  TrendingDown, Minus, Info, AlertTriangle,
} from 'lucide-react'

// ── Section wrapper ────────────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="space-y-3">
      <h3 className="text-xs font-semibold uppercase tracking-widest text-zinc-500">{title}</h3>
      {children}
    </div>
  )
}

function Card({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn('rounded-xl border border-white/10 bg-white/[0.03] p-5', className)}>
      {children}
    </div>
  )
}

function InfoRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex gap-3 text-sm">
      <span className="w-2 h-2 rounded-full bg-purple-500/60 flex-shrink-0 mt-1.5" />
      <div>
        <span className="font-medium text-white">{label}: </span>
        <span className="text-zinc-400 leading-relaxed">{children}</span>
      </div>
    </div>
  )
}

// ── Agents section ─────────────────────────────────────────────────────────────

const AGENTS = [
  {
    Icon: BarChart2,
    name: 'Fundamental Analysis',
    color: 'text-purple-400',
    what: 'Reads the company\'s financial statements — revenue, earnings, debt, margins.',
    why: 'Tells you whether the business itself is healthy and whether the stock price is cheap or expensive relative to what the company actually earns.',
    score: 'Higher = stronger business quality and more attractive valuation.',
  },
  {
    Icon: Activity,
    name: 'Technical Analysis',
    color: 'text-blue-400',
    what: 'Analyzes price charts, moving averages, momentum indicators (RSI, MACD), and volume patterns.',
    why: 'Tells you what the stock\'s price is doing right now — is it trending up, down, or sideways? Are buyers or sellers in control?',
    score: 'Not a 0–100 score. Instead shows Bullish / Bearish / Neutral direction with a confidence percentage.',
  },
  {
    Icon: TrendingUp,
    name: 'Quantitative Factors',
    color: 'text-cyan-400',
    what: 'Scores the stock on four academic "factors": momentum (recent price trend), quality (profit consistency), value (cheap vs. peers), and low-volatility (stability).',
    why: 'Decades of research show these factors outperform over time. They are purely mathematical — no opinion involved.',
    score: 'Higher = the stock scores well on historically rewarding characteristics.',
  },
  {
    Icon: Globe,
    name: 'Sector & Peers',
    color: 'text-emerald-400',
    what: 'Compares the stock against its industry ETF and closest competitors.',
    why: 'A stock can look great in isolation but still lag its entire sector. Context matters — you want stocks outperforming their peers, not just the broad market.',
    score: 'Higher = stronger relative performance versus competitors.',
  },
  {
    Icon: MessageSquare,
    name: 'Market Sentiment',
    color: 'text-amber-400',
    what: 'Scans Reddit and financial news for how retail investors and media are talking about the stock.',
    why: 'Extreme optimism online is often a contrarian warning sign — when everyone is already bullish, there may be no one left to buy. This agent discounts hype automatically.',
    score: 'Range: roughly −1.0 (very bearish chatter) to +1.0 (very bullish). High volume + high score = caution flag, not a green light.',
  },
  {
    Icon: Brain,
    name: 'Synthesis',
    color: 'text-pink-400',
    what: 'Combines all five agent scores into a single weighted composite, then generates the final verdict and narrative.',
    why: 'No single lens is enough. A great business can have terrible momentum. A hyped stock can have awful fundamentals. Synthesis weighs everything together, adjusting for the current market regime and your trader profile.',
    score: 'The composite score (0–100) drives the final verdict.',
  },
]

function AgentsSection() {
  return (
    <Section title="The Six Agents — What They Do">
      <div className="grid gap-3 md:grid-cols-2">
        {AGENTS.map(({ Icon, name, color, what, why, score }) => (
          <Card key={name}>
            <div className="flex items-center gap-2 mb-3">
              <div className="w-8 h-8 rounded-lg bg-white/5 flex items-center justify-center flex-shrink-0">
                <Icon className={cn('w-4 h-4', color)} />
              </div>
              <span className="font-semibold text-sm text-white">{name}</span>
            </div>
            <div className="space-y-2 text-xs text-zinc-400 leading-relaxed">
              <p><span className="text-zinc-300 font-medium">What it reads: </span>{what}</p>
              <p><span className="text-zinc-300 font-medium">Why it matters: </span>{why}</p>
              <p className="text-purple-300/80 italic">{score}</p>
            </div>
          </Card>
        ))}
      </div>
    </Section>
  )
}

// ── Scores section ─────────────────────────────────────────────────────────────

function ScoreBar({ pct, color }: { pct: number; color: string }) {
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 h-2 rounded-full bg-white/5 overflow-hidden">
        <div className={cn('h-full rounded-full', color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="font-mono text-xs text-zinc-400 w-8 text-right">{pct}</span>
    </div>
  )
}

function ScoresSection() {
  return (
    <Section title="Signal Scores — What the Numbers Mean">
      <Card>
        <p className="text-sm text-zinc-400 leading-relaxed mb-5">
          Each agent (except Technical) produces a score from <span className="text-white font-medium">0 to 100</span>. Think of it as a confidence reading — higher means more positive evidence for that dimension.
        </p>
        <div className="space-y-4">
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs font-medium text-emerald-400">65–100 · Strong signal</span>
            </div>
            <ScoreBar pct={80} color="bg-emerald-400" />
            <p className="text-xs text-zinc-500 mt-1.5 leading-relaxed">Clear evidence in favor. The agent saw consistent, reliable data pointing the same direction.</p>
          </div>
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs font-medium text-amber-400">45–64 · Mixed signal</span>
            </div>
            <ScoreBar pct={54} color="bg-amber-400" />
            <p className="text-xs text-zinc-500 mt-1.5 leading-relaxed">Some positives, some negatives. The agent couldn't form a strong view either way — proceed with caution.</p>
          </div>
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs font-medium text-red-400">0–44 · Weak or negative signal</span>
            </div>
            <ScoreBar pct={28} color="bg-red-400" />
            <p className="text-xs text-zinc-500 mt-1.5 leading-relaxed">Evidence points against the stock on this dimension. Multiple weak scores across agents are a meaningful warning.</p>
          </div>
        </div>
        <div className="mt-5 p-3 rounded-lg bg-amber-400/5 border border-amber-400/15">
          <p className="text-xs text-amber-300/80 leading-relaxed">
            <AlertTriangle className="w-3 h-3 inline mr-1 mb-0.5" />
            <strong>No single score tells the full story.</strong> A stock can score 80 on fundamentals and 20 on technical — that might mean it's a great long-term hold but a poor short-term trade. Context always matters.
          </p>
        </div>
      </Card>
    </Section>
  )
}

// ── Verdicts section ───────────────────────────────────────────────────────────

const VERDICTS = [
  { label: 'Strong Buy', range: '75–100', color: 'text-emerald-400', bg: 'bg-emerald-400/10 border-emerald-400/20', desc: 'Overwhelming evidence across multiple agents points upward. The business is solid, price is reasonable, and momentum is on your side. High confidence — but still not a guarantee.' },
  { label: 'Buy', range: '60–74', color: 'text-emerald-300', bg: 'bg-emerald-300/10 border-emerald-300/20', desc: 'More positives than negatives. A reasonable entry point for most trader profiles, with manageable risk.' },
  { label: 'Hold', range: '40–59', color: 'text-amber-400', bg: 'bg-amber-400/10 border-amber-400/20', desc: 'Mixed signals — the agents don\'t agree. If you own it, no urgent reason to sell. If you don\'t own it, no compelling reason to buy yet. Wait for clarity.' },
  { label: 'Sell', range: '25–39', color: 'text-red-300', bg: 'bg-red-300/10 border-red-300/20', desc: 'More negatives than positives. The evidence is tilting against the stock — consider reducing exposure.' },
  { label: 'Strong Sell', range: '0–24', color: 'text-red-400', bg: 'bg-red-400/10 border-red-400/20', desc: 'Consistent negative signals across agents. Significant downside risk. Exiting or avoiding this stock is justified by the evidence.' },
]

function VerdictsSection() {
  return (
    <Section title="Verdicts — What the Final Call Means">
      <div className="space-y-2">
        {VERDICTS.map(({ label, range, color, bg, desc }) => (
          <div key={label} className={cn('rounded-xl border p-4', bg)}>
            <div className="flex items-center justify-between mb-1.5">
              <span className={cn('font-bold text-sm', color)}>{label}</span>
              <span className="text-xs font-mono text-zinc-500">composite {range}</span>
            </div>
            <p className="text-xs text-zinc-400 leading-relaxed">{desc}</p>
          </div>
        ))}
      </div>
      <Card>
        <p className="text-xs text-zinc-500 font-medium uppercase tracking-wider mb-2">Conviction Level</p>
        <div className="space-y-2.5">
          <InfoRow label="High conviction">All agents broadly agree, data quality is good, and nothing unusual is happening in market structure.</InfoRow>
          <InfoRow label="Medium conviction">Some disagreement between agents, or the system detected that the trade is already "crowded" — many signals pointing the same way often means the market already knows.</InfoRow>
          <InfoRow label="Low conviction">Significant gaps in data, agents diverge sharply, or market conditions are too uncertain to commit.</InfoRow>
        </div>
        <div className="mt-4 p-3 rounded-lg bg-purple-500/5 border border-purple-500/15">
          <p className="text-xs text-purple-300/80 leading-relaxed">
            <Info className="w-3 h-3 inline mr-1 mb-0.5" />
            <strong>Full consensus warning:</strong> When all agents point strongly in the same direction, conviction is automatically capped at "medium." Unanimous agreement usually means the information is already priced in — professional traders have already acted on it.
          </p>
        </div>
      </Card>
    </Section>
  )
}

// ── Regime section ─────────────────────────────────────────────────────────────

function RegimeSection() {
  return (
    <Section title="Market Regime — The Backdrop">
      <Card>
        <p className="text-sm text-zinc-400 leading-relaxed mb-5">
          The market regime tells you what the <span className="text-white font-medium">overall stock market</span> is doing — not this specific stock. It changes what the analysis means.
        </p>
        <div className="space-y-4">
          <div className="flex gap-3">
            <TrendingUp className="w-4 h-4 text-emerald-400 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-emerald-400 mb-1">Bull Market</p>
              <p className="text-xs text-zinc-400 leading-relaxed">The broad market is trending up. Momentum and technical signals carry more weight — the tide lifts most boats. A "Buy" in a bull market is more meaningful than the same score in a downturn.</p>
            </div>
          </div>
          <div className="flex gap-3">
            <TrendingDown className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-red-400 mb-1">Bear Market</p>
              <p className="text-xs text-zinc-400 leading-relaxed">The broad market is declining. Fundamental quality matters more — strong businesses survive downturns. Technical signals become less reliable because even great stocks get sold during panics. Sentiment signals are treated with extra skepticism.</p>
            </div>
          </div>
          <div className="flex gap-3">
            <Minus className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-amber-400 mb-1">Transitional Market</p>
              <p className="text-xs text-zinc-400 leading-relaxed">The market is between regimes — unclear direction. No single factor dominates. This is the hardest environment to trade in. The system balances all factors equally and reflects this uncertainty in lower conviction scores.</p>
            </div>
          </div>
        </div>
        <div className="mt-4 p-3 rounded-lg bg-white/[0.02] border border-white/5">
          <p className="text-xs text-zinc-500 leading-relaxed">
            <strong className="text-zinc-400">VIX</strong> (Volatility Index) measures how much fear is in the market. VIX below 20 = calm. 20–30 = elevated anxiety. Above 30 = significant fear. High VIX often coincides with bear or transitional regimes.
          </p>
        </div>
      </Card>
    </Section>
  )
}

// ── Statistical metrics section ────────────────────────────────────────────────

function StatMetricsSection() {
  return (
    <Section title="Statistical Metrics — The Raw Math">
      <Card>
        <p className="text-sm text-zinc-400 leading-relaxed mb-5">
          These four metrics in the Quantitative agent are purely mathematical — no AI opinion involved. They detect statistically unusual conditions.
        </p>
        <div className="space-y-5">
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-medium text-white">Return Z-Score</span>
              <span className="text-xs font-mono text-zinc-500">typical range: −3 to +3</span>
            </div>
            <p className="text-xs text-zinc-400 leading-relaxed mb-2">How unusual is today's price move compared to the past 90 trading days? Zero = completely normal. Beyond ±2 = statistically rare.</p>
            <div className="grid grid-cols-3 gap-2 text-xs">
              <div className="rounded-lg bg-emerald-400/5 border border-emerald-400/15 p-2 text-center">
                <p className="font-mono font-medium text-emerald-400">&lt; −2</p>
                <p className="text-zinc-500 mt-0.5">Oversold spike — potential reversal</p>
              </div>
              <div className="rounded-lg bg-white/[0.03] border border-white/5 p-2 text-center">
                <p className="font-mono font-medium text-zinc-300">−2 to +2</p>
                <p className="text-zinc-500 mt-0.5">Normal</p>
              </div>
              <div className="rounded-lg bg-red-400/5 border border-red-400/15 p-2 text-center">
                <p className="font-mono font-medium text-red-400">&gt; +2</p>
                <p className="text-zinc-500 mt-0.5">Overbought spike — watch for pullback</p>
              </div>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-medium text-white">Volume Ratio</span>
              <span className="text-xs font-mono text-zinc-500">today's vol ÷ 20-day avg</span>
            </div>
            <p className="text-xs text-zinc-400 leading-relaxed mb-2">Is today's trading volume unusually high or low? 1.0 = average. Big price moves on high volume are more meaningful than moves on thin volume.</p>
            <div className="grid grid-cols-3 gap-2 text-xs">
              <div className="rounded-lg bg-zinc-800/50 border border-white/5 p-2 text-center">
                <p className="font-mono font-medium text-zinc-500">&lt; 0.5</p>
                <p className="text-zinc-500 mt-0.5">Low conviction move</p>
              </div>
              <div className="rounded-lg bg-white/[0.03] border border-white/5 p-2 text-center">
                <p className="font-mono font-medium text-zinc-300">0.5–2.0</p>
                <p className="text-zinc-500 mt-0.5">Normal</p>
              </div>
              <div className="rounded-lg bg-purple-400/5 border border-purple-400/15 p-2 text-center">
                <p className="font-mono font-medium text-purple-400">&gt; 2.0</p>
                <p className="text-zinc-500 mt-0.5">High-volume — meaningful move</p>
              </div>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-medium text-white">Bollinger Band Percentile</span>
              <span className="text-xs font-mono text-zinc-500">0 = lower band · 1 = upper band</span>
            </div>
            <p className="text-xs text-zinc-400 leading-relaxed mb-2">Where is the price sitting within its recent volatility range? 0 = at the very bottom of its range (lower Bollinger Band). 1 = at the very top.</p>
            <div className="grid grid-cols-3 gap-2 text-xs">
              <div className="rounded-lg bg-emerald-400/5 border border-emerald-400/15 p-2 text-center">
                <p className="font-mono font-medium text-emerald-400">&lt; 0.2</p>
                <p className="text-zinc-500 mt-0.5">Near low — possible oversold</p>
              </div>
              <div className="rounded-lg bg-white/[0.03] border border-white/5 p-2 text-center">
                <p className="font-mono font-medium text-zinc-300">0.2–0.8</p>
                <p className="text-zinc-500 mt-0.5">Mid-range</p>
              </div>
              <div className="rounded-lg bg-red-400/5 border border-red-400/15 p-2 text-center">
                <p className="font-mono font-medium text-red-400">&gt; 0.8</p>
                <p className="text-zinc-500 mt-0.5">Near high — possible overbought</p>
              </div>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-medium text-white">RSI Percentile</span>
              <span className="text-xs font-mono text-zinc-500">vs. past year</span>
            </div>
            <p className="text-xs text-zinc-400 leading-relaxed mb-2">Where does today's RSI (momentum indicator) rank compared to all RSI readings over the past year? 0 = lowest momentum of the year. 1 = highest momentum.</p>
            <div className="grid grid-cols-3 gap-2 text-xs">
              <div className="rounded-lg bg-emerald-400/5 border border-emerald-400/15 p-2 text-center">
                <p className="font-mono font-medium text-emerald-400">&lt; 0.2</p>
                <p className="text-zinc-500 mt-0.5">Weakest momentum of the year</p>
              </div>
              <div className="rounded-lg bg-white/[0.03] border border-white/5 p-2 text-center">
                <p className="font-mono font-medium text-zinc-300">0.2–0.8</p>
                <p className="text-zinc-500 mt-0.5">Normal range</p>
              </div>
              <div className="rounded-lg bg-red-400/5 border border-red-400/15 p-2 text-center">
                <p className="font-mono font-medium text-red-400">&gt; 0.8</p>
                <p className="text-zinc-500 mt-0.5">Strongest momentum of the year</p>
              </div>
            </div>
          </div>
        </div>
      </Card>
    </Section>
  )
}

// ── How synthesis works ────────────────────────────────────────────────────────

function SynthesisSection() {
  return (
    <Section title="How It All Comes Together">
      <Card>
        <div className="space-y-4 text-sm text-zinc-400 leading-relaxed">
          <div className="flex gap-3">
            <span className="w-6 h-6 rounded-full bg-purple-500/20 text-purple-300 text-xs font-bold flex items-center justify-center flex-shrink-0">1</span>
            <p><span className="text-white font-medium">Five agents run in parallel.</span> Fundamental, Technical, Quant, Sector, and Sentiment each analyze the stock independently using real financial data — no hallucinated numbers.</p>
          </div>
          <div className="flex gap-3">
            <span className="w-6 h-6 rounded-full bg-purple-500/20 text-purple-300 text-xs font-bold flex items-center justify-center flex-shrink-0">2</span>
            <p><span className="text-white font-medium">Weights adjust for regime.</span> In a bull market, technical and sector signals get more weight. In a bear market, fundamental quality dominates. In a transitional market, everything is balanced equally.</p>
          </div>
          <div className="flex gap-3">
            <span className="w-6 h-6 rounded-full bg-purple-500/20 text-purple-300 text-xs font-bold flex items-center justify-center flex-shrink-0">3</span>
            <p><span className="text-white font-medium">Your trader profile shifts the weights further.</span> A conservative long-term income investor cares more about fundamentals and sector stability. An aggressive short-term trader cares more about technical momentum and sentiment.</p>
          </div>
          <div className="flex gap-3">
            <span className="w-6 h-6 rounded-full bg-purple-500/20 text-purple-300 text-xs font-bold flex items-center justify-center flex-shrink-0">4</span>
            <p><span className="text-white font-medium">The composite score maps to a verdict.</span> The weighted average of all five scores becomes the composite, which directly determines Strong Buy / Buy / Hold / Sell / Strong Sell.</p>
          </div>
          <div className="flex gap-3">
            <span className="w-6 h-6 rounded-full bg-purple-500/20 text-purple-300 text-xs font-bold flex items-center justify-center flex-shrink-0">5</span>
            <p><span className="text-white font-medium">The AI writes the narrative.</span> Given all the data, scores, regime, and your profile, the synthesis AI generates a plain-English explanation of the bull case, bear case, and what conflicts to watch for.</p>
          </div>
        </div>

        <div className="mt-5 p-4 rounded-lg bg-white/[0.02] border border-white/5">
          <p className="text-xs font-medium text-zinc-400 mb-2">Important limitations to understand:</p>
          <div className="space-y-1.5">
            {[
              'This tool provides analysis — not advice. It does not know your full financial situation.',
              'Past patterns do not guarantee future results. All scores reflect historical data.',
              'Earnings surprises, news events, and macro shocks can invalidate any analysis instantly.',
              'Never use this as your only source of information before making financial decisions.',
            ].map((txt, i) => (
              <div key={i} className="flex gap-2 text-xs text-zinc-500">
                <span className="text-zinc-600 flex-shrink-0">—</span>
                <p>{txt}</p>
              </div>
            ))}
          </div>
        </div>
      </Card>
    </Section>
  )
}

// ── Main export ────────────────────────────────────────────────────────────────

export function ExplainTab() {
  return (
    <div className="space-y-10">
      <div>
        <p className="text-sm text-zinc-400 leading-relaxed">
          Not sure what all these numbers and terms mean? This guide explains every part of the analysis in plain English — no finance background required.
        </p>
      </div>
      <AgentsSection />
      <ScoresSection />
      <VerdictsSection />
      <RegimeSection />
      <StatMetricsSection />
      <SynthesisSection />
    </div>
  )
}
