"use client"

interface PrismLogoProps {
  size?: "sm" | "md" | "lg"
  showText?: boolean
}

export function PrismLogo({ size = "md", showText = true }: PrismLogoProps) {
  const sizeClasses = {
    sm: "w-8 h-8",
    md: "w-12 h-12",
    lg: "w-16 h-16",
  }

  const textSizeClasses = {
    sm: "text-lg",
    md: "text-xl",
    lg: "text-2xl",
  }

  return (
    <div className="flex items-center space-x-3">
      {/* 简洁的棱镜图标 */}
      <div className={`${sizeClasses[size]} relative flex items-center justify-center`}>
        {/* 棱镜主体 - 简洁的三角形 */}
        <div
          className="w-full h-full bg-blue-500 opacity-90"
          style={{
            clipPath: "polygon(50% 0%, 0% 100%, 100% 100%)",
          }}
        />

        {/* 简单的高光效果 */}
        <div
          className="absolute inset-0 bg-white opacity-20"
          style={{
            clipPath: "polygon(50% 0%, 20% 100%, 50% 80%)",
          }}
        />
      </div>

      {/* 品牌文字 */}
      {showText && (
        <div className="flex flex-col">
          <h1 className={`${textSizeClasses[size]} font-bold text-white`}>市场棱镜</h1>
          <p className="text-xs text-blue-300/70 font-medium tracking-wide">MarketPrism</p>
        </div>
      )}
    </div>
  )
}
