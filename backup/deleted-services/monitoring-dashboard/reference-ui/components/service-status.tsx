"use client"

import { Badge } from "@/components/ui/badge"
import { CheckCircle, AlertCircle, XCircle, Activity } from "lucide-react"

export function ServiceStatus() {
  const services = [
    {
      name: "API Gateway",
      port: "8080",
      status: "healthy",
      responseTime: "12ms",
      uptime: "99.9%",
      requests: "1.2K/min",
    },
    {
      name: "Data Collector",
      port: "8081",
      status: "healthy",
      responseTime: "8ms",
      uptime: "99.8%",
      requests: "856/min",
    },
    {
      name: "Data Storage",
      port: "8082",
      status: "warning",
      responseTime: "45ms",
      uptime: "99.5%",
      requests: "234/min",
    },
    {
      name: "Monitoring",
      port: "8083",
      status: "healthy",
      responseTime: "15ms",
      uptime: "100%",
      requests: "45/min",
    },
    {
      name: "Scheduler",
      port: "8084",
      status: "healthy",
      responseTime: "6ms",
      uptime: "99.9%",
      requests: "12/min",
    },
    {
      name: "Message Broker",
      port: "8085",
      status: "healthy",
      responseTime: "3ms",
      uptime: "99.9%",
      requests: "678/min",
    },
  ]

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "healthy":
        return <CheckCircle className="h-4 w-4 text-cyan-400" />
      case "warning":
        return <AlertCircle className="h-4 w-4 text-yellow-400" />
      case "error":
        return <XCircle className="h-4 w-4 text-red-400" />
      default:
        return <CheckCircle className="h-4 w-4 text-cyan-400" />
    }
  }

  const getStatusBadge = (status: string) => {
    const variants = {
      healthy: "bg-cyan-400/20 text-cyan-400 border-cyan-400/50",
      warning: "bg-yellow-400/20 text-yellow-400 border-yellow-400/50",
      error: "bg-red-400/20 text-red-400 border-red-400/50",
    }

    return (
      <Badge className={variants[status as keyof typeof variants] || variants.healthy}>
        {status === "healthy" ? "ONLINE" : status === "warning" ? "WARNING" : "ERROR"}
      </Badge>
    )
  }

  return (
    <div className="space-y-2">
      {services.map((service, index) => (
        <div
          key={service.name}
          className={`flex items-center justify-between p-4 rounded-lg border border-blue-500/20 hover:bg-blue-500/10 transition-colors htx-table-row ${
            index % 2 === 0 ? "bg-blue-900/10" : "bg-transparent"
          }`}
        >
          <div className="flex items-center space-x-3">
            {getStatusIcon(service.status)}
            <div>
              <p className="text-sm font-medium text-white">{service.name}</p>
              <div className="flex items-center space-x-2 text-xs text-blue-300/60">
                <span>Port: {service.port}</span>
                <span>•</span>
                <span className="flex items-center">
                  <Activity className="h-3 w-3 mr-1" />
                  {service.requests}
                </span>
              </div>
            </div>
          </div>
          <div className="flex items-center space-x-4">
            <div className="text-right">
              <p className="text-xs text-blue-300/60">Response</p>
              <p className="text-sm font-mono text-white">{service.responseTime}</p>
            </div>
            <div className="text-right">
              <p className="text-xs text-blue-300/60">Uptime</p>
              <p className="text-sm font-mono text-white">{service.uptime}</p>
            </div>
            {getStatusBadge(service.status)}
          </div>
        </div>
      ))}
    </div>
  )
}
