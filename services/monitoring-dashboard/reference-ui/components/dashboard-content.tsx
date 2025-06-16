"use client"

import { useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import {
  Activity,
  Server,
  Users,
  AlertTriangle,
  Cpu,
  Wifi,
  RefreshCw,
  Download,
  Maximize2,
  TrendingUp,
} from "lucide-react"
import { MetricCard } from "@/components/metric-card"
import { SystemChart } from "@/components/system-chart"
import { ServiceStatus } from "@/components/service-status"
import { RealTimeStream } from "@/components/real-time-stream"
import { PerformanceMonitor } from "@/components/performance-monitor"

export function DashboardContent() {
  const [refreshing, setRefreshing] = useState(false)

  const handleRefresh = () => {
    setRefreshing(true)
    setTimeout(() => setRefreshing(false), 1000)
  }

  return (
    <div className="p-6 space-y-6 min-h-screen">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white mb-1">市场棱镜数据分析台</h1>
          <p className="text-blue-200/70">从市场数据中提取有价值的交易洞察</p>
        </div>
        <div className="flex items-center space-x-3">
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            disabled={refreshing}
            className="border-blue-500/30 text-blue-200 hover:bg-blue-500/20 hover:text-white"
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${refreshing ? "animate-spin" : ""}`} />
            刷新数据
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="border-blue-500/30 text-blue-200 hover:bg-blue-500/20 hover:text-white"
          >
            <Download className="h-4 w-4 mr-2" />
            导出报告
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="border-blue-500/30 text-blue-200 hover:bg-blue-500/20 hover:text-white"
          >
            <Maximize2 className="h-4 w-4 mr-2" />
            全屏模式
          </Button>
        </div>
      </div>

      {/* Key Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <MetricCard
          title="系统健康度"
          value="98.5%"
          icon={Activity}
          trend="up"
          trendValue="+2.1%"
          color="green"
          description="所有系统正常运行"
        />
        <MetricCard title="活跃服务" value="6/6" icon={Server} trend="stable" color="blue" description="全部服务在线" />
        <MetricCard
          title="实时连接"
          value="1,247"
          icon={Users}
          trend="up"
          trendValue="+156"
          color="cyan"
          description="WebSocket连接数"
        />
        <MetricCard
          title="活跃告警"
          value="3"
          icon={AlertTriangle}
          trend="down"
          trendValue="-2"
          color="orange"
          description="2个警告，1个信息"
        />
      </div>

      {/* System Resources & Service Status */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* System Resources */}
        <Card className="bg-slate-800/50 border-slate-700/50">
          <CardHeader className="pb-4">
            <CardTitle className="text-white flex items-center text-lg">
              <Cpu className="h-5 w-5 mr-3 text-blue-400" />
              系统资源监控
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="space-y-4">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm text-slate-300">CPU使用率</span>
                  <span className="text-sm font-mono text-white">45.2%</span>
                </div>
                <Progress value={45.2} className="h-2" />
                <div className="flex justify-between text-xs text-slate-400 mt-1">
                  <span>4核心</span>
                  <span>平均2.4 GHz</span>
                </div>
              </div>
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm text-slate-300">内存使用</span>
                  <span className="text-sm font-mono text-white">67.8% (10.8GB/16GB)</span>
                </div>
                <Progress value={67.8} className="h-2" />
                <div className="flex justify-between text-xs text-slate-400 mt-1">
                  <span>可用: 5.2GB</span>
                  <span>缓存: 2.1GB</span>
                </div>
              </div>
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm text-slate-300">磁盘使用</span>
                  <span className="text-sm font-mono text-white">34.5% (345GB/1TB)</span>
                </div>
                <Progress value={34.5} className="h-2" />
                <div className="flex justify-between text-xs text-slate-400 mt-1">
                  <span>剩余: 655GB</span>
                  <span>I/O: 125MB/s</span>
                </div>
              </div>
            </div>
            <SystemChart />
          </CardContent>
        </Card>

        {/* Service Status */}
        <Card className="bg-slate-800/50 border-slate-700/50">
          <CardHeader className="pb-4">
            <CardTitle className="text-white flex items-center text-lg">
              <Server className="h-5 w-5 mr-3 text-cyan-400" />
              服务状态监控
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ServiceStatus />
          </CardContent>
        </Card>
      </div>

      {/* Market Overview */}
      <Card className="bg-slate-800/50 border-slate-700/50">
        <CardHeader className="pb-4">
          <CardTitle className="text-white flex items-center text-lg">
            <TrendingUp className="h-5 w-5 mr-3 text-green-400" />
            市场数据分析
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              { symbol: "BTC/USDT", price: "43,256.78", change: "+2.34%", volume: "1.2B", isUp: true },
              { symbol: "ETH/USDT", price: "2,678.90", change: "-1.23%", volume: "856M", isUp: false },
              { symbol: "BNB/USDT", price: "312.45", change: "+0.87%", volume: "234M", isUp: true },
              { symbol: "SOL/USDT", price: "98.76", change: "+5.21%", volume: "445M", isUp: true },
            ].map((coin) => (
              <div key={coin.symbol} className="p-4 bg-slate-700/30 rounded-lg border border-slate-600/30">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-slate-300">{coin.symbol}</span>
                  <div className={`status-dot ${coin.isUp ? "bg-green-400" : "bg-red-400"}`}></div>
                </div>
                <div className="space-y-1">
                  <p className="text-lg font-mono font-bold text-white">${coin.price}</p>
                  <p className={`text-sm font-mono ${coin.isUp ? "price-up" : "price-down"}`}>{coin.change}</p>
                  <p className="text-xs text-slate-400">成交量: {coin.volume}</p>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Performance Monitor */}
      <PerformanceMonitor />

      {/* Real-time Data Stream */}
      <Card className="bg-slate-800/50 border-slate-700/50">
        <CardHeader className="pb-4">
          <CardTitle className="text-white flex items-center text-lg">
            <Wifi className="h-5 w-5 mr-3 text-blue-400" />
            实时数据流
          </CardTitle>
        </CardHeader>
        <CardContent>
          <RealTimeStream />
        </CardContent>
      </Card>
    </div>
  )
}
