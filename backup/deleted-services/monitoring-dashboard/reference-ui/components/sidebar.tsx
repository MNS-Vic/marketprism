"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { BarChart3, Monitor, Settings, TrendingUp, AlertTriangle, Clock, ChevronLeft, ChevronRight } from "lucide-react"
import { PrismLogo } from "@/components/prism-logo"

interface SidebarProps {
  activeTab: string
  onTabChange: (tab: string) => void
}

export function Sidebar({ activeTab, onTabChange }: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false)

  const menuItems = [
    {
      id: "dashboard",
      label: "Dashboard",
      icon: BarChart3,
      badge: null,
      description: "数据总览",
    },
    {
      id: "system",
      label: "System",
      icon: Monitor,
      badge: null,
      description: "系统监控",
    },
    {
      id: "services",
      label: "Services",
      icon: Settings,
      badge: "6",
      description: "服务状态",
    },
    {
      id: "trading",
      label: "Trading",
      icon: TrendingUp,
      badge: null,
      description: "交易分析",
    },
    {
      id: "alerts",
      label: "Alerts",
      icon: AlertTriangle,
      badge: "3",
      description: "告警管理",
    },
  ]

  return (
    <div
      className={cn(
        "fixed left-0 top-0 h-screen bg-slate-900/95 border-r border-blue-500/20 transition-all duration-300 z-40 backdrop-blur-sm",
        collapsed ? "w-16" : "w-64",
      )}
    >
      {/* Header */}
      <div className="h-16 border-b border-blue-500/20 flex items-center justify-between px-4">
        {!collapsed && <PrismLogo size="sm" showText={true} />}
        {collapsed && <PrismLogo size="sm" showText={false} />}
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setCollapsed(!collapsed)}
          className="text-blue-300 hover:text-white hover:bg-blue-500/20 h-8 w-8"
        >
          {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </Button>
      </div>

      {/* Navigation */}
      <nav className="p-3 space-y-1">
        {menuItems.map((item) => {
          const Icon = item.icon
          const isActive = activeTab === item.id

          return (
            <Button
              key={item.id}
              variant="ghost"
              className={cn(
                "w-full justify-start h-12 text-left font-medium transition-all",
                collapsed ? "px-2" : "px-3",
                isActive
                  ? "bg-blue-500/20 text-white border-r-2 border-blue-400"
                  : "text-blue-200/80 hover:text-white hover:bg-blue-500/10",
              )}
              onClick={() => onTabChange(item.id)}
            >
              <Icon className={cn("h-5 w-5", collapsed ? "mx-auto" : "mr-3")} />
              {!collapsed && (
                <>
                  <div className="flex-1">
                    <span className="block">{item.label}</span>
                    <span className="text-xs text-blue-300/60 block">{item.description}</span>
                  </div>
                  {item.badge && (
                    <Badge className="bg-red-500/20 text-red-400 border-red-500/50 text-xs px-1.5 py-0.5">
                      {item.badge}
                    </Badge>
                  )}
                </>
              )}
            </Button>
          )
        })}
      </nav>

      {/* 数据流状态 */}
      {!collapsed && (
        <div className="absolute bottom-20 left-3 right-3 p-3 bg-blue-900/30 border border-blue-500/30 rounded-lg backdrop-blur-sm">
          <div className="flex items-center space-x-2 mb-2">
            <div className="status-dot bg-blue-400 animate-pulse"></div>
            <span className="text-sm text-blue-200 font-medium">数据流实时同步</span>
          </div>
          <div className="flex items-center space-x-2 text-xs text-blue-300/70">
            <Clock className="h-3 w-3" />
            <span>更新时间: {new Date().toLocaleTimeString()}</span>
          </div>
          <div className="mt-2 text-xs text-blue-300/80">
            正在处理 {Math.floor(Math.random() * 1000 + 5000).toLocaleString()} 个数据点
          </div>
        </div>
      )}

      {/* User Info */}
      {!collapsed && (
        <div className="absolute bottom-3 left-3 right-3 flex items-center space-x-3 p-3 bg-blue-900/30 border border-blue-500/30 rounded-lg backdrop-blur-sm">
          <Avatar className="h-8 w-8">
            <AvatarFallback className="bg-blue-500 text-white text-sm font-bold">MP</AvatarFallback>
          </Avatar>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-white truncate">数据分析师</p>
            <div className="flex items-center space-x-1">
              <div className="status-dot bg-green-400"></div>
              <p className="text-xs text-blue-300/70">在线分析中</p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
