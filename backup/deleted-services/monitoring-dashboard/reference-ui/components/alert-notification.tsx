"use client"

import { useState, useEffect } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { X, AlertTriangle, Bell } from "lucide-react"
import { cn } from "@/lib/utils"

interface AlertNotificationProps {
  alert: {
    id: number
    level: string
    title: string
    description: string
    time: string
  }
  onDismiss: (id: number) => void
  onAcknowledge: (id: number) => void
}

export function AlertNotification({ alert, onDismiss, onAcknowledge }: AlertNotificationProps) {
  const [isVisible, setIsVisible] = useState(true)

  useEffect(() => {
    // 自动消失（除了critical级别）
    if (alert.level !== "critical") {
      const timer = setTimeout(() => {
        setIsVisible(false)
        setTimeout(() => onDismiss(alert.id), 300)
      }, 8000)

      return () => clearTimeout(timer)
    }
  }, [alert.id, alert.level, onDismiss])

  const getAlertStyles = (level: string) => {
    switch (level) {
      case "critical":
        return "border-l-red-500 bg-red-500/10"
      case "warning":
        return "border-l-yellow-500 bg-yellow-500/10"
      case "info":
        return "border-l-blue-500 bg-blue-500/10"
      default:
        return "border-l-yellow-500 bg-yellow-500/10"
    }
  }

  const getAlertIcon = (level: string) => {
    switch (level) {
      case "critical":
        return <AlertTriangle className="h-5 w-5 text-red-400" />
      case "warning":
        return <AlertTriangle className="h-5 w-5 text-yellow-400" />
      case "info":
        return <Bell className="h-5 w-5 text-blue-400" />
      default:
        return <AlertTriangle className="h-5 w-5 text-yellow-400" />
    }
  }

  if (!isVisible) return null

  return (
    <Card
      className={cn(
        "fixed top-4 right-4 w-96 z-50 border-l-4 transition-all duration-300 transform",
        getAlertStyles(alert.level),
        isVisible ? "translate-x-0 opacity-100" : "translate-x-full opacity-0",
      )}
    >
      <CardContent className="p-4">
        <div className="flex items-start space-x-3">
          {getAlertIcon(alert.level)}
          <div className="flex-1">
            <div className="flex items-center justify-between mb-2">
              <h4 className="font-medium text-white">{alert.title}</h4>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setIsVisible(false)
                  setTimeout(() => onDismiss(alert.id), 300)
                }}
                className="h-6 w-6 p-0 text-zinc-400 hover:text-white"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
            <p className="text-sm text-zinc-300 mb-3">{alert.description}</p>
            <div className="flex items-center justify-between">
              <span className="text-xs text-zinc-500">{alert.time}</span>
              <div className="flex items-center space-x-2">
                <Badge className="bg-zinc-700 text-zinc-300 border-zinc-600">{alert.level.toUpperCase()}</Badge>
                <Button
                  size="sm"
                  onClick={() => onAcknowledge(alert.id)}
                  className="h-6 text-xs bg-yellow-500/20 text-yellow-400 hover:bg-yellow-500/30 border border-yellow-500/50"
                >
                  Acknowledge
                </Button>
              </div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
