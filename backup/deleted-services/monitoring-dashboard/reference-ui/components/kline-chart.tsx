"use client"

import { useState, useEffect, useRef } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import { ComposedChart, ResponsiveContainer, XAxis, YAxis, Tooltip, Bar, Line, ReferenceLine, Cell } from "recharts"
import { TrendingUp, TrendingDown, BarChart3, Settings, Maximize2, Volume2, Activity } from "lucide-react"

interface KlineData {
  time: string
  timestamp: number
  open: number
  high: number
  low: number
  close: number
  volume: number
  ma5?: number
  ma10?: number
  ma20?: number
  ma60?: number
  rsi?: number
  macd?: number
  signal?: number
  histogram?: number
}

interface KlineChartProps {
  symbol?: string
  height?: number
}

export function KlineChart({ symbol = "BTC/USDT", height = 500 }: KlineChartProps) {
  const [data, setData] = useState<KlineData[]>([])
  const [timeframe, setTimeframe] = useState("1h")
  const [indicators, setIndicators] = useState({
    ma: true,
    volume: true,
    rsi: false,
    macd: false,
    bollinger: false,
  })
  const [currentPrice, setCurrentPrice] = useState(0)
  const [priceChange, setPriceChange] = useState(0)
  const [priceChangePercent, setPriceChangePercent] = useState(0)
  const chartRef = useRef<HTMLDivElement>(null)

  // 生成模拟K线数据
  useEffect(() => {
    const generateKlineData = () => {
      const now = Date.now()
      const interval =
        timeframe === "1m"
          ? 60000
          : timeframe === "5m"
            ? 300000
            : timeframe === "15m"
              ? 900000
              : timeframe === "1h"
                ? 3600000
                : 86400000
      const periods = 100

      let basePrice = 43000 + Math.random() * 10000
      const newData: KlineData[] = []

      for (let i = periods; i >= 0; i--) {
        const timestamp = now - i * interval
        const time = new Date(timestamp)

        // 生成OHLC数据
        const volatility = 0.02
        const trend = (Math.random() - 0.5) * 0.001

        const open = basePrice
        const change = basePrice * volatility * (Math.random() - 0.5)
        const high = Math.max(open, open + Math.abs(change) + Math.random() * basePrice * 0.01)
        const low = Math.min(open, open - Math.abs(change) - Math.random() * basePrice * 0.01)
        const close = open + change + basePrice * trend
        const volume = Math.random() * 1000 + 100

        basePrice = close

        const kline: KlineData = {
          time:
            timeframe === "1d"
              ? time.toLocaleDateString()
              : time.toLocaleTimeString("en-US", {
                  hour: "2-digit",
                  minute: "2-digit",
                  month: "short",
                  day: "numeric",
                }),
          timestamp,
          open: Number(open.toFixed(2)),
          high: Number(high.toFixed(2)),
          low: Number(low.toFixed(2)),
          close: Number(close.toFixed(2)),
          volume: Number(volume.toFixed(2)),
        }

        newData.push(kline)
      }

      // 计算技术指标
      calculateIndicators(newData)
      setData(newData)

      // 设置当前价格
      const latest = newData[newData.length - 1]
      const previous = newData[newData.length - 2]
      if (latest && previous) {
        setCurrentPrice(latest.close)
        const change = latest.close - previous.close
        setPriceChange(change)
        setPriceChangePercent((change / previous.close) * 100)
      }
    }

    generateKlineData()
    const interval = setInterval(generateKlineData, 5000)
    return () => clearInterval(interval)
  }, [timeframe])

  // 计算技术指标
  const calculateIndicators = (data: KlineData[]) => {
    // 移动平均线
    for (let i = 0; i < data.length; i++) {
      if (i >= 4) {
        data[i].ma5 = data.slice(i - 4, i + 1).reduce((sum, item) => sum + item.close, 0) / 5
      }
      if (i >= 9) {
        data[i].ma10 = data.slice(i - 9, i + 1).reduce((sum, item) => sum + item.close, 0) / 10
      }
      if (i >= 19) {
        data[i].ma20 = data.slice(i - 19, i + 1).reduce((sum, item) => sum + item.close, 0) / 20
      }
      if (i >= 59) {
        data[i].ma60 = data.slice(i - 59, i + 1).reduce((sum, item) => sum + item.close, 0) / 60
      }
    }

    // RSI计算
    for (let i = 14; i < data.length; i++) {
      let gains = 0
      let losses = 0

      for (let j = i - 13; j <= i; j++) {
        const change = data[j].close - data[j - 1]?.close || 0
        if (change > 0) gains += change
        else losses += Math.abs(change)
      }

      const avgGain = gains / 14
      const avgLoss = losses / 14
      const rs = avgGain / avgLoss
      data[i].rsi = 100 - 100 / (1 + rs)
    }
  }

  // 自定义K线柱状图组件
  const CandlestickBar = (props: any) => {
    const { payload, x, y, width, height } = props
    if (!payload) return null

    const { open, high, low, close } = payload
    const isUp = close >= open
    const color = isUp ? "#00D4AA" : "#F5455C"

    const bodyHeight = (Math.abs(close - open) * height) / (payload.high - payload.low)
    const bodyY = y + (Math.max(high - Math.max(open, close), 0) * height) / (payload.high - payload.low)

    const wickX = x + width / 2
    const highY = y
    const lowY = y + height
    const bodyTop = isUp
      ? y + ((high - close) * height) / (payload.high - payload.low)
      : y + ((high - open) * height) / (payload.high - payload.low)
    const bodyBottom = bodyTop + bodyHeight

    return (
      <g>
        {/* 上下影线 */}
        <line x1={wickX} y1={highY} x2={wickX} y2={bodyTop} stroke={color} strokeWidth={1} />
        <line x1={wickX} y1={bodyBottom} x2={wickX} y2={lowY} stroke={color} strokeWidth={1} />
        {/* K线实体 */}
        <rect
          x={x + 1}
          y={bodyTop}
          width={width - 2}
          height={Math.max(bodyHeight, 1)}
          fill={isUp ? color : color}
          stroke={color}
          strokeWidth={isUp ? 1 : 0}
          fillOpacity={isUp ? 0.1 : 1}
        />
      </g>
    )
  }

  // 自定义Tooltip
  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload
      const isUp = data.close >= data.open

      return (
        <div className="htx-card p-3 text-sm">
          <p className="text-blue-200/80 mb-2">{label}</p>
          <div className="space-y-1">
            <div className="flex justify-between space-x-4">
              <span className="text-blue-300/60">Open:</span>
              <span className="text-white font-mono">{data.open?.toFixed(2)}</span>
            </div>
            <div className="flex justify-between space-x-4">
              <span className="text-blue-300/60">High:</span>
              <span className="text-white font-mono">{data.high?.toFixed(2)}</span>
            </div>
            <div className="flex justify-between space-x-4">
              <span className="text-blue-300/60">Low:</span>
              <span className="text-white font-mono">{data.low?.toFixed(2)}</span>
            </div>
            <div className="flex justify-between space-x-4">
              <span className="text-blue-300/60">Close:</span>
              <span className={`font-mono ${isUp ? "price-up" : "price-down"}`}>{data.close?.toFixed(2)}</span>
            </div>
            <div className="flex justify-between space-x-4">
              <span className="text-blue-300/60">Volume:</span>
              <span className="text-white font-mono">{data.volume?.toFixed(2)}</span>
            </div>
            {indicators.ma && data.ma20 && (
              <div className="flex justify-between space-x-4">
                <span className="text-blue-300/60">MA20:</span>
                <span className="text-cyan-400 font-mono">{data.ma20.toFixed(2)}</span>
              </div>
            )}
          </div>
        </div>
      )
    }
    return null
  }

  const timeframes = [
    { value: "1m", label: "1m" },
    { value: "5m", label: "5m" },
    { value: "15m", label: "15m" },
    { value: "1h", label: "1h" },
    { value: "4h", label: "4h" },
    { value: "1d", label: "1D" },
  ]

  return (
    <Card className="htx-card">
      <CardHeader className="pb-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <CardTitle className="text-white flex items-center text-lg">
              <BarChart3 className="h-5 w-5 mr-3 text-cyan-400" />
              {symbol}
            </CardTitle>
            <div className="flex items-center space-x-2">
              <span className="text-2xl font-mono font-bold text-white">${currentPrice.toFixed(2)}</span>
              <div className="flex items-center space-x-1">
                {priceChange >= 0 ? (
                  <TrendingUp className="h-4 w-4 price-up" />
                ) : (
                  <TrendingDown className="h-4 w-4 price-down" />
                )}
                <span className={`text-sm font-mono ${priceChange >= 0 ? "price-up" : "price-down"}`}>
                  {priceChange >= 0 ? "+" : ""}
                  {priceChange.toFixed(2)} ({priceChangePercent.toFixed(2)}%)
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center space-x-3">
            {/* 时间周期选择 */}
            <div className="flex items-center space-x-1 bg-blue-900/30 rounded-lg p-1">
              {timeframes.map((tf) => (
                <Button
                  key={tf.value}
                  size="sm"
                  variant={timeframe === tf.value ? "default" : "ghost"}
                  onClick={() => setTimeframe(tf.value)}
                  className={`h-7 px-3 text-xs ${
                    timeframe === tf.value ? "htx-button" : "text-blue-200/80 hover:text-white hover:bg-blue-500/20"
                  }`}
                >
                  {tf.label}
                </Button>
              ))}
            </div>

            <Button size="sm" variant="outline" className="border-blue-500/30 text-blue-200 hover:bg-blue-500/20">
              <Settings className="h-4 w-4 mr-1" />
              Indicators
            </Button>

            <Button size="sm" variant="outline" className="border-blue-500/30 text-blue-200 hover:bg-blue-500/20">
              <Maximize2 className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* 技术指标开关 */}
        <div className="flex items-center space-x-6 mt-4">
          <div className="flex items-center space-x-2">
            <Switch
              checked={indicators.ma}
              onCheckedChange={(checked) => setIndicators((prev) => ({ ...prev, ma: checked }))}
            />
            <span className="text-sm text-blue-200/80">MA Lines</span>
          </div>
          <div className="flex items-center space-x-2">
            <Switch
              checked={indicators.volume}
              onCheckedChange={(checked) => setIndicators((prev) => ({ ...prev, volume: checked }))}
            />
            <span className="text-sm text-blue-200/80">Volume</span>
          </div>
          <div className="flex items-center space-x-2">
            <Switch
              checked={indicators.rsi}
              onCheckedChange={(checked) => setIndicators((prev) => ({ ...prev, rsi: checked }))}
            />
            <span className="text-sm text-blue-200/80">RSI</span>
          </div>
          <div className="flex items-center space-x-2">
            <Switch
              checked={indicators.macd}
              onCheckedChange={(checked) => setIndicators((prev) => ({ ...prev, macd: checked }))}
            />
            <span className="text-sm text-blue-200/80">MACD</span>
          </div>
        </div>
      </CardHeader>

      <CardContent>
        <div ref={chartRef} style={{ height: `${height}px` }}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
              <XAxis
                dataKey="time"
                axisLine={false}
                tickLine={false}
                tick={{ fill: "#8B9DC3", fontSize: 11 }}
                interval="preserveStartEnd"
              />
              <YAxis
                domain={["dataMin - 100", "dataMax + 100"]}
                axisLine={false}
                tickLine={false}
                tick={{ fill: "#8B9DC3", fontSize: 11 }}
                orientation="right"
              />

              <Tooltip content={<CustomTooltip />} />

              {/* K线图 */}
              <Bar dataKey="high" shape={<CandlestickBar />} isAnimationActive={false} />

              {/* 移动平均线 */}
              {indicators.ma && (
                <>
                  <Line
                    type="monotone"
                    dataKey="ma5"
                    stroke="#FFD700"
                    strokeWidth={1}
                    dot={false}
                    connectNulls={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="ma10"
                    stroke="#FF6B6B"
                    strokeWidth={1}
                    dot={false}
                    connectNulls={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="ma20"
                    stroke="#4ECDC4"
                    strokeWidth={1}
                    dot={false}
                    connectNulls={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="ma60"
                    stroke="#A8E6CF"
                    strokeWidth={1}
                    dot={false}
                    connectNulls={false}
                  />
                </>
              )}
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        {/* 成交量图表 */}
        {indicators.volume && (
          <div className="mt-4" style={{ height: "120px" }}>
            <div className="flex items-center space-x-2 mb-2">
              <Volume2 className="h-4 w-4 text-blue-400" />
              <span className="text-sm text-blue-200/80">Volume</span>
            </div>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={data}>
                <XAxis
                  dataKey="time"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "#8B9DC3", fontSize: 10 }}
                  interval="preserveStartEnd"
                />
                <YAxis axisLine={false} tickLine={false} tick={{ fill: "#8B9DC3", fontSize: 10 }} orientation="right" />
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (active && payload && payload.length) {
                      return (
                        <div className="htx-card p-2 text-xs">
                          <p className="text-blue-200/80">{label}</p>
                          <p className="text-white font-mono">Volume: {payload[0].value?.toFixed(2)}</p>
                        </div>
                      )
                    }
                    return null
                  }}
                />
                <Bar dataKey="volume">
                  {data.map((entry, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={entry.close >= entry.open ? "#00D4AA" : "#F5455C"}
                      fillOpacity={0.6}
                    />
                  ))}
                </Bar>
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* RSI指标 */}
        {indicators.rsi && (
          <div className="mt-4" style={{ height: "100px" }}>
            <div className="flex items-center space-x-2 mb-2">
              <Activity className="h-4 w-4 text-purple-400" />
              <span className="text-sm text-blue-200/80">RSI (14)</span>
            </div>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={data}>
                <XAxis
                  dataKey="time"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "#8B9DC3", fontSize: 10 }}
                  interval="preserveStartEnd"
                />
                <YAxis
                  domain={[0, 100]}
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "#8B9DC3", fontSize: 10 }}
                  orientation="right"
                />
                <ReferenceLine y={70} stroke="#F5455C" strokeDasharray="3 3" strokeOpacity={0.5} />
                <ReferenceLine y={30} stroke="#00D4AA" strokeDasharray="3 3" strokeOpacity={0.5} />
                <ReferenceLine y={50} stroke="#8B9DC3" strokeDasharray="1 1" strokeOpacity={0.3} />
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (active && payload && payload.length) {
                      return (
                        <div className="htx-card p-2 text-xs">
                          <p className="text-blue-200/80">{label}</p>
                          <p className="text-white font-mono">RSI: {payload[0].value?.toFixed(2)}</p>
                        </div>
                      )
                    }
                    return null
                  }}
                />
                <Line type="monotone" dataKey="rsi" stroke="#A855F7" strokeWidth={2} dot={false} connectNulls={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* 图例 */}
        {indicators.ma && (
          <div className="flex items-center space-x-6 mt-4 pt-4 border-t border-blue-500/20">
            <div className="flex items-center space-x-2">
              <div className="w-3 h-0.5 bg-yellow-400"></div>
              <span className="text-xs text-blue-200/80">MA5</span>
            </div>
            <div className="flex items-center space-x-2">
              <div className="w-3 h-0.5 bg-red-400"></div>
              <span className="text-xs text-blue-200/80">MA10</span>
            </div>
            <div className="flex items-center space-x-2">
              <div className="w-3 h-0.5 bg-cyan-400"></div>
              <span className="text-xs text-blue-200/80">MA20</span>
            </div>
            <div className="flex items-center space-x-2">
              <div className="w-3 h-0.5 bg-green-300"></div>
              <span className="text-xs text-blue-200/80">MA60</span>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
