"use client"

import { useState } from "react"
import { ModernSidebar } from "@/components/modern-sidebar"
import { ModernDashboardContent } from "@/components/modern-dashboard-content"
import { SystemContent } from "@/components/system-content"
import { ServicesContent } from "@/components/services-content"
import { TradingContent } from "@/components/trading-content"
import { AlertsContent } from "@/components/alerts-content"

export default function MarketPrismDashboard() {
  const [activeTab, setActiveTab] = useState("dashboard")

  const renderContent = () => {
    switch (activeTab) {
      case "dashboard":
        return <ModernDashboardContent />
      case "system":
        return <SystemContent />
      case "services":
        return <ServicesContent />
      case "trading":
        return <TradingContent />
      case "alerts":
        return <AlertsContent />
      default:
        return <ModernDashboardContent />
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-blue-900/20 to-slate-900">
      <div className="flex">
        <ModernSidebar activeTab={activeTab} onTabChange={setActiveTab} />
        <main className="flex-1 ml-72 transition-all duration-500">{renderContent()}</main>
      </div>
    </div>
  )
}
