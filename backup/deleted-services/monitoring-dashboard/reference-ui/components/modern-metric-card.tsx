"use client"

import { Card, CardContent } from "@/components/ui/card"
import { TrendingUp, TrendingDown, Minus, type LucideIcon } from "lucide-react"
import { cn } from "@/lib/utils"

interface ModernMetricCardProps {
  title: string
  value: string
  icon: LucideIcon
  trend?: "up" | "down" | "stable"
  trendValue?: string
  color: "blue" | "green" | "orange" | "red" | "cyan"
  description?: string
  delay?: number
}

export function ModernMetricCard({
  title,
  value,
  icon: Icon,
  trend,
  trendValue,
  color,
  description,
  delay = 0,
}: ModernMetricCardProps) {
  const colorClasses = {
    blue: "border-blue-400/30 bg-gradient-to-br from-blue-500/10 to-blue-600/5",
    green: "border-green-400/30 bg-gradient-to-br from-green-500/10 to-green-600/5",
    orange: "border-orange-400/30 bg-gradient-to-br from-orange-500/10 to-orange-600/5",
    red: "border-red-400/30 bg-gradient-to-br from-red-500/10 to-red-600/5",
    cyan: "border-cyan-400/30 bg-gradient-to-br from-cyan-500/10 to-cyan-600/5",
  }

  const iconColors = {
    blue: "text-blue-400",
    green: "text-green-400",
    orange: "text-orange-400",
    red: "text-red-400",
    cyan: "text-cyan-400",
  }

  const iconBgColors = {
    blue: "bg-blue-500/20",
    green: "bg-green-500/20",
    orange: "bg-orange-500/20",
    red: "bg-red-500/20",
    cyan: "bg-cyan-500/20",
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
        "prism-card border backdrop-blur-xl transition-all duration-500 hover:scale-[1.02] group smooth-enter data-visualization",
        colorClasses[color],
      )}
      style={{ animationDelay: `${delay}s` }}
    >
      <CardContent className="p-6">
        <div className="flex items-center justify-between mb-6">
          <div className={cn("p-3 rounded-xl transition-all duration-300 group-hover:scale-110", iconBgColors[color])}>
            <Icon className={cn("h-6 w-6", iconColors[color])} />
          </div>
          {trend && (
            <div className="flex items-center space-x-2 px-3 py-1 rounded-full bg-black/20 backdrop-blur-sm">
              {getTrendIcon()}
              {trendValue && (
                <span
                  className={cn(
                    "text-sm font-mono font-semibold",
                    trend === "up" ? "text-green-400" : trend === "down" ? "text-red-400" : "text-blue-300/60",
                  )}
                >
                  {trendValue}
                </span>
              )}
            </div>
          )}
        </div>

        <div className="space-y-3">
          <h3 className="text-sm font-medium text-blue-200/80 uppercase tracking-wider">{title}</h3>
          <p className="responsive-title font-bold text-white font-mono tracking-tight">{value}</p>
          {description && <p className="text-sm text-blue-300/70 leading-relaxed">{description}</p>}
        </div>

        {/* 数据流动效果 */}
        <div className="absolute bottom-0 left-0 right-0 h-1 bg-gradient-to-r from-transparent via-cyan-400/50 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
      </CardContent>
    </Card>
  )
}
