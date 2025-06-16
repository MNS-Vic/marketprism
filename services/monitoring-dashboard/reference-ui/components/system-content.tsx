"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { Badge } from "@/components/ui/badge"
import { Cpu, HardDrive, Wifi, Thermometer, Activity, MemoryStick } from "lucide-react"

export function SystemContent() {
  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-white">系统监控</h1>
        <p className="text-slate-400 mt-1">详细的系统资源使用情况</p>
      </div>

      {/* System Overview */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="bg-slate-800/50 border-slate-700/50">
          <CardHeader>
            <CardTitle className="text-white flex items-center">
              <Cpu className="h-5 w-5 mr-2 text-blue-400" />
              CPU监控
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <p className="text-sm text-slate-300">核心1</p>
                <Progress value={45} className="h-2" />
                <p className="text-xs text-slate-400">45%</p>
              </div>
              <div className="space-y-2">
                <p className="text-sm text-slate-300">核心2</p>
                <Progress value={38} className="h-2" />
                <p className="text-xs text-slate-400">38%</p>
              </div>
              <div className="space-y-2">
                <p className="text-sm text-slate-300">核心3</p>
                <Progress value={52} className="h-2" />
                <p className="text-xs text-slate-400">52%</p>
              </div>
              <div className="space-y-2">
                <p className="text-sm text-slate-300">核心4</p>
                <Progress value={41} className="h-2" />
                <p className="text-xs text-slate-400">41%</p>
              </div>
            </div>
            <div className="pt-4 border-t border-slate-700">
              <div className="flex justify-between items-center">
                <span className="text-sm text-slate-300">平均负载</span>
                <span className="text-sm text-white">1.2, 1.5, 1.8</span>
              </div>
              <div className="flex justify-between items-center mt-2">
                <span className="text-sm text-slate-300">温度</span>
                <div className="flex items-center space-x-2">
                  <Thermometer className="h-4 w-4 text-orange-400" />
                  <span className="text-sm text-white">65°C</span>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="bg-slate-800/50 border-slate-700/50">
          <CardHeader>
            <CardTitle className="text-white flex items-center">
              <MemoryStick className="h-5 w-5 mr-2 text-purple-400" />
              内存监控
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <div className="flex justify-between mb-2">
                <span className="text-sm text-slate-300">已使用内存</span>
                <span className="text-sm text-white">10.8GB / 16GB</span>
              </div>
              <Progress value={67.5} className="h-3" />
            </div>
            <div>
              <div className="flex justify-between mb-2">
                <span className="text-sm text-slate-300">缓存</span>
                <span className="text-sm text-white">2.1GB</span>
              </div>
              <Progress value={13.1} className="h-2" />
            </div>
            <div>
              <div className="flex justify-between mb-2">
                <span className="text-sm text-slate-300">缓冲区</span>
                <span className="text-sm text-white">0.8GB</span>
              </div>
              <Progress value={5} className="h-2" />
            </div>
            <div className="pt-4 border-t border-slate-700">
              <div className="flex justify-between items-center">
                <span className="text-sm text-slate-300">交换分区</span>
                <Badge variant="outline" className="border-green-500/30 text-green-400">
                  未使用
                </Badge>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Storage and Network */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="bg-slate-800/50 border-slate-700/50">
          <CardHeader>
            <CardTitle className="text-white flex items-center">
              <HardDrive className="h-5 w-5 mr-2 text-green-400" />
              磁盘监控
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-3">
              <div>
                <div className="flex justify-between mb-2">
                  <span className="text-sm text-slate-300">/dev/sda1 (系统)</span>
                  <span className="text-sm text-white">345GB / 1TB</span>
                </div>
                <Progress value={34.5} className="h-2" />
              </div>
              <div>
                <div className="flex justify-between mb-2">
                  <span className="text-sm text-slate-300">/dev/sdb1 (数据)</span>
                  <span className="text-sm text-white">1.2TB / 2TB</span>
                </div>
                <Progress value={60} className="h-2" />
              </div>
            </div>
            <div className="pt-4 border-t border-slate-700 space-y-2">
              <div className="flex justify-between">
                <span className="text-sm text-slate-300">读取速度</span>
                <span className="text-sm text-white">125 MB/s</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-slate-300">写入速度</span>
                <span className="text-sm text-white">89 MB/s</span>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="bg-slate-800/50 border-slate-700/50">
          <CardHeader>
            <CardTitle className="text-white flex items-center">
              <Wifi className="h-5 w-5 mr-2 text-cyan-400" />
              网络监控
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-3">
              <div className="flex justify-between">
                <span className="text-sm text-slate-300">上行流量</span>
                <span className="text-sm text-white">45.2 MB/s</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-slate-300">下行流量</span>
                <span className="text-sm text-white">128.7 MB/s</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-slate-300">活跃连接</span>
                <span className="text-sm text-white">1,247</span>
              </div>
            </div>
            <div className="pt-4 border-t border-slate-700 space-y-2">
              <div className="flex justify-between">
                <span className="text-sm text-slate-300">平均延迟</span>
                <span className="text-sm text-white">12ms</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-slate-300">丢包率</span>
                <span className="text-sm text-green-400">0.01%</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Process Monitoring */}
      <Card className="bg-slate-800/50 border-slate-700/50">
        <CardHeader>
          <CardTitle className="text-white flex items-center">
            <Activity className="h-5 w-5 mr-2 text-yellow-400" />
            进程监控
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {[
              { pid: "1234", name: "market-prism-api", cpu: "15.2%", memory: "256MB", status: "运行中" },
              { pid: "1235", name: "data-collector", cpu: "8.7%", memory: "128MB", status: "运行中" },
              { pid: "1236", name: "monitoring-service", cpu: "3.1%", memory: "64MB", status: "运行中" },
              { pid: "1237", name: "scheduler", cpu: "2.8%", memory: "48MB", status: "运行中" },
              { pid: "1238", name: "message-broker", cpu: "5.4%", memory: "96MB", status: "运行中" },
            ].map((process) => (
              <div
                key={process.pid}
                className="flex items-center justify-between p-3 bg-slate-700/30 rounded border border-slate-600/30"
              >
                <div className="flex items-center space-x-4">
                  <span className="text-sm text-slate-400 font-mono">{process.pid}</span>
                  <span className="text-sm text-white font-medium">{process.name}</span>
                </div>
                <div className="flex items-center space-x-6">
                  <span className="text-sm text-slate-300">{process.cpu}</span>
                  <span className="text-sm text-slate-300">{process.memory}</span>
                  <Badge variant="outline" className="border-green-500/30 text-green-400">
                    {process.status}
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
