import { useState, useCallback } from 'react'
import { HeroSection } from '@/components/blocks/HeroSection'
import { AgentProgressTracker } from '@/components/AgentProgressTracker'
import { ReportDashboard } from '@/components/ReportDashboard'
import type { AgentName, AgentState, FinalReport, SSEEvent } from '@/types'

type AppView = 'hero' | 'researching' | 'report'

function App() {
  const [view, setView] = useState<AppView>('hero')
  const [ticker, setTicker] = useState('')
  const [agents, setAgents] = useState<Partial<Record<AgentName, AgentState>>>({})
  const [report, setReport] = useState<FinalReport | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleAnalyze = useCallback(async (inputTicker: string) => {
    const t = inputTicker.toUpperCase().trim()
    setTicker(t)
    setAgents({})
    setReport(null)
    setError(null)
    setView('researching')

    try {
      const res = await fetch('/api/research/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker: t }),
      })

      if (!res.ok) {
        const json = await res.json().catch(() => ({})) as { error?: string }
        throw new Error(json.error ?? `HTTP ${res.status}`)
      }

      if (!res.body) {
        throw new Error('No response body')
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const json = line.slice(6).trim()
          if (!json || json === '[DONE]') continue

          let event: SSEEvent
          try {
            event = JSON.parse(json) as SSEEvent
          } catch {
            continue
          }

          switch (event.type) {
            case 'agent_start':
              setAgents(prev => ({
                ...prev,
                [event.agent]: { status: 'running' },
              }))
              break

            case 'agent_complete':
              setAgents(prev => ({
                ...prev,
                [event.agent]: { status: 'complete', signal: event.signal },
              }))
              break

            case 'pipeline_complete':
              setReport(event.report)
              setView('report')
              break

            case 'error':
              setError(event.message)
              break

            default:
              break
          }
        }
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Something went wrong'
      setError(msg)
    }
  }, [])

  const handleReset = useCallback(() => {
    setView('hero')
    setTicker('')
    setAgents({})
    setReport(null)
    setError(null)
  }, [])

  return (
    <div className="min-h-screen bg-[#080808] text-white">
      {view === 'hero' && (
        <HeroSection onAnalyze={handleAnalyze} />
      )}

      {view === 'researching' && (
        <AgentProgressTracker
          ticker={ticker}
          agents={agents}
          error={error}
        />
      )}

      {view === 'report' && report && (
        <ReportDashboard
          ticker={ticker}
          report={report}
          agents={agents}
          onReset={handleReset}
        />
      )}
    </div>
  )
}

export default App
