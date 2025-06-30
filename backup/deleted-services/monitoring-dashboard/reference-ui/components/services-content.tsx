"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { Server, Wifi, Activity, AlertTriangle, CheckCircle, Play, Square, RotateCcw } from "lucide-react"

export function ServicesContent() {
  const services = [
    {
      name: "API Gateway",
      port: "8080",
      status: "healthy",
      cpu: "15.2%",
      memory: "256MB",
      requests: "1,247/min",
      uptime: "99.9%",
      description: "主要API网关服务",
    },
    {
      name: "Data Collector",
      port: "8081",
      status: "healthy",
      cpu: "8.7%",
      memory: "128MB",
      requests: "856/min",
      uptime: "99.8%",
      description: "数据收集服务",
    },
    {
      name: "Data Storage",
      port: "8082",
      status: "warning",
      cpu: "12.4%",
      memory: "512MB",
      requests: "234/min",
      uptime: "99.5%",
      description: "数据存储服务",
    },
    {
      name: "Monitoring",
      port: "8083",
      status: "healthy",
      cpu: "3.1%",
      memory: "64MB",
      requests: "45/min",
      uptime: "100%",
      description: "监控服务",
    },
    {
      name: "Scheduler",
      port: "8084",
      status: "healthy",
      cpu: "2.8%",
      memory: "48MB",
      requests: "12/min",
      uptime: "99.9%",
      description: "任务调度服务",
    },
    {
      name: "Message Broker",
      port: "8085",
      status: "healthy",
      cpu: "5.4%",
      memory: "96MB",
      requests: "678/min",
      uptime: "99.9%",
      description: "消息代理服务",
    },
  ]

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "healthy":
        return <CheckCircle className="h-5 w-5 text-green-400" />
      case "warning":
        return <AlertTriangle className="h-5 w-5 text-yellow-400" />
      case "error":
        return <AlertTriangle className="h-5 w-5 text-red-400" />
      default:
        return <CheckCircle className="h-5 w-5 text-green-400" />
    }
  }

  const getStatusBadge = (status: string) => {
    const variants = {
      healthy: "bg-green-500/20 text-green-400 border-green-500/30",
      warning: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
      error: "bg-red-500/20 text-red-400 border-red-500/30",
    }

    return (
      <Badge className={variants[status as keyof typeof variants] || variants.healthy}>
        {status === "healthy" ? "正常" : status === "warning" ? "警告" : "错误"}
      </Badge>
    )
  }

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-white">服务监控</h1>
        <p className="text-slate-400 mt-1">微服务状态和性能监控</p>
      </div>

      {/* Service Overview */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card className="bg-gradient-to-br from-green-500/20 to-emerald-500/20 border-green-500/30">
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-slate-300">健康服务</p>
                <p className="text-3xl font-bold text-white">5</p>
              </div>
              <CheckCircle className="h-8 w-8 text-green-400" />
            </div>
          </CardContent>
        </Card>

        <Card className="bg-gradient-to-br from-yellow-500/20 to-orange-500/20 border-yellow-500/30">
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-slate-300">警告服务</p>
                <p className="text-3xl font-bold text-white">1</p>
              </div>
              <AlertTriangle className="h-8 w-8 text-yellow-400" />
            </div>
          </CardContent>
        </Card>

        <Card className="bg-gradient-to-br from-blue-500/20 to-cyan-500/20 border-blue-500/30">
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-slate-300">总请求数</p>
                <p className="text-3xl font-bold text-white">3,072</p>
              </div>
              <Activity className="h-8 w-8 text-blue-400" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Detailed Service Monitoring */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {services.map((service) => (
          <Card key={service.name} className="bg-slate-800/50 border-slate-700/50">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  {getStatusIcon(service.status)}
                  <div>
                    <CardTitle className="text-white text-lg">{service.name}</CardTitle>
                    <p className="text-sm text-slate-400">
                      端口: {service.port} • {service.description}
                    </p>
                  </div>
                </div>
                {getStatusBadge(service.status)}
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-xs text-slate-400 mb-1">CPU使用率</p>
                  <p className="text-sm font-medium text-white">{service.cpu}</p>
                  <Progress value={Number.parseFloat(service.cpu)} className="h-1 mt-1" />
                </div>
                <div>
                  <p className="text-xs text-slate-400 mb-1">内存使用</p>
                  <p className="text-sm font-medium text-white">{service.memory}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-400 mb-1">请求频率</p>
                  <p className="text-sm font-medium text-white">{service.requests}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-400 mb-1">可用性</p>
                  <p className="text-sm font-medium text-white">{service.uptime}</p>
                </div>
              </div>

              <div className="flex items-center space-x-2 pt-2 border-t border-slate-700">
                <Button size="sm" variant="outline" className="border-slate-600 text-slate-300 hover:bg-slate-700">
                  <Play className="h-3 w-3 mr-1" />
                  启动
                </Button>
                <Button size="sm" variant="outline" className="border-slate-600 text-slate-300 hover:bg-slate-700">
                  <Square className="h-3 w-3 mr-1" />
                  停止
                </Button>
                <Button size="sm" variant="outline" className="border-slate-600 text-slate-300 hover:bg-slate-700">
                  <RotateCcw className="h-3 w-3 mr-1" />
                  重启
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Service Dependencies */}
      <Card className="bg-slate-800/50 border-slate-700/50">
        <CardHeader>
          <CardTitle className="text-white flex items-center">
            <Wifi className="h-5 w-5 mr-2 text-purple-400" />
            服务依赖关系
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-64 flex items-center justify-center text-slate-400">
            <div className="text-center">
              <Server className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>服务拓扑图</p>
              <p className="text-sm mt-2">可视化显示服务间依赖关系</p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
