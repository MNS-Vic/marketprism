"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import {
  BarChart3,
  Monitor,
  Settings,
  TrendingUp,
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  Activity,
  Zap,
} from "lucide-react"

interface ModernSidebarProps {
  activeTab: string
  onTabChange: (tab: string) => void
}

export function ModernSidebar({ activeTab, onTabChange }: ModernSidebarProps) {
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
        "fixed left-0 top-0 h-screen glass-effect transition-all duration-500 ease-out z-40",
        collapsed ? "w-16" : "w-72",
      )}
    >
      {/* Header */}
      <div className="h-16 border-b border-blue-500/20 flex items-center justify-between px-4">
        {!collapsed && (
          <div className="flex items-center space-x-3 smooth-enter">
            {/* 现代棱镜Logo */}
            <div className="relative">
              <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-cyan-400 rounded-lg flex items-center justify-center">
                <div className="w-6 h-6 bg-white/20 rounded transform rotate-45"></div>
              </div>
              <div className="absolute -top-1 -right-1 w-3 h-3 bg-cyan-400 rounded-full animate-pulse"></div>
            </div>
            <div>
              <h1 className="text-lg font-bold text-white">市场棱镜</h1>
              <p className="text-xs text-blue-300/70 font-medium">MarketPrism</p>
            </div>
          </div>
        )}
        {collapsed && (
          <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-cyan-400 rounded-lg flex items-center justify-center mx-auto">
            <div className="w-6 h-6 bg-white/20 rounded transform rotate-45"></div>
          </div>
        )}
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setCollapsed(!collapsed)}
          className="text-blue-300 hover:text-white hover:bg-blue-500/20 h-8 w-8 transition-all duration-300"
        >
          {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </Button>
      </div>

      {/* Navigation */}
      <nav className="p-4 space-y-2">
        {menuItems.map((item, index) => {
          const Icon = item.icon
          const isActive = activeTab === item.id

          return (
            <Button
              key={item.id}
              variant="ghost"
              className={cn(
                "w-full justify-start h-14 text-left font-medium transition-all duration-300 group",
                collapsed ? "px-2" : "px-4",
                isActive
                  ? "bg-gradient-to-r from-blue-500/20 to-cyan-400/20 text-white border-r-2 border-cyan-400 shadow-lg"
                  : "text-blue-200/80 hover:text-white hover:bg-blue-500/10",
                "smooth-enter",
              )}
              style={{ animationDelay: `${index * 0.1}s` }}
              onClick={() => onTabChange(item.id)}
            >
              <Icon
                className={cn(
                  "h-5 w-5 transition-all duration-300",
                  collapsed ? "mx-auto" : "mr-3",
                  isActive ? "text-cyan-400" : "group-hover:text-cyan-300",
                )}
              />
              {!collapsed && (
                <>
                  <div className="flex-1">
                    <span className="block font-semibold">{item.label}</span>
                    <span className="text-xs text-blue-300/60 block">{item.description}</span>
                  </div>
                  {item.badge && (
                    <Badge className="bg-red-500/20 text-red-400 border-red-500/50 text-xs px-2 py-1 animate-pulse">
                      {item.badge}
                    </Badge>
                  )}
                </>
              )}
            </Button>
          )
        })}
      </nav>

      {/* 实时状态指示器 */}
      {!collapsed && (
        <div className="absolute bottom-24 left-4 right-4 p-4 glass-effect rounded-xl border border-blue-500/30 smooth-enter">
          <div className="flex items-center space-x-3 mb-3">
            <div className="status-indicator active"></div>
            <span className="text-sm text-white font-medium">实时数据流</span>
            <Zap className="h-4 w-4 text-cyan-400" />
          </div>
          <div className="space-y-2 text-xs text-blue-300/70">
            <div className="flex items-center justify-between">
              <span>延迟</span>
              <span className="font-mono text-cyan-400">12ms</span>
            </div>
            <div className="flex items-center justify-between">
              <span>数据点</span>
              <span className="font-mono text-white">{Math.floor(Math.random() * 1000 + 5000).toLocaleString()}</span>
            </div>
            <div className="w-full bg-blue-900/30 rounded-full h-1 overflow-hidden">
              <div className="h-full bg-gradient-to-r from-cyan-400 to-blue-500 data-flow"></div>
            </div>
          </div>
        </div>
      )}

      {/* User Profile */}
      {!collapsed && (
        <div className="absolute bottom-4 left-4 right-4 flex items-center space-x-3 p-3 glass-effect rounded-xl border border-blue-500/30 smooth-enter">
          <Avatar className="h-10 w-10 ring-2 ring-cyan-400/50">
            <AvatarFallback className="bg-gradient-to-br from-blue-500 to-cyan-400 text-white text-sm font-bold">
              MP
            </AvatarFallback>
          </Avatar>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-white truncate">量化分析师</p>
            <div className="flex items-center space-x-2">
              <div className="status-indicator active"></div>
              <p className="text-xs text-blue-300/70">在线分析中</p>
              <Activity className="h-3 w-3 text-cyan-400" />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
