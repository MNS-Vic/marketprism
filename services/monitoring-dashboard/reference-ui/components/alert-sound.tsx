"use client"

import { useEffect, useRef } from "react"

interface AlertSoundProps {
  level: string
  enabled: boolean
}

export function AlertSound({ level, enabled }: AlertSoundProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null)

  useEffect(() => {
    if (enabled && typeof window !== "undefined") {
      // 创建音频上下文
      const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)()

      const playAlertSound = (frequency: number, duration: number) => {
        const oscillator = audioContext.createOscillator()
        const gainNode = audioContext.createGain()

        oscillator.connect(gainNode)
        gainNode.connect(audioContext.destination)

        oscillator.frequency.setValueAtTime(frequency, audioContext.currentTime)
        oscillator.type = "sine"

        gainNode.gain.setValueAtTime(0.3, audioContext.currentTime)
        gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + duration)

        oscillator.start(audioContext.currentTime)
        oscillator.stop(audioContext.currentTime + duration)
      }

      // 根据告警级别播放不同声音
      switch (level) {
        case "critical":
          // 紧急警报声 - 高频率，重复3次
          playAlertSound(800, 0.2)
          setTimeout(() => playAlertSound(800, 0.2), 300)
          setTimeout(() => playAlertSound(800, 0.2), 600)
          break
        case "warning":
          // 警告声 - 中频率，重复2次
          playAlertSound(600, 0.3)
          setTimeout(() => playAlertSound(600, 0.3), 400)
          break
        case "info":
          // 提示声 - 低频率，单次
          playAlertSound(400, 0.4)
          break
      }
    }
  }, [level, enabled])

  return null
}
