"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { TrendingUp, BarChart3 } from "lucide-react"

interface OrderBookEntry {
  price: number
  amount: number
  total: number
}

interface OrderBookProps {
  symbol?: string
}

export function OrderBook({ symbol = "BTC/USDT" }: OrderBookProps) {
  const [asks, setAsks] = useState<OrderBookEntry[]>([])
  const [bids, setBids] = useState<OrderBookEntry[]>([])
  const [spread, setSpread] = useState(0)
  const [spreadPercent, setSpreadPercent] = useState(0)

  useEffect(() => {
    const generateOrderBook = () => {
      const basePrice = 43000 + Math.random() * 1000
      const newAsks: OrderBookEntry[] = []
      const newBids: OrderBookEntry[] = []

      let totalAsk = 0
      let totalBid = 0

      // 生成卖单 (asks)
      for (let i = 0; i < 15; i++) {
        const price = basePrice + (i + 1) * (Math.random() * 10 + 5)
        const amount = Math.random() * 5 + 0.1
        totalAsk += amount
        newAsks.push({
          price: Number(price.toFixed(2)),
          amount: Number(amount.toFixed(4)),
          total: Number(totalAsk.toFixed(4)),
        })
      }

      // 生成买单 (bids)
      for (let i = 0; i < 15; i++) {
        const price = basePrice - (i + 1) * (Math.random() * 10 + 5)
        const amount = Math.random() * 5 + 0.1
        totalBid += amount
        newBids.push({
          price: Number(price.toFixed(2)),
          amount: Number(amount.toFixed(4)),
          total: Number(totalBid.toFixed(4)),
        })
      }

      setAsks(newAsks)
      setBids(newBids)

      // 计算价差
      if (newAsks.length > 0 && newBids.length > 0) {
        const bestAsk = newAsks[0].price
        const bestBid = newBids[0].price
        const spreadValue = bestAsk - bestBid
        setSpread(spreadValue)
        setSpreadPercent((spreadValue / bestBid) * 100)
      }
    }

    generateOrderBook()
    const interval = setInterval(generateOrderBook, 2000)
    return () => clearInterval(interval)
  }, [])

  const maxAskTotal = Math.max(...asks.map((ask) => ask.total))
  const maxBidTotal = Math.max(...bids.map((bid) => bid.total))

  return (
    <Card className="htx-card">
      <CardHeader className="pb-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-white flex items-center text-lg">
            <BarChart3 className="h-5 w-5 mr-3 text-cyan-400" />
            Order Book - {symbol}
          </CardTitle>
          <div className="flex items-center space-x-2">
            <Badge className="bg-blue-400/20 text-blue-400 border-blue-400/50">
              Spread: ${spread.toFixed(2)} ({spreadPercent.toFixed(3)}%)
            </Badge>
          </div>
        </div>
      </CardHeader>

      <CardContent>
        <div className="grid grid-cols-3 gap-4 text-xs text-blue-300/60 mb-3 font-medium">
          <div>Price (USDT)</div>
          <div className="text-right">Amount (BTC)</div>
          <div className="text-right">Total</div>
        </div>

        {/* 卖单 (Asks) */}
        <div className="space-y-1 mb-4">
          {asks
            .slice()
            .reverse()
            .map((ask, index) => {
              const widthPercent = (ask.total / maxAskTotal) * 100
              return (
                <div key={index} className="relative">
                  <div
                    className="absolute right-0 top-0 h-full bg-red-500/10 transition-all duration-300"
                    style={{ width: `${widthPercent}%` }}
                  />
                  <div className="relative grid grid-cols-3 gap-4 py-1 px-2 hover:bg-blue-500/10 transition-colors">
                    <div className="price-down font-mono text-sm">{ask.price.toFixed(2)}</div>
                    <div className="text-right text-white font-mono text-sm">{ask.amount.toFixed(4)}</div>
                    <div className="text-right text-blue-200/80 font-mono text-sm">{ask.total.toFixed(4)}</div>
                  </div>
                </div>
              )
            })}
        </div>

        {/* 最新价格 */}
        <div className="flex items-center justify-center py-3 border-y border-blue-500/20 mb-4">
          <div className="flex items-center space-x-2">
            <TrendingUp className="h-4 w-4 price-up" />
            <span className="text-lg font-mono font-bold text-white">
              {bids.length > 0 ? ((asks[0]?.price + bids[0]?.price) / 2).toFixed(2) : "0.00"}
            </span>
            <span className="text-sm text-blue-300/60">
              ≈ ${bids.length > 0 ? ((asks[0]?.price + bids[0]?.price) / 2).toFixed(2) : "0.00"}
            </span>
          </div>
        </div>

        {/* 买单 (Bids) */}
        <div className="space-y-1">
          {bids.map((bid, index) => {
            const widthPercent = (bid.total / maxBidTotal) * 100
            return (
              <div key={index} className="relative">
                <div
                  className="absolute right-0 top-0 h-full bg-green-500/10 transition-all duration-300"
                  style={{ width: `${widthPercent}%` }}
                />
                <div className="relative grid grid-cols-3 gap-4 py-1 px-2 hover:bg-blue-500/10 transition-colors">
                  <div className="price-up font-mono text-sm">{bid.price.toFixed(2)}</div>
                  <div className="text-right text-white font-mono text-sm">{bid.amount.toFixed(4)}</div>
                  <div className="text-right text-blue-200/80 font-mono text-sm">{bid.total.toFixed(4)}</div>
                </div>
              </div>
            )
          })}
        </div>

        {/* 统计信息 */}
        <div className="mt-4 pt-4 border-t border-blue-500/20 grid grid-cols-2 gap-4 text-sm">
          <div className="flex justify-between">
            <span className="text-blue-300/60">Total Bids:</span>
            <span className="text-white font-mono">
              {bids.reduce((sum, bid) => sum + bid.amount, 0).toFixed(4)} BTC
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-blue-300/60">Total Asks:</span>
            <span className="text-white font-mono">
              {asks.reduce((sum, ask) => sum + ask.amount, 0).toFixed(4)} BTC
            </span>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
