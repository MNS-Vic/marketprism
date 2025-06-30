"use client"

import { useEffect, useState } from "react"
import { ResponsiveContainer, XAxis, YAxis, Tooltip, Area, AreaChart } from "recharts"

export function SystemChart() {
  const [data, setData] = useState<Array<{ time: string; cpu: number; memory: number }>>([])

  useEffect(() => {
    const generateData = () => {
      const now = new Date()
      const newData = []

      for (let i = 29; i >= 0; i--) {
        const time = new Date(now.getTime() - i * 60000)
        newData.push({
          time: time.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" }),
          cpu: Math.random() * 30 + 20,
          memory: Math.random() * 20 + 60,
        })
      }

      setData(newData)
    }

    generateData()
    const interval = setInterval(generateData, 5000)

    return () => clearInterval(interval)
  }, [])

  return (
    <div className="h-48">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data}>
          <defs>
            <linearGradient id="cpuGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#2E7CF6" stopOpacity={0.4} />
              <stop offset="95%" stopColor="#2E7CF6" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="memoryGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#00D4AA" stopOpacity={0.4} />
              <stop offset="95%" stopColor="#00D4AA" stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="time"
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#8B9DC3", fontSize: 11 }}
            interval="preserveStartEnd"
          />
          <YAxis axisLine={false} tickLine={false} tick={{ fill: "#8B9DC3", fontSize: 11 }} domain={[0, 100]} />
          <Tooltip
            contentStyle={{
              backgroundColor: "#1B2B4D",
              border: "1px solid #2E7CF6",
              borderRadius: "8px",
              color: "#ffffff",
            }}
          />
          <Area type="monotone" dataKey="cpu" stroke="#2E7CF6" strokeWidth={2} fill="url(#cpuGradient)" name="CPU %" />
          <Area
            type="monotone"
            dataKey="memory"
            stroke="#00D4AA"
            strokeWidth={2}
            fill="url(#memoryGradient)"
            name="Memory %"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
