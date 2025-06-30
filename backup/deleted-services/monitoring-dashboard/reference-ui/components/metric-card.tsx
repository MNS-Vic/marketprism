"use client"

import { Card, CardContent } from "@/components/ui/card"
import { TrendingUp, TrendingDown, Minus, type LucideIcon } from "lucide-react"
import { cn } from "@/lib/utils"

interface MetricCardProps {
  title: string
  value: string
  icon: LucideIcon
  trend?: "up" | "down" | "stable"
  trendValue?: string
  color: "blue" | "green" | "orange" | "red" | "cyan"
  description?: string
}

export function MetricCard({ title, value, icon: Icon, trend, trendValue, color, description }: MetricCardProps) {
  const colorClasses = {
    blue: "border-blue-400/30",
    green: "border-green-400/30",
    orange: "border-orange-400/30",
    red: "border-red-400/30",
    cyan: "border-cyan-400/30",
  }

  const iconColors = {
    blue: "text-blue-400",
    green: "text-green-400",
    orange: "text-orange-400",
    red: "text-red-400",
    cyan: "text-cyan-400",
  }

  const getTrendIcon = () => {
    switch (trend) {
      case "up":
        return <TrendingUp className="h-4 w-4 text-green-400" />
      case "down":
        return <TrendingDown className="h-4 w-4 text-red-400" />
      default:
        return <Minus className="h-4 w-4 text-blue-300/60" />
    }
  }

  return (
    <Card
      className={cn(
        "bg-slate-800/50 border backdrop-blur-sm transition-all duration-300 hover:scale-[1.02]",
        colorClasses[color],
      )}
    >
      <CardContent className="p-6">
        <div className="flex items-center justify-between mb-4">
          <Icon className={cn("h-8 w-8", iconColors[color])} />
          {trend && (
            <div className="flex items-center space-x-1">
              {getTrendIcon()}
              {trendValue && (
                <span
                  className={cn(
                    "text-sm font-mono font-medium",
                    trend === "up" ? "text-green-400" : trend === "down" ? "text-red-400" : "text-blue-300/60",
                  )}
                >
                  {trendValue}
                </span>
              )}
            </div>
          )}
        </div>
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-blue-200/80 uppercase tracking-wide">{title}</h3>
          <p className="text-3xl font-bold text-white font-mono">{value}</p>
          {description && <p className="text-xs text-blue-300/60">{description}</p>}
        </div>
      </CardContent>
    </Card>
  )
}
