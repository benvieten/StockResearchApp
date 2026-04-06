import { useEffect, useRef, useState } from 'react'
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  ColorType,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type HistogramData,
  type Time,
} from 'lightweight-charts'

interface OhlcvData {
  dates: string[]
  open: (number | null)[]
  high: (number | null)[]
  low: (number | null)[]
  close: (number | null)[]
  volume: (number | null)[]
}

type Range = '1M' | '3M' | '6M' | '1Y' | '2Y'

const RANGES: Range[] = ['1M', '3M', '6M', '1Y', '2Y']

function subtractMonths(date: Date, months: number): Date {
  const d = new Date(date)
  d.setMonth(d.getMonth() - months)
  return d
}

function rangeStart(range: Range, latest: Date): Date {
  const m = { '1M': 1, '3M': 3, '6M': 6, '1Y': 12, '2Y': 24 }[range]
  return subtractMonths(latest, m)
}

interface Props {
  ticker: string
  priceAtAnalysis?: number | null
}

export function StockChart({ ticker, priceAtAnalysis }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeRef = useRef<ISeriesApi<'Histogram'> | null>(null)

  const [data, setData] = useState<OhlcvData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [range, setRange] = useState<Range>('6M')

  // Fetch OHLCV once
  useEffect(() => {
    setLoading(true)
    setError(false)
    fetch(`/api/price-history/${ticker}`)
      .then(r => r.json())
      .then(d => setData(d))
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }, [ticker])

  // Create chart once container is ready
  useEffect(() => {
    if (!containerRef.current || chartRef.current) return

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#71717a',
        fontFamily: 'inherit',
      },
      grid: {
        vertLines: { color: 'rgba(255,255,255,0.04)' },
        horzLines: { color: 'rgba(255,255,255,0.04)' },
      },
      crosshair: {
        vertLine: { color: 'rgba(139,92,246,0.5)', labelBackgroundColor: '#7c3aed' },
        horzLine: { color: 'rgba(139,92,246,0.5)', labelBackgroundColor: '#7c3aed' },
      },
      rightPriceScale: { borderColor: 'rgba(255,255,255,0.06)' },
      timeScale: { borderColor: 'rgba(255,255,255,0.06)', timeVisible: true },
      height: 280,
    })

    const candles = chart.addSeries(CandlestickSeries, {
      upColor: '#34d399',
      downColor: '#f87171',
      borderUpColor: '#34d399',
      borderDownColor: '#f87171',
      wickUpColor: '#34d399',
      wickDownColor: '#f87171',
    })

    const volume = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    })
    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    })

    chartRef.current = chart
    candleRef.current = candles
    volumeRef.current = volume

    const ro = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth })
      }
    })
    ro.observe(containerRef.current)

    return () => {
      ro.disconnect()
      chart.remove()
      chartRef.current = null
      candleRef.current = null
      volumeRef.current = null
    }
  }, [])

  // Update data when ohlcv or range changes
  useEffect(() => {
    if (!data || !candleRef.current || !volumeRef.current) return

    const allCandles: CandlestickData[] = []
    const allVolumes: HistogramData[] = []

    for (let i = 0; i < data.dates.length; i++) {
      const o = data.open[i], h = data.high[i], l = data.low[i], c = data.close[i], v = data.volume[i]
      if (o == null || h == null || l == null || c == null) continue
      const time = data.dates[i] as Time
      allCandles.push({ time, open: o, high: h, low: l, close: c })
      allVolumes.push({
        time,
        value: v ?? 0,
        color: c >= o ? 'rgba(52,211,153,0.25)' : 'rgba(248,113,113,0.25)',
      })
    }

    if (allCandles.length === 0) return

    const latest = new Date(allCandles[allCandles.length - 1].time as string)
    const start = rangeStart(range, latest).toISOString().split('T')[0]

    const filtered = allCandles.filter(d => (d.time as string) >= start)
    const filteredVol = allVolumes.filter(d => (d.time as string) >= start)

    candleRef.current.setData(filtered)
    volumeRef.current.setData(filteredVol)
    chartRef.current?.timeScale().fitContent()
  }, [data, range])

  // Draw price-at-analysis line
  useEffect(() => {
    if (!candleRef.current || !priceAtAnalysis) return
    candleRef.current.applyOptions({
      lastValueVisible: true,
    })
    chartRef.current?.applyOptions({})
    // Use a price line to mark entry price
    candleRef.current.createPriceLine({
      price: priceAtAnalysis,
      color: 'rgba(139,92,246,0.7)',
      lineWidth: 1,
      lineStyle: 2, // dashed
      axisLabelVisible: true,
      title: 'analysis price',
    })
  }, [data, priceAtAnalysis])

  if (error) return null

  return (
    <div className="mt-4">
      {/* Range selector */}
      <div className="flex items-center gap-1 mb-2">
        {RANGES.map(r => (
          <button
            key={r}
            onClick={() => setRange(r)}
            className={`px-2.5 py-0.5 rounded text-xs font-medium transition-colors ${
              range === r
                ? 'bg-violet-600/30 text-violet-300'
                : 'text-zinc-600 hover:text-zinc-400'
            }`}
          >
            {r}
          </button>
        ))}
      </div>

      {/* Chart */}
      <div className="relative rounded-lg overflow-hidden border border-white/5">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-[#080808]/80 z-10">
            <div className="w-4 h-4 border-2 border-zinc-700 border-t-violet-500 rounded-full animate-spin" />
          </div>
        )}
        <div ref={containerRef} className="w-full" />
      </div>
    </div>
  )
}
