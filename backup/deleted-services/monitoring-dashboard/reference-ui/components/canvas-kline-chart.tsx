"use client"

import type React from "react"

import { useState, useEffect, useRef, useCallback, useMemo } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
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

interface CanvasKlineChartProps {
  symbol?: string
  height?: number
  maxDataPoints?: number
}

interface ChartConfig {
  padding: { top: number; right: number; bottom: number; left: number }
  candleWidth: number
  candleSpacing: number
  colors: {
    up: string
    down: string
    ma5: string
    ma10: string
    ma20: string
    ma60: string
    volume: string
    grid: string
    text: string
    background: string
  }
}

export function CanvasKlineChart({ symbol = "BTC/USDT", height = 500, maxDataPoints = 1000 }: CanvasKlineChartProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const volumeCanvasRef = useRef<HTMLCanvasElement>(null)
  const rsiCanvasRef = useRef<HTMLCanvasElement>(null)
  const overlayCanvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

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
  const [canvasSize, setCanvasSize] = useState({ width: 0, height: 0 })
  const [mousePos, setMousePos] = useState<{ x: number; y: number } | null>(null)
  const [crosshair, setCrosshair] = useState<{ x: number; y: number; data: KlineData } | null>(null)

  // 图表配置
  const config: ChartConfig = useMemo(
    () => ({
      padding: { top: 20, right: 80, bottom: 30, left: 20 },
      candleWidth: 8,
      candleSpacing: 2,
      colors: {
        up: "#00D4AA",
        down: "#F5455C",
        ma5: "#FFD700",
        ma10: "#FF6B6B",
        ma20: "#4ECDC4",
        ma60: "#A8E6CF",
        volume: "#8B9DC3",
        grid: "rgba(139, 157, 195, 0.1)",
        text: "#8B9DC3",
        background: "transparent",
      },
    }),
    [],
  )

  // 生成高性能模拟数据
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

      let basePrice = 43000 + Math.random() * 10000
      const newData: KlineData[] = []

      // 生成大量数据点以测试性能
      for (let i = maxDataPoints; i >= 0; i--) {
        const timestamp = now - i * interval
        const time = new Date(timestamp)

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
    const interval = setInterval(generateKlineData, 10000) // 降低更新频率以测试性能
    return () => clearInterval(interval)
  }, [timeframe, maxDataPoints])

  // 计算技术指标（优化版本）
  const calculateIndicators = useCallback((data: KlineData[]) => {
    const len = data.length

    // 使用更高效的循环计算移动平均线
    for (let i = 0; i < len; i++) {
      // MA5
      if (i >= 4) {
        let sum = 0
        for (let j = i - 4; j <= i; j++) {
          sum += data[j].close
        }
        data[i].ma5 = sum / 5
      }

      // MA10
      if (i >= 9) {
        let sum = 0
        for (let j = i - 9; j <= i; j++) {
          sum += data[j].close
        }
        data[i].ma10 = sum / 10
      }

      // MA20
      if (i >= 19) {
        let sum = 0
        for (let j = i - 19; j <= i; j++) {
          sum += data[j].close
        }
        data[i].ma20 = sum / 20
      }

      // MA60
      if (i >= 59) {
        let sum = 0
        for (let j = i - 59; j <= i; j++) {
          sum += data[j].close
        }
        data[i].ma60 = sum / 60
      }
    }

    // RSI计算（优化版本）
    for (let i = 14; i < len; i++) {
      let gains = 0
      let losses = 0

      for (let j = i - 13; j <= i; j++) {
        const change = data[j].close - (data[j - 1]?.close || data[j].close)
        if (change > 0) gains += change
        else losses += Math.abs(change)
      }

      const avgGain = gains / 14
      const avgLoss = losses / 14
      const rs = avgLoss === 0 ? 100 : avgGain / avgLoss
      data[i].rsi = 100 - 100 / (1 + rs)
    }
  }, [])

  // 响应式Canvas尺寸
  useEffect(() => {
    const updateCanvasSize = () => {
      if (containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect()
        setCanvasSize({ width: rect.width, height })
      }
    }

    updateCanvasSize()
    window.addEventListener("resize", updateCanvasSize)
    return () => window.removeEventListener("resize", updateCanvasSize)
  }, [height])

  // 高性能Canvas渲染函数
  const renderChart = useCallback(() => {
    const canvas = canvasRef.current
    const ctx = canvas?.getContext("2d")
    if (!canvas || !ctx || data.length === 0) return

    const { width, height } = canvasSize
    const { padding } = config

    // 设置高DPI支持
    const dpr = window.devicePixelRatio || 1
    canvas.width = width * dpr
    canvas.height = height * dpr
    canvas.style.width = `${width}px`
    canvas.style.height = `${height}px`
    ctx.scale(dpr, dpr)

    // 清空画布
    ctx.clearRect(0, 0, width, height)

    // 计算绘制区域
    const chartWidth = width - padding.left - padding.right
    const chartHeight = height - padding.top - padding.bottom

    // 计算价格范围
    const visibleData = data.slice(-Math.floor(chartWidth / (config.candleWidth + config.candleSpacing)))
    const prices = visibleData.flatMap((d) => [d.high, d.low])
    const minPrice = Math.min(...prices)
    const maxPrice = Math.max(...prices)
    const priceRange = maxPrice - minPrice
    const priceScale = chartHeight / priceRange

    // 绘制网格线（优化：减少网格线数量）
    ctx.strokeStyle = config.colors.grid
    ctx.lineWidth = 1
    ctx.beginPath()

    // 水平网格线
    for (let i = 0; i <= 5; i++) {
      const y = padding.top + (chartHeight / 5) * i
      ctx.moveTo(padding.left, y)
      ctx.lineTo(width - padding.right, y)
    }

    // 垂直网格线
    let timeStepCalc = Math.max(1, Math.floor(visibleData.length / 10))
    for (let i = 0; i < visibleData.length; i += timeStepCalc) {
      const x = padding.left + i * (config.candleWidth + config.candleSpacing)
      ctx.moveTo(x, padding.top)
      ctx.lineTo(x, height - padding.bottom)
    }
    ctx.stroke()

    // 绘制K线（批量渲染优化）
    const candleWidth = config.candleWidth
    const candleSpacing = config.candleSpacing

    // 分别绘制上涨和下跌的K线以减少状态切换
    const upCandles: Array<{ x: number; open: number; high: number; low: number; close: number }> = []
    const downCandles: Array<{ x: number; open: number; high: number; low: number; close: number }> = []

    visibleData.forEach((item, index) => {
      const x = padding.left + index * (candleWidth + candleSpacing)
      const candleData = {
        x,
        open: padding.top + (maxPrice - item.open) * priceScale,
        high: padding.top + (maxPrice - item.high) * priceScale,
        low: padding.top + (maxPrice - item.low) * priceScale,
        close: padding.top + (maxPrice - item.close) * priceScale,
      }

      if (item.close >= item.open) {
        upCandles.push(candleData)
      } else {
        downCandles.push(candleData)
      }
    })

    // 批量绘制上涨K线
    ctx.strokeStyle = config.colors.up
    ctx.fillStyle = config.colors.up
    ctx.lineWidth = 1
    upCandles.forEach((candle) => {
      // 影线
      ctx.beginPath()
      ctx.moveTo(candle.x + candleWidth / 2, candle.high)
      ctx.lineTo(candle.x + candleWidth / 2, candle.low)
      ctx.stroke()

      // 实体
      ctx.fillRect(candle.x, candle.close, candleWidth, candle.open - candle.close)
    })

    // 批量绘制下跌K线
    ctx.strokeStyle = config.colors.down
    ctx.fillStyle = config.colors.down
    downCandles.forEach((candle) => {
      // 影线
      ctx.beginPath()
      ctx.moveTo(candle.x + candleWidth / 2, candle.high)
      ctx.lineTo(candle.x + candleWidth / 2, candle.low)
      ctx.stroke()

      // 实体
      ctx.fillRect(candle.x, candle.open, candleWidth, candle.close - candle.open)
    })

    // 绘制移动平均线（优化：使用Path2D）
    if (indicators.ma) {
      const maLines = [
        { key: "ma5", color: config.colors.ma5 },
        { key: "ma10", color: config.colors.ma10 },
        { key: "ma20", color: config.colors.ma20 },
        { key: "ma60", color: config.colors.ma60 },
      ]

      maLines.forEach(({ key, color }) => {
        ctx.strokeStyle = color
        ctx.lineWidth = 1
        ctx.beginPath()

        let firstPoint = true
        visibleData.forEach((item, index) => {
          const value = item[key as keyof KlineData] as number
          if (value) {
            const x = padding.left + index * (candleWidth + candleSpacing) + candleWidth / 2
            const y = padding.top + (maxPrice - value) * priceScale

            if (firstPoint) {
              ctx.moveTo(x, y)
              firstPoint = false
            } else {
              ctx.lineTo(x, y)
            }
          }
        })
        ctx.stroke()
      })
    }

    // 绘制价格标签
    ctx.fillStyle = config.colors.text
    ctx.font = "11px monospace"
    ctx.textAlign = "left"

    for (let i = 0; i <= 5; i++) {
      const price = maxPrice - (priceRange / 5) * i
      const y = padding.top + (chartHeight / 5) * i
      ctx.fillText(price.toFixed(2), width - padding.right + 5, y + 4)
    }

    // 绘制时间标签
    ctx.textAlign = "center"
    timeStepCalc = Math.max(1, Math.floor(visibleData.length / 8))
    for (let i = 0; i < visibleData.length; i += timeStepCalc) {
      const x = padding.left + i * (candleWidth + candleSpacing) + candleWidth / 2
      ctx.fillText(visibleData[i].time, x, height - 5)
    }
  }, [data, canvasSize, config, indicators])

  // 渲染成交量图表
  const renderVolumeChart = useCallback(() => {
    const canvas = volumeCanvasRef.current
    const ctx = canvas?.getContext("2d")
    if (!canvas || !ctx || data.length === 0 || !indicators.volume) return

    const { width } = canvasSize
    const volumeHeight = 120
    const { padding } = config

    // 设置高DPI支持
    const dpr = window.devicePixelRatio || 1
    canvas.width = width * dpr
    canvas.height = volumeHeight * dpr
    canvas.style.width = `${width}px`
    canvas.style.height = `${volumeHeight}px`
    ctx.scale(dpr, dpr)

    ctx.clearRect(0, 0, width, volumeHeight)

    const chartWidth = width - padding.left - padding.right
    const chartHeight = volumeHeight - 20

    const visibleData = data.slice(-Math.floor(chartWidth / (config.candleWidth + config.candleSpacing)))
    const maxVolume = Math.max(...visibleData.map((d) => d.volume))
    const volumeScale = chartHeight / maxVolume

    // 绘制成交量柱状图
    visibleData.forEach((item, index) => {
      const x = padding.left + index * (config.candleWidth + config.candleSpacing)
      const barHeight = item.volume * volumeScale
      const y = chartHeight - barHeight

      ctx.fillStyle = item.close >= item.open ? config.colors.up : config.colors.down
      ctx.globalAlpha = 0.6
      ctx.fillRect(x, y, config.candleWidth, barHeight)
    })

    ctx.globalAlpha = 1
  }, [data, canvasSize, config, indicators.volume])

  // 渲染RSI指标
  const renderRSIChart = useCallback(() => {
    const canvas = rsiCanvasRef.current
    const ctx = canvas?.getContext("2d")
    if (!canvas || !ctx || data.length === 0 || !indicators.rsi) return

    const { width } = canvasSize
    const rsiHeight = 100
    const { padding } = config

    const dpr = window.devicePixelRatio || 1
    canvas.width = width * dpr
    canvas.height = rsiHeight * dpr
    canvas.style.width = `${width}px`
    canvas.style.height = `${rsiHeight}px`
    ctx.scale(dpr, dpr)

    ctx.clearRect(0, 0, width, rsiHeight)

    const chartWidth = width - padding.left - padding.right
    const chartHeight = rsiHeight - 20

    const visibleData = data.slice(-Math.floor(chartWidth / (config.candleWidth + config.candleSpacing)))

    // 绘制RSI参考线
    ctx.strokeStyle = config.colors.grid
    ctx.lineWidth = 1
    ctx.setLineDash([3, 3])

    // 70线（超买）
    ctx.beginPath()
    ctx.moveTo(padding.left, chartHeight * 0.3)
    ctx.lineTo(width - padding.right, chartHeight * 0.3)
    ctx.stroke()

    // 30线（超卖）
    ctx.beginPath()
    ctx.moveTo(padding.left, chartHeight * 0.7)
    ctx.lineTo(width - padding.right, chartHeight * 0.7)
    ctx.stroke()

    // 50线（中线）
    ctx.beginPath()
    ctx.moveTo(padding.left, chartHeight * 0.5)
    ctx.lineTo(width - padding.right, chartHeight * 0.5)
    ctx.stroke()

    ctx.setLineDash([])

    // 绘制RSI线
    ctx.strokeStyle = "#A855F7"
    ctx.lineWidth = 2
    ctx.beginPath()

    let firstPoint = true
    visibleData.forEach((item, index) => {
      if (item.rsi !== undefined) {
        const x = padding.left + index * (config.candleWidth + config.candleSpacing) + config.candleWidth / 2
        const y = chartHeight - (item.rsi / 100) * chartHeight

        if (firstPoint) {
          ctx.moveTo(x, y)
          firstPoint = false
        } else {
          ctx.lineTo(x, y)
        }
      }
    })
    ctx.stroke()

    // RSI标签
    ctx.fillStyle = config.colors.text
    ctx.font = "10px monospace"
    ctx.textAlign = "left"
    ctx.fillText("70", width - padding.right + 5, chartHeight * 0.3 + 3)
    ctx.fillText("30", width - padding.right + 5, chartHeight * 0.7 + 3)
    ctx.fillText("50", width - padding.right + 5, chartHeight * 0.5 + 3)
  }, [data, canvasSize, config, indicators.rsi])

  // 鼠标事件处理
  const handleMouseMove = useCallback(
    (event: React.MouseEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current
      if (!canvas || data.length === 0) return

      const rect = canvas.getBoundingClientRect()
      const x = event.clientX - rect.left
      const y = event.clientY - rect.top

      setMousePos({ x, y })

      // 计算十字线对应的数据点
      const { padding } = config
      const chartWidth = canvasSize.width - padding.left - padding.right
      const visibleData = data.slice(-Math.floor(chartWidth / (config.candleWidth + config.candleSpacing)))

      const dataIndex = Math.floor((x - padding.left) / (config.candleWidth + config.candleSpacing))
      if (dataIndex >= 0 && dataIndex < visibleData.length) {
        setCrosshair({ x, y, data: visibleData[dataIndex] })
      }
    },
    [data, canvasSize, config],
  )

  const handleMouseLeave = useCallback(() => {
    setMousePos(null)
    setCrosshair(null)
  }, [])

  // 渲染十字线和信息框
  const renderOverlay = useCallback(() => {
    const canvas = overlayCanvasRef.current
    const ctx = canvas?.getContext("2d")
    if (!canvas || !ctx || !crosshair) return

    const { width, height } = canvasSize
    const dpr = window.devicePixelRatio || 1
    canvas.width = width * dpr
    canvas.height = height * dpr
    canvas.style.width = `${width}px`
    canvas.style.height = `${height}px`
    ctx.scale(dpr, dpr)

    ctx.clearRect(0, 0, width, height)

    // 绘制十字线
    ctx.strokeStyle = "rgba(139, 157, 195, 0.5)"
    ctx.lineWidth = 1
    ctx.setLineDash([2, 2])

    ctx.beginPath()
    ctx.moveTo(0, crosshair.y)
    ctx.lineTo(width, crosshair.y)
    ctx.moveTo(crosshair.x, 0)
    ctx.lineTo(crosshair.x, height)
    ctx.stroke()

    ctx.setLineDash([])

    // 绘制信息框
    const info = crosshair.data
    const isUp = info.close >= info.open
    const boxWidth = 200
    const boxHeight = 120
    const boxX = crosshair.x > width / 2 ? crosshair.x - boxWidth - 10 : crosshair.x + 10
    const boxY = Math.max(10, Math.min(crosshair.y - boxHeight / 2, height - boxHeight - 10))

    // 背景
    ctx.fillStyle = "rgba(27, 43, 77, 0.95)"
    ctx.strokeStyle = "rgba(46, 124, 246, 0.5)"
    ctx.lineWidth = 1
    ctx.fillRect(boxX, boxY, boxWidth, boxHeight)
    ctx.strokeRect(boxX, boxY, boxWidth, boxHeight)

    // 文本
    ctx.fillStyle = "#ffffff"
    ctx.font = "12px monospace"
    ctx.textAlign = "left"

    const lines = [
      `Time: ${info.time}`,
      `Open: ${info.open.toFixed(2)}`,
      `High: ${info.high.toFixed(2)}`,
      `Low: ${info.low.toFixed(2)}`,
      `Close: ${info.close.toFixed(2)}`,
      `Volume: ${info.volume.toFixed(2)}`,
    ]

    lines.forEach((line, index) => {
      ctx.fillText(line, boxX + 10, boxY + 20 + index * 16)
    })

    // 价格变化
    const change = info.close - info.open
    const changePercent = (change / info.open) * 100
    ctx.fillStyle = isUp ? config.colors.up : config.colors.down
    ctx.fillText(
      `Change: ${change >= 0 ? "+" : ""}${change.toFixed(2)} (${changePercent.toFixed(2)}%)`,
      boxX + 10,
      boxY + 20 + lines.length * 16,
    )
  }, [crosshair, canvasSize, config])

  // 执行渲染
  useEffect(() => {
    renderChart()
  }, [renderChart])

  useEffect(() => {
    renderVolumeChart()
  }, [renderVolumeChart])

  useEffect(() => {
    renderRSIChart()
  }, [renderRSIChart])

  useEffect(() => {
    renderOverlay()
  }, [renderOverlay])

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
              {symbol} - Canvas Optimized
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
            <div className="text-sm text-blue-300/60">Data Points: {data.length.toLocaleString()}</div>
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
              Settings
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
        </div>
      </CardHeader>

      <CardContent>
        <div ref={containerRef} className="relative">
          {/* 主K线图 - 修复层级问题 */}
          <canvas
            ref={canvasRef}
            className="block cursor-crosshair relative z-10"
            onMouseMove={handleMouseMove}
            onMouseLeave={handleMouseLeave}
          />
          {/* 十字线覆盖层 - 降低z-index */}
          <canvas ref={overlayCanvasRef} className="absolute top-0 left-0 pointer-events-none z-20" />

          {/* 成交量图表 */}
          {indicators.volume && (
            <div className="mt-4">
              <div className="flex items-center space-x-2 mb-2">
                <Volume2 className="h-4 w-4 text-blue-400" />
                <span className="text-sm text-blue-200/80">Volume</span>
              </div>
              <canvas ref={volumeCanvasRef} className="block" />
            </div>
          )}

          {/* RSI指标 */}
          {indicators.rsi && (
            <div className="mt-4">
              <div className="flex items-center space-x-2 mb-2">
                <Activity className="h-4 w-4 text-purple-400" />
                <span className="text-sm text-blue-200/80">RSI (14)</span>
              </div>
              <canvas ref={rsiCanvasRef} className="block" />
            </div>
          )}
        </div>

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

        {/* 性能信息 */}
        <div className="mt-4 pt-4 border-t border-blue-500/20 text-xs text-blue-300/60">
          <div className="flex items-center justify-between">
            <span>Canvas Rendering - High Performance Mode</span>
            <span>Rendering {data.length.toLocaleString()} data points</span>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
