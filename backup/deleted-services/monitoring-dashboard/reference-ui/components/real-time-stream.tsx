"use client"

import { useState, useEffect } from "react"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { TrendingUp, TrendingDown, Activity, Zap } from "lucide-react"

export function RealTimeStream() {
  const [tradingData, setTradingData] = useState<Array<any>>([])
  const [systemLogs, setSystemLogs] = useState<Array<any>>([])

  useEffect(() => {
    const generateTradingData = () => {
      const symbols = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "ADA/USDT", "SOL/USDT", "DOGE/USDT", "XRP/USDT"]
      const newData = {
        id: Date.now(),
        symbol: symbols[Math.floor(Math.random() * symbols.length)],
        price: (Math.random() * 50000 + 20000).toFixed(2),
        change: (Math.random() * 10 - 5).toFixed(2),
        volume: (Math.random() * 1000000).toFixed(0),
        time: new Date().toLocaleTimeString("en-US", { hour12: false }),
      }

      setTradingData((prev) => [newData, ...prev.slice(0, 19)])
    }

    const generateSystemLogs = () => {
      const logTypes = ["INFO", "WARN", "ERROR", "DEBUG"]
      const messages = [
        "WebSocket connection established successfully",
        "Market data stream initialized",
        "Order book update received",
        "Price alert triggered for BTC/USDT",
        "Database connection pool refreshed",
        "API rate limit check passed",
        "System health check completed",
        "Cache invalidation completed",
      ]

      const newLog = {
        id: Date.now(),
        type: logTypes[Math.floor(Math.random() * logTypes.length)],
        message: messages[Math.floor(Math.random() * messages.length)],
        service: ["api-gateway", "data-collector", "trading-engine", "monitoring"][Math.floor(Math.random() * 4)],
        time: new Date().toLocaleTimeString("en-US", { hour12: false }),
      }

      setSystemLogs((prev) => [newLog, ...prev.slice(0, 19)])
    }

    const tradingInterval = setInterval(generateTradingData, 1500)
    const logsInterval = setInterval(generateSystemLogs, 2500)

    generateTradingData()
    generateSystemLogs()

    return () => {
      clearInterval(tradingInterval)
      clearInterval(logsInterval)
    }
  }, [])

  const getLogBadge = (type: string) => {
    const variants = {
      INFO: "bg-blue-400/20 text-blue-400 border-blue-400/50",
      WARN: "bg-yellow-400/20 text-yellow-400 border-yellow-400/50",
      ERROR: "bg-red-400/20 text-red-400 border-red-400/50",
      DEBUG: "bg-blue-300/20 text-blue-300 border-blue-300/50",
    }

    return (
      <Badge className={`${variants[type as keyof typeof variants] || variants.INFO} text-xs px-2 py-1`}>{type}</Badge>
    )
  }

  return (
    <Tabs defaultValue="trading" className="w-full">
      <TabsList className="grid w-full grid-cols-3 bg-blue-900/30 h-10">
        <TabsTrigger value="trading" className="data-[state=active]:bg-blue-500/30 text-sm">
          Market Data
        </TabsTrigger>
        <TabsTrigger value="logs" className="data-[state=active]:bg-blue-500/30 text-sm">
          System Logs
        </TabsTrigger>
        <TabsTrigger value="network" className="data-[state=active]:bg-blue-500/30 text-sm">
          Network I/O
        </TabsTrigger>
      </TabsList>

      <TabsContent value="trading" className="mt-4">
        <ScrollArea className="h-64">
          <div className="space-y-2">
            {tradingData.map((trade, index) => (
              <div
                key={trade.id}
                className={`flex items-center justify-between p-3 rounded-lg border border-blue-500/20 hover:bg-blue-500/10 transition-colors htx-table-row ${
                  index % 2 === 0 ? "bg-blue-900/10" : "bg-transparent"
                }`}
              >
                <div className="flex items-center space-x-3">
                  {Number.parseFloat(trade.change) >= 0 ? (
                    <TrendingUp className="h-4 w-4 price-up" />
                  ) : (
                    <TrendingDown className="h-4 w-4 price-down" />
                  )}
                  <div>
                    <p className="text-sm font-mono font-medium text-white">{trade.symbol}</p>
                    <p className="text-xs text-blue-300/60">{trade.time}</p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-sm font-mono font-bold text-white">${trade.price}</p>
                  <p
                    className={`text-sm font-mono ${Number.parseFloat(trade.change) >= 0 ? "price-up" : "price-down"}`}
                  >
                    {Number.parseFloat(trade.change) >= 0 ? "+" : ""}
                    {trade.change}%
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-xs text-blue-300/60">Volume</p>
                  <p className="text-sm font-mono text-blue-200">{Number(trade.volume).toLocaleString()}</p>
                </div>
              </div>
            ))}
          </div>
        </ScrollArea>
      </TabsContent>

      <TabsContent value="logs" className="mt-4">
        <ScrollArea className="h-64">
          <div className="space-y-2">
            {systemLogs.map((log, index) => (
              <div
                key={log.id}
                className={`flex items-center justify-between p-3 rounded-lg border border-blue-500/20 hover:bg-blue-500/10 transition-colors htx-table-row ${
                  index % 2 === 0 ? "bg-blue-900/10" : "bg-transparent"
                }`}
              >
                <div className="flex items-center space-x-3 flex-1">
                  <Activity className="h-4 w-4 text-blue-400" />
                  <div className="flex-1">
                    <p className="text-sm text-white">{log.message}</p>
                    <p className="text-xs text-blue-300/60 font-mono">
                      {log.service} • {log.time}
                    </p>
                  </div>
                </div>
                {getLogBadge(log.type)}
              </div>
            ))}
          </div>
        </ScrollArea>
      </TabsContent>

      <TabsContent value="network" className="mt-4">
        <div className="h-64 flex items-center justify-center text-blue-300/60">
          <div className="text-center">
            <Zap className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p className="text-lg font-medium">Network Traffic Monitor</p>
            <p className="text-sm mt-2 opacity-75">Real-time network I/O visualization</p>
            <div className="flex items-center justify-center space-x-4 mt-4 text-xs">
              <div className="flex items-center space-x-1">
                <div className="status-dot bg-cyan-400"></div>
                <span>Inbound: 125 MB/s</span>
              </div>
              <div className="flex items-center space-x-1">
                <div className="status-dot bg-blue-400"></div>
                <span>Outbound: 89 MB/s</span>
              </div>
            </div>
          </div>
        </div>
      </TabsContent>
    </Tabs>
  )
}
