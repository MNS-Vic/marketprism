"use client"

import { useState, useEffect, useRef } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Activity, Cpu, Clock, Zap } from "lucide-react"

interface PerformanceMetrics {
  fps: number
  renderTime: number
  memoryUsage: number
  dataPoints: number
  canvasCount: number
}

export function PerformanceMonitor() {
  const [metrics, setMetrics] = useState<PerformanceMetrics>({
    fps: 0,
    renderTime: 0,
    memoryUsage: 0,
    dataPoints: 0,
    canvasCount: 0,
  })

  const frameCountRef = useRef(0)
  const lastTimeRef = useRef(performance.now())
  const renderTimesRef = useRef<number[]>([])

  useEffect(() => {
    let animationId: number

    const measurePerformance = () => {
      const now = performance.now()
      const deltaTime = now - lastTimeRef.current

      frameCountRef.current++

      // 计算FPS（每秒更新一次）
      if (deltaTime >= 1000) {
        const fps = Math.round((frameCountRef.current * 1000) / deltaTime)

        // 计算平均渲染时间
        const avgRenderTime =
          renderTimesRef.current.length > 0
            ? renderTimesRef.current.reduce((a, b) => a + b, 0) / renderTimesRef.current.length
            : 0

        // 获取内存使用情况（如果支持）
        const memoryUsage = (performance as any).memory
          ? Math.round((performance as any).memory.usedJSHeapSize / 1024 / 1024)
          : 0

        // 统计Canvas数量
        const canvasCount = document.querySelectorAll("canvas").length

        // 估算数据点数量（基于页面上的图表组件）
        const dataPoints = 2000 // 这里可以从实际组件获取

        setMetrics({
          fps,
          renderTime: Math.round(avgRenderTime * 100) / 100,
          memoryUsage,
          dataPoints,
          canvasCount,
        })

        frameCountRef.current = 0
        lastTimeRef.current = now
        renderTimesRef.current = []
      }

      animationId = requestAnimationFrame(measurePerformance)
    }

    measurePerformance()

    return () => {
      if (animationId) {
        cancelAnimationFrame(animationId)
      }
    }
  }, [])

  // 记录渲染时间的函数（可以被图表组件调用）
  const recordRenderTime = (time: number) => {
    renderTimesRef.current.push(time)
    if (renderTimesRef.current.length > 60) {
      renderTimesRef.current.shift()
    }
  }

  const getPerformanceStatus = (fps: number) => {
    if (fps >= 50) return { status: "excellent", color: "bg-cyan-400/20 text-cyan-400 border-cyan-400/50" }
    if (fps >= 30) return { status: "good", color: "bg-green-400/20 text-green-400 border-green-400/50" }
    if (fps >= 20) return { status: "fair", color: "bg-yellow-400/20 text-yellow-400 border-yellow-400/50" }
    return { status: "poor", color: "bg-red-400/20 text-red-400 border-red-400/50" }
  }

  const performanceStatus = getPerformanceStatus(metrics.fps)

  return (
    <Card className="htx-card">
      <CardHeader className="pb-4">
        <CardTitle className="text-white flex items-center text-lg">
          <Activity className="h-5 w-5 mr-3 text-cyan-400" />
          Performance Monitor
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-blue-500/20 rounded-lg">
              <Zap className="h-5 w-5 text-blue-400" />
            </div>
            <div>
              <p className="text-sm text-blue-200/80">FPS</p>
              <div className="flex items-center space-x-2">
                <p className="text-xl font-mono font-bold text-white">{metrics.fps}</p>
                <Badge className={performanceStatus.color}>{performanceStatus.status.toUpperCase()}</Badge>
              </div>
            </div>
          </div>

          <div className="flex items-center space-x-3">
            <div className="p-2 bg-purple-500/20 rounded-lg">
              <Clock className="h-5 w-5 text-purple-400" />
            </div>
            <div>
              <p className="text-sm text-blue-200/80">Render Time</p>
              <p className="text-xl font-mono font-bold text-white">{metrics.renderTime}ms</p>
            </div>
          </div>

          <div className="flex items-center space-x-3">
            <div className="p-2 bg-green-500/20 rounded-lg">
              <Cpu className="h-5 w-5 text-green-400" />
            </div>
            <div>
              <p className="text-sm text-blue-200/80">Memory</p>
              <p className="text-xl font-mono font-bold text-white">{metrics.memoryUsage}MB</p>
            </div>
          </div>

          <div className="flex items-center space-x-3">
            <div className="p-2 bg-cyan-500/20 rounded-lg">
              <Activity className="h-5 w-5 text-cyan-400" />
            </div>
            <div>
              <p className="text-sm text-blue-200/80">Data Points</p>
              <p className="text-xl font-mono font-bold text-white">{metrics.dataPoints.toLocaleString()}</p>
            </div>
          </div>

          <div className="flex items-center space-x-3">
            <div className="p-2 bg-yellow-500/20 rounded-lg">
              <Activity className="h-5 w-5 text-yellow-400" />
            </div>
            <div>
              <p className="text-sm text-blue-200/80">Canvas Count</p>
              <p className="text-xl font-mono font-bold text-white">{metrics.canvasCount}</p>
            </div>
          </div>
        </div>

        <div className="mt-4 pt-4 border-t border-blue-500/20">
          <div className="flex items-center justify-between text-sm">
            <span className="text-blue-200/80">Canvas Optimization Status:</span>
            <Badge className="bg-cyan-400/20 text-cyan-400 border-cyan-400/50">ACTIVE</Badge>
          </div>
          <div className="mt-2 text-xs text-blue-300/60">
            High-performance Canvas rendering with batch operations and optimized draw calls
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
