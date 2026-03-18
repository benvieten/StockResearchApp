export type DataQuality = 'full' | 'partial'
export type Verdict = 'strong_buy' | 'buy' | 'hold' | 'sell' | 'strong_sell'
export type Conviction = 'high' | 'medium' | 'low'
export type Direction = 'bullish' | 'bearish' | 'neutral'
export type BotRisk = 'low' | 'medium' | 'high'
export type ValuationVerdict = 'undervalued' | 'fair' | 'overvalued'
export type RelativePerformance = 'outperforming' | 'inline' | 'underperforming'
export type AgentName = 'fundamental' | 'technical' | 'quant' | 'sector' | 'sentiment' | 'synthesis'
export type AgentStatus = 'pending' | 'running' | 'complete' | 'error'

export interface FundamentalSignal {
  reasoning: string
  quality_score: number
  valuation_verdict: ValuationVerdict
  key_flags: string[]
  metrics: Record<string, number | null>
  data_quality: DataQuality
}

export interface TechnicalSignal {
  reasoning: string
  direction: Direction
  confidence: number
  key_levels: Record<string, number>
  indicator_summary: string
  raw_indicators: Record<string, number | null>
  data_quality: DataQuality
}

export interface QuantSignal {
  reasoning: string | null
  composite_score: number
  factor_breakdown: Record<string, number | null>
  data_quality: DataQuality
}

export interface SectorSignal {
  reasoning: string
  sector: string
  relative_performance: RelativePerformance
  sector_etf: string
  peer_comparison: Record<string, number>
  data_quality: DataQuality
}

export interface SentimentSignal {
  reasoning: string
  raw_score: number
  adjusted_score: number
  bot_risk: BotRisk
  source_breakdown: Record<string, number>
  narrative_themes: string[]
  mention_volume: number
  data_quality: DataQuality
}

export interface SynthesisSignal {
  reasoning: string
  composite_score: number
  data_quality: DataQuality
}

export type AgentSignal =
  | FundamentalSignal
  | TechnicalSignal
  | QuantSignal
  | SectorSignal
  | SentimentSignal
  | SynthesisSignal

export interface AgentState {
  status: AgentStatus
  signal?: AgentSignal
  error?: string
}

export interface FinalReport {
  ticker: string
  verdict: Verdict
  conviction: Conviction
  narrative: string
  bull_case: string[]
  bear_case: string[]
  conflicts: string[]
  signal_scores: Record<string, number>
  generated_at: string
}

export type SSEEvent =
  | { type: 'pipeline_start'; ticker: string }
  | { type: 'agent_start'; agent: AgentName }
  | { type: 'agent_complete'; agent: AgentName; signal: AgentSignal }
  | { type: 'pipeline_complete'; report: FinalReport }
  | { type: 'error'; message: string }
