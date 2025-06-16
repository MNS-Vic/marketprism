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
  RefreshCw,
  Download,
  Maximize2,
  TrendingUp,
  Zap,
  Database,
  Globe,
} from "lucide-react"
import { ModernMetricCard } from "@/components/modern-metric-card"
import { SystemChart } from "@/components/system-chart"
import { ServiceStatus } from "@/components/service-status"
import { RealTimeStream } from "@/components/real-time-stream"
import { PerformanceMonitor } from "@/components/performance-monitor"

export function ModernDashboardContent() {
  const [refreshing, setRefreshing] = useState(false)

  const handleRefresh = () => {
    setRefreshing(true)
    setTimeout(() => setRefreshing(false), 1000)
  }

  return (
    <div className="p-8 space-y-8 min-h-screen fade-in">
      {/* Modern Header */}
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <h1 className="responsive-title font-bold text-white">市场棱镜分析台</h1>
          <p className="text-blue-200/70 text-lg">高性能量化交易数据洞察平台</p>
          <div className="flex items-center space-x-4 text-sm text-blue-300/60">
            <div className="flex items-center space-x-2">
              <div className="status-indicator active"></div>
              <span>实时连接</span>
            </div>
            <div className="flex items-center space-x-2">
              <Globe className="h-4 w-4" />
              <span>全球市场</span>
            </div>
            <div className="flex items-center space-x-2">
              <Zap className="h-4 w-4" />
              <span>低延迟模式</span>
            </div>
          </div>
        </div>
        <div className="flex items-center space-x-3">
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            disabled={refreshing}
            className="prism-button border-blue-500/30 text-white hover:bg-blue-500/20"
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${refreshing ? "animate-spin" : ""}`} />
            刷新数据
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="prism-button border-blue-500/30 text-white hover:bg-blue-500/20"
          >
            <Download className="h-4 w-4 mr-2" />
            导出报告
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="prism-button border-blue-500/30 text-white hover:bg-blue-500/20"
          >
            <Maximize2 className="h-4 w-4 mr-2" />
            全屏模式
          </Button>
        </div>
      </div>

      {/* Key Metrics Grid */}
      <div className="data-grid">
        <ModernMetricCard
          title="系统健康度"
          value="98.5%"
          icon={Activity}
          trend="up"
          trendValue="+2.1%"
          color="green"
          description="所有核心系统正常运行"
          delay={0.1}
        />
        <ModernMetricCard
          title="活跃服务"
          value="6/6"
          icon={Server}
          trend="stable"
          color="blue"
          description="全部微服务在线运行"
          delay={0.2}
        />
        <ModernMetricCard
          title="实时连接"
          value="1,247"
          icon={Users}
          trend="up"
          trendValue="+156"
          color="cyan"
          description="WebSocket活跃连接数"
          delay={0.3}
        />
        <ModernMetricCard
          title="活跃告警"
          value="3"
          icon={AlertTriangle}
          trend="down"
          trendValue="-2"
          color="orange"
          description="2个警告，1个信息提示"
          delay={0.4}
        />
      </div>

      {/* System Resources & Service Status */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
        {/* System Resources */}
        <Card className="prism-card data-visualization smooth-enter">
          <CardHeader className="pb-6">
            <CardTitle className="text-white flex items-center text-xl">
              <div className="p-2 bg-blue-500/20 rounded-lg mr-4">
                <Cpu className="h-6 w-6 text-blue-400" />
              </div>
              系统资源监控
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-8">
            <div className="space-y-6">
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-blue-200/90">CPU使用率</span>
                  <span className="text-sm font-mono text-white bg-blue-500/20 px-2 py-1 rounded">45.2%</span>
                </div>
                <Progress value={45.2} className="h-3 bg-blue-900/30" />
                <div className="flex justify-between text-xs text-blue-300/60">
                  <span>4核心 @ 2.4 GHz</span>
                  <span>温度: 65°C</span>
                </div>
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-blue-200/90">内存使用</span>
                  <span className="text-sm font-mono text-white bg-cyan-500/20 px-2 py-1 rounded">67.8%</span>
                </div>
                <Progress value={67.8} className="h-3 bg-cyan-900/30" />
                <div className="flex justify-between text-xs text-blue-300/60">
                  <span>10.8GB / 16GB</span>
                  <span>缓存: 2.1GB</span>
                </div>
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-blue-200/90">磁盘使用</span>
                  <span className="text-sm font-mono text-white bg-green-500/20 px-2 py-1 rounded">34.5%</span>
                </div>
                <Progress value={34.5} className="h-3 bg-green-900/30" />
                <div className="flex justify-between text-xs text-blue-300/60">
                  <span>345GB / 1TB</span>
                  <span>I/O: 125MB/s</span>
                </div>
              </div>
            </div>
            <SystemChart />
          </CardContent>
        </Card>

        {/* Service Status */}
        <Card className="prism-card data-visualization smooth-enter">
          <CardHeader className="pb-6">
            <CardTitle className="text-white flex items-center text-xl">
              <div className="p-2 bg-cyan-500/20 rounded-lg mr-4">
                <Server className="h-6 w-6 text-cyan-400" />
              </div>
              服务状态监控
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ServiceStatus />
          </CardContent>
        </Card>
      </div>

      {/* Market Data Overview */}
      <Card className="prism-card data-visualization smooth-enter">
        <CardHeader className="pb-6">
          <CardTitle className="text-white flex items-center text-xl">
            <div className="p-2 bg-green-500/20 rounded-lg mr-4">
              <TrendingUp className="h-6 w-6 text-green-400" />
            </div>
            市场数据概览
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="data-grid">
            {[
              { symbol: "BTC/USDT", price: "43,256.78", change: "+2.34%", volume: "1.2B", isUp: true },
              { symbol: "ETH/USDT", price: "2,678.90", change: "-1.23%", volume: "856M", isUp: false },
              { symbol: "BNB/USDT", price: "312.45", change: "+0.87%", volume: "234M", isUp: true },
              { symbol: "SOL/USDT", price: "98.76", change: "+5.21%", volume: "445M", isUp: true },
            ].map((coin, index) => (
              <div
                key={coin.symbol}
                className="modern-table-row p-6 rounded-xl group"
                style={{ animationDelay: `${index * 0.1}s` }}
              >
                <div className="flex items-center justify-between mb-4">
                  <span className="text-lg font-semibold text-white">{coin.symbol}</span>
                  <div className={`status-indicator ${coin.isUp ? "active" : ""}`}></div>
                </div>
                <div className="space-y-3">
                  <p className="text-2xl font-mono font-bold text-white">${coin.price}</p>
                  <p className={`text-lg font-mono font-semibold ${coin.isUp ? "price-up" : "price-down"}`}>
                    {coin.change}
                  </p>
                  <p className="text-sm text-blue-300/70">24h成交量: {coin.volume}</p>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Performance Monitor */}
      <PerformanceMonitor />

      {/* Real-time Data Stream */}
      <Card className="prism-card data-visualization smooth-enter">
        <CardHeader className="pb-6">
          <CardTitle className="text-white flex items-center text-xl">
            <div className="p-2 bg-purple-500/20 rounded-lg mr-4">
              <Database className="h-6 w-6 text-purple-400" />
            </div>
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
