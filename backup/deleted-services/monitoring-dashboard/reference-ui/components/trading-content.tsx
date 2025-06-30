"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { TrendingUp, Wifi, Database, AlertTriangle, CheckCircle } from "lucide-react"
import { OrderBook } from "@/components/order-book"
// 在imports部分添加新的Canvas组件
import { CanvasKlineChart } from "@/components/canvas-kline-chart"

export function TradingContent() {
  const exchanges = [
    {
      name: "HTX",
      status: "connected",
      latency: "12ms",
      reconnects: 0,
      wsConnections: 8,
      apiQuota: "85%",
    },
    {
      name: "Binance",
      status: "connected",
      latency: "18ms",
      reconnects: 1,
      wsConnections: 6,
      apiQuota: "62%",
    },
    {
      name: "OKX",
      status: "warning",
      latency: "45ms",
      reconnects: 3,
      wsConnections: 4,
      apiQuota: "91%",
    },
  ]

  const tradingPairs = [
    {
      symbol: "BTC/USDT",
      price: "43,256.78",
      change: "+2.34%",
      volume: "1.2B",
      isUp: true,
    },
    {
      symbol: "ETH/USDT",
      price: "2,678.90",
      change: "-1.23%",
      volume: "856M",
      isUp: false,
    },
    {
      symbol: "BNB/USDT",
      price: "312.45",
      change: "+0.87%",
      volume: "234M",
      isUp: true,
    },
    {
      symbol: "SOL/USDT",
      price: "98.76",
      change: "+5.21%",
      volume: "445M",
      isUp: true,
    },
  ]

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "connected":
        return <CheckCircle className="h-4 w-4 text-cyan-400" />
      case "warning":
        return <AlertTriangle className="h-4 w-4 text-yellow-400" />
      case "disconnected":
        return <AlertTriangle className="h-4 w-4 text-red-400" />
      default:
        return <CheckCircle className="h-4 w-4 text-cyan-400" />
    }
  }

  const getStatusBadge = (status: string) => {
    const variants = {
      connected: "bg-cyan-400/20 text-cyan-400 border-cyan-400/50",
      warning: "bg-yellow-400/20 text-yellow-400 border-yellow-400/50",
      disconnected: "bg-red-400/20 text-red-400 border-red-400/50",
    }

    return (
      <Badge className={variants[status as keyof typeof variants] || variants.connected}>
        {status === "connected" ? "CONNECTED" : status === "warning" ? "WARNING" : "DISCONNECTED"}
      </Badge>
    )
  }

  return (
    <div className="p-6 space-y-6 min-h-screen">
      <div>
        <h1 className="text-3xl font-bold text-white mb-1">Trading Monitor</h1>
        <p className="text-blue-200/70">Real-time market data and exchange monitoring</p>
      </div>

      {/* 主要交易界面 */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* Canvas优化的K线图表 */}
        <div className="xl:col-span-2">
          <CanvasKlineChart symbol="BTC/USDT" height={600} maxDataPoints={2000} />
        </div>

        {/* 订单簿 */}
        <div>
          <OrderBook symbol="BTC/USDT" />
        </div>
      </div>

      {/* Exchange Connection Status */}
      <Card className="htx-card">
        <CardHeader>
          <CardTitle className="text-white flex items-center text-lg">
            <Wifi className="h-5 w-5 mr-3 text-blue-400" />
            Exchange Connection Status
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {exchanges.map((exchange, index) => (
              <div
                key={exchange.name}
                className={`p-4 rounded-lg border border-blue-500/20 htx-table-row ${
                  index % 2 === 0 ? "bg-blue-900/10" : "bg-transparent"
                }`}
              >
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center space-x-2">
                    {getStatusIcon(exchange.status)}
                    <h3 className="font-medium text-white">{exchange.name}</h3>
                  </div>
                  {getStatusBadge(exchange.status)}
                </div>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-blue-200/80">Latency</span>
                    <span className="text-white font-mono">{exchange.latency}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-blue-200/80">Reconnects</span>
                    <span className="text-white font-mono">{exchange.reconnects}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-blue-200/80">WebSocket</span>
                    <span className="text-white font-mono">{exchange.wsConnections}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-blue-200/80">API Quota</span>
                    <span className="text-white font-mono">{exchange.apiQuota}</span>
                  </div>
                  <Progress value={Number.parseInt(exchange.apiQuota)} className="h-1 mt-2 bg-blue-900/30" />
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Market Data */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="htx-card">
          <CardHeader>
            <CardTitle className="text-white flex items-center text-lg">
              <TrendingUp className="h-5 w-5 mr-3 text-cyan-400" />
              Real-time Price Monitor
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {tradingPairs.map((pair, index) => (
                <div
                  key={pair.symbol}
                  className={`flex items-center justify-between p-3 rounded border border-blue-500/20 hover:bg-blue-500/10 transition-colors htx-table-row ${
                    index % 2 === 0 ? "bg-blue-900/10" : "bg-transparent"
                  }`}
                >
                  <div>
                    <p className="font-medium text-white font-mono">{pair.symbol}</p>
                    <p className="text-sm text-blue-300/60">24h Vol: {pair.volume}</p>
                  </div>
                  <div className="text-right">
                    <p className="font-medium text-white font-mono">${pair.price}</p>
                    <p className={`text-sm font-mono ${pair.isUp ? "price-up" : "price-down"}`}>{pair.change}</p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card className="htx-card">
          <CardHeader>
            <CardTitle className="text-white flex items-center text-lg">
              <Database className="h-5 w-5 mr-3 text-blue-400" />
              Data Quality Monitor
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <div className="flex justify-between mb-2">
                <span className="text-sm text-blue-200/80">Data Integrity</span>
                <span className="text-sm text-white font-mono">99.8%</span>
              </div>
              <Progress value={99.8} className="h-2 bg-blue-900/30" />
            </div>
            <div>
              <div className="flex justify-between mb-2">
                <span className="text-sm text-blue-200/80">Average Latency</span>
                <span className="text-sm text-white font-mono">15ms</span>
              </div>
              <Progress value={85} className="h-2 bg-blue-900/30" />
            </div>
            <div>
              <div className="flex justify-between mb-2">
                <span className="text-sm text-blue-200/80">Packet Loss</span>
                <span className="text-sm price-up font-mono">0.02%</span>
              </div>
              <Progress value={2} className="h-2 bg-blue-900/30" />
            </div>
            <div className="pt-4 border-t border-blue-500/20">
              <div className="flex justify-between items-center">
                <span className="text-sm text-blue-200/80">Anomaly Detection</span>
                <Badge className="bg-cyan-400/20 text-cyan-400 border-cyan-400/50">NORMAL</Badge>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
