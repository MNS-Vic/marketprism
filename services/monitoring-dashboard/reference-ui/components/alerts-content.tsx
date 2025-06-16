"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { ScrollArea } from "@/components/ui/scroll-area"
import { AlertTriangle, CheckCircle, XCircle, Clock, Bell, Search, Activity } from "lucide-react"

export function AlertsContent() {
  const [alerts, setAlerts] = useState<Array<any>>([])
  const [alertRules, setAlertRules] = useState<Array<any>>([])
  const [filterLevel, setFilterLevel] = useState("all")
  const [filterStatus, setFilterStatus] = useState("all")
  const [searchTerm, setSearchTerm] = useState("")

  // 模拟告警数据
  useEffect(() => {
    const initialAlerts = [
      {
        id: 1,
        level: "critical",
        title: "API Gateway Response Time Critical",
        description: "API Gateway average response time exceeded 1000ms threshold for 5 minutes",
        source: "API Gateway (8080)",
        category: "performance",
        time: new Date(Date.now() - 300000).toISOString(),
        status: "active",
        count: 1,
        acknowledged: false,
        assignee: null,
      },
      {
        id: 2,
        level: "warning",
        title: "High Memory Usage Detected",
        description: "System memory usage reached 85% on production server",
        source: "System Monitor",
        category: "resource",
        time: new Date(Date.now() - 600000).toISOString(),
        status: "active",
        count: 3,
        acknowledged: true,
        assignee: "admin",
      },
      {
        id: 3,
        level: "warning",
        title: "HTX API Rate Limit Warning",
        description: "HTX API usage reached 90% of rate limit",
        source: "Trading Engine",
        category: "trading",
        time: new Date(Date.now() - 900000).toISOString(),
        status: "active",
        count: 1,
        acknowledged: false,
        assignee: null,
      },
    ]

    setAlerts(initialAlerts)

    // 模拟实时告警
    const interval = setInterval(() => {
      if (Math.random() > 0.8) {
        const newAlert = {
          id: Date.now(),
          level: ["warning", "info", "critical"][Math.floor(Math.random() * 3)],
          title: [
            "WebSocket Connection Unstable",
            "Disk Space Warning",
            "High Network Latency",
            "Service Health Check Failed",
          ][Math.floor(Math.random() * 4)],
          description: "Automated system alert generated",
          source: ["API Gateway", "Data Collector", "Trading Engine"][Math.floor(Math.random() * 3)],
          category: ["system", "network", "trading"][Math.floor(Math.random() * 3)],
          time: new Date().toISOString(),
          status: "active",
          count: 1,
          acknowledged: false,
          assignee: null,
        }
        setAlerts((prev) => [newAlert, ...prev.slice(0, 19)])
      }
    }, 15000)

    return () => clearInterval(interval)
  }, [])

  const alertStats = {
    critical: alerts.filter((a) => a.level === "critical" && a.status === "active").length,
    warning: alerts.filter((a) => a.level === "warning" && a.status === "active").length,
    info: alerts.filter((a) => a.level === "info" && a.status === "active").length,
    total: alerts.filter((a) => a.status === "active").length,
    resolved: alerts.filter((a) => a.status === "resolved").length,
  }

  const getAlertIcon = (level: string) => {
    switch (level) {
      case "critical":
        return <XCircle className="h-5 w-5 text-red-400" />
      case "warning":
        return <AlertTriangle className="h-5 w-5 text-yellow-400" />
      case "info":
        return <Bell className="h-5 w-5 text-blue-400" />
      default:
        return <AlertTriangle className="h-5 w-5 text-yellow-400" />
    }
  }

  const getAlertBadge = (level: string) => {
    const variants = {
      critical: "bg-red-400/20 text-red-400 border-red-400/50",
      warning: "bg-yellow-400/20 text-yellow-400 border-yellow-400/50",
      info: "bg-blue-400/20 text-blue-400 border-blue-400/50",
    }

    const labels = {
      critical: "CRITICAL",
      warning: "WARNING",
      info: "INFO",
    }

    return (
      <Badge className={variants[level as keyof typeof variants] || variants.warning}>
        {labels[level as keyof typeof labels] || "UNKNOWN"}
      </Badge>
    )
  }

  const handleAcknowledge = (alertId: number) => {
    setAlerts((prev) =>
      prev.map((alert) =>
        alert.id === alertId ? { ...alert, acknowledged: true, status: "acknowledged", assignee: "admin" } : alert,
      ),
    )
  }

  const handleResolve = (alertId: number) => {
    setAlerts((prev) =>
      prev.map((alert) => (alert.id === alertId ? { ...alert, status: "resolved", acknowledged: true } : alert)),
    )
  }

  const filteredAlerts = alerts.filter((alert) => {
    const matchesLevel = filterLevel === "all" || alert.level === filterLevel
    const matchesStatus = filterStatus === "all" || alert.status === filterStatus
    const matchesSearch =
      searchTerm === "" ||
      alert.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
      alert.description.toLowerCase().includes(searchTerm.toLowerCase()) ||
      alert.source.toLowerCase().includes(searchTerm.toLowerCase())

    return matchesLevel && matchesStatus && matchesSearch
  })

  return (
    <div className="p-6 space-y-6 min-h-screen">
      <div>
        <h1 className="text-3xl font-bold text-white mb-1">Alert Management</h1>
        <p className="text-blue-200/70">Monitor and manage system alerts and notifications</p>
      </div>

      {/* Alert Statistics */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
        <Card className="htx-card border-l-4 border-l-red-400">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-blue-200/80 uppercase tracking-wide">Critical</p>
                <p className="text-2xl font-bold text-red-400 font-mono">{alertStats.critical}</p>
              </div>
              <XCircle className="h-8 w-8 text-red-400" />
            </div>
          </CardContent>
        </Card>

        <Card className="htx-card border-l-4 border-l-yellow-400">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-blue-200/80 uppercase tracking-wide">Warning</p>
                <p className="text-2xl font-bold text-yellow-400 font-mono">{alertStats.warning}</p>
              </div>
              <AlertTriangle className="h-8 w-8 text-yellow-400" />
            </div>
          </CardContent>
        </Card>

        <Card className="htx-card border-l-4 border-l-blue-400">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-blue-200/80 uppercase tracking-wide">Info</p>
                <p className="text-2xl font-bold text-blue-400 font-mono">{alertStats.info}</p>
              </div>
              <Bell className="h-8 w-8 text-blue-400" />
            </div>
          </CardContent>
        </Card>

        <Card className="htx-card border-l-4 border-l-cyan-400">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-blue-200/80 uppercase tracking-wide">Active</p>
                <p className="text-2xl font-bold text-cyan-400 font-mono">{alertStats.total}</p>
              </div>
              <Activity className="h-8 w-8 text-cyan-400" />
            </div>
          </CardContent>
        </Card>

        <Card className="htx-card border-l-4 border-l-green-400">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-blue-200/80 uppercase tracking-wide">Resolved</p>
                <p className="text-2xl font-bold text-green-400 font-mono">{alertStats.resolved}</p>
              </div>
              <CheckCircle className="h-8 w-8 text-green-400" />
            </div>
          </CardContent>
        </Card>
      </div>

      <Card className="htx-card">
        <CardHeader className="pb-4">
          <div className="flex items-center justify-between">
            <CardTitle className="text-white flex items-center text-lg">
              <AlertTriangle className="h-5 w-5 mr-3 text-yellow-400" />
              Alert Dashboard
            </CardTitle>
            <div className="flex items-center space-x-3">
              <div className="flex items-center space-x-2">
                <Search className="h-4 w-4 text-blue-300" />
                <Input
                  placeholder="Search alerts..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-64 bg-blue-900/30 border-blue-500/30 text-white placeholder:text-blue-300/60"
                />
              </div>
              <Select value={filterLevel} onValueChange={setFilterLevel}>
                <SelectTrigger className="w-32 bg-blue-900/30 border-blue-500/30 text-white">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-blue-900 border-blue-500/30">
                  <SelectItem value="all">All Levels</SelectItem>
                  <SelectItem value="critical">Critical</SelectItem>
                  <SelectItem value="warning">Warning</SelectItem>
                  <SelectItem value="info">Info</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-96">
            <div className="space-y-3">
              {filteredAlerts.map((alert, index) => (
                <div
                  key={alert.id}
                  className={`p-4 rounded-lg border border-blue-500/20 hover:bg-blue-500/10 transition-colors htx-table-row ${
                    index % 2 === 0 ? "bg-blue-900/10" : "bg-transparent"
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-start space-x-3 flex-1">
                      {getAlertIcon(alert.level)}
                      <div className="flex-1">
                        <div className="flex items-center space-x-2 mb-2">
                          <h3 className="font-medium text-white">{alert.title}</h3>
                          {getAlertBadge(alert.level)}
                          {alert.count > 1 && (
                            <Badge className="bg-blue-400/20 text-blue-400 border-blue-400/50">x{alert.count}</Badge>
                          )}
                        </div>
                        <p className="text-sm text-blue-200/80 mb-3">{alert.description}</p>
                        <div className="flex items-center space-x-4 text-xs text-blue-300/60">
                          <span>{alert.source}</span>
                          <span className="flex items-center space-x-1">
                            <Clock className="h-3 w-3" />
                            <span>{new Date(alert.time).toLocaleString()}</span>
                          </span>
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center space-x-2 ml-4">
                      {!alert.acknowledged && alert.status === "active" && (
                        <Button size="sm" onClick={() => handleAcknowledge(alert.id)} className="htx-button text-sm">
                          Acknowledge
                        </Button>
                      )}
                      {alert.status !== "resolved" && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleResolve(alert.id)}
                          className="border-cyan-400/50 text-cyan-400 hover:bg-cyan-400/20"
                        >
                          Resolve
                        </Button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  )
}
