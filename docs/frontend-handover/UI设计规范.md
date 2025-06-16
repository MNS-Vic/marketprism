# MarketPrism UI设计规范

## 🎨 概述
基于MarketPrism现有的modern UI设计，本文档提供完整的前端UI/UX设计规范，确保前端团队能够实现一致、专业的金融级用户界面。

## 🌈 色彩系统

### 主色调 - Carbon Black主题
```css
/* 主背景色 */
--primary-bg: #0f172a;           /* 深海蓝黑 */
--secondary-bg: #1e293b;         /* 碳黑色 */
--tertiary-bg: #334155;          /* 石板灰 */

/* 表面色彩 */
--surface-1: rgba(30, 41, 59, 0.6);     /* 半透明表面 */
--surface-2: rgba(51, 65, 85, 0.4);     /* 浅色表面 */
--surface-3: rgba(71, 85, 105, 0.3);    /* 最浅表面 */

/* 边框色彩 */
--border-primary: rgba(148, 163, 184, 0.2);
--border-secondary: rgba(203, 213, 225, 0.1);
```

### 功能色彩
```css
/* 成功状态 - 绿色系 */
--success-primary: #10b981;      /* 翠绿 */
--success-light: #34d399;        /* 亮绿 */
--success-dark: #059669;         /* 深绿 */
--success-bg: rgba(16, 185, 129, 0.1);

/* 警告状态 - 橙色系 */
--warning-primary: #f59e0b;      /* 琥珀橙 */
--warning-light: #fbbf24;        /* 亮橙 */
--warning-dark: #d97706;         /* 深橙 */
--warning-bg: rgba(245, 158, 11, 0.1);

/* 错误状态 - 红色系 */
--error-primary: #ef4444;        /* 朱红 */
--error-light: #f87171;          /* 亮红 */
--error-dark: #dc2626;           /* 深红 */
--error-bg: rgba(239, 68, 68, 0.1);

/* 信息状态 - 蓝色系 */
--info-primary: #3b82f6;         /* 蔚蓝 */
--info-light: #60a5fa;           /* 亮蓝 */
--info-dark: #2563eb;            /* 深蓝 */
--info-bg: rgba(59, 130, 246, 0.1);
```

### 文本色彩
```css
--text-primary: #f8fafc;         /* 主文本 - 接近白色 */
--text-secondary: #cbd5e1;       /* 次要文本 - 银灰 */
--text-tertiary: #94a3b8;        /* 三级文本 - 石板灰 */
--text-disabled: #64748b;        /* 禁用文本 - 暗灰 */
--text-accent: #38bdf8;          /* 强调文本 - 天蓝 */
```

### 数据可视化色彩
```css
/* 价格涨跌色彩 */
--price-up: #10b981;             /* 涨价绿 */
--price-down: #ef4444;           /* 跌价红 */
--price-neutral: #94a3b8;        /* 无变化灰 */

/* 图表配色方案 */
--chart-colors: [
  '#3b82f6',  /* 蓝色 */
  '#10b981',  /* 绿色 */
  '#f59e0b',  /* 橙色 */
  '#ef4444',  /* 红色 */
  '#8b5cf6',  /* 紫色 */
  '#06b6d4',  /* 青色 */
  '#f97316',  /* 橙红 */
  '#84cc16'   /* 青绿 */
];
```

## 🪟 玻璃拟态效果

### 基础玻璃效果
```css
.glass-morphism {
  background: rgba(30, 41, 59, 0.6);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 16px;
  box-shadow: 
    0 8px 32px rgba(0, 0, 0, 0.4),
    inset 0 1px 0 rgba(255, 255, 255, 0.1);
}

.glass-card {
  background: rgba(51, 65, 85, 0.4);
  backdrop-filter: blur(8px);
  border-radius: 12px;
  border: 1px solid rgba(203, 213, 225, 0.1);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.glass-card:hover {
  background: rgba(71, 85, 105, 0.5);
  border-color: rgba(148, 163, 184, 0.3);
  transform: translateY(-2px);
  box-shadow: 0 12px 24px rgba(0, 0, 0, 0.3);
}
```

### 层级效果
```css
/* 一级表面 - 主要内容 */
.surface-level-1 {
  background: rgba(30, 41, 59, 0.8);
  backdrop-filter: blur(16px);
  z-index: 10;
}

/* 二级表面 - 卡片组件 */
.surface-level-2 {
  background: rgba(51, 65, 85, 0.6);
  backdrop-filter: blur(12px);
  z-index: 20;
}

/* 三级表面 - 浮层组件 */
.surface-level-3 {
  background: rgba(71, 85, 105, 0.7);
  backdrop-filter: blur(20px);
  z-index: 30;
}
```

## 📐 布局系统

### 响应式断点
```css
/* 断点定义 */
$breakpoints: (
  xs: 0,          /* 超小屏 */
  sm: 576px,      /* 小屏 */
  md: 768px,      /* 中屏 */
  lg: 992px,      /* 大屏 */
  xl: 1200px,     /* 超大屏 */
  xxl: 1400px     /* 超超大屏 */
);

/* 响应式容器 */
.container {
  width: 100%;
  padding-left: 16px;
  padding-right: 16px;
  margin: 0 auto;
}

@media (min-width: 576px) { .container { max-width: 540px; } }
@media (min-width: 768px) { .container { max-width: 720px; } }
@media (min-width: 992px) { .container { max-width: 960px; } }
@media (min-width: 1200px) { .container { max-width: 1140px; } }
```

### 网格系统
```css
/* 12列网格系统 */
.grid {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  gap: 24px;
  padding: 24px;
}

.col-1 { grid-column: span 1; }
.col-2 { grid-column: span 2; }
.col-3 { grid-column: span 3; }
.col-4 { grid-column: span 4; }
.col-6 { grid-column: span 6; }
.col-8 { grid-column: span 8; }
.col-12 { grid-column: span 12; }

/* 响应式网格 */
@media (max-width: 768px) {
  .grid { grid-template-columns: 1fr; gap: 16px; }
  .col-md-12 { grid-column: span 12; }
}
```

### 间距系统
```css
/* 间距变量 */
:root {
  --spacing-xs: 4px;
  --spacing-sm: 8px;
  --spacing-md: 16px;
  --spacing-lg: 24px;
  --spacing-xl: 32px;
  --spacing-2xl: 48px;
  --spacing-3xl: 64px;
}

/* 间距工具类 */
.p-xs { padding: var(--spacing-xs); }
.p-sm { padding: var(--spacing-sm); }
.p-md { padding: var(--spacing-md); }
.p-lg { padding: var(--spacing-lg); }

.m-xs { margin: var(--spacing-xs); }
.m-sm { margin: var(--spacing-sm); }
.m-md { margin: var(--spacing-md); }
.m-lg { margin: var(--spacing-lg); }
```

## 📝 字体系统

### 字体族
```css
:root {
  /* 主字体 - 系统字体栈 */
  --font-primary: -apple-system, BlinkMacSystemFont, 'Segoe UI', 
                  'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 
                  'Helvetica Neue', Helvetica, Arial, sans-serif;
  
  /* 数字字体 - 等宽字体 */
  --font-mono: 'JetBrains Mono', 'Fira Code', 'Source Code Pro', 
               Consolas, 'Liberation Mono', Menlo, Courier, monospace;
  
  /* 标题字体 */
  --font-heading: 'Inter', var(--font-primary);
}
```

### 字体大小
```css
/* 字体大小系统 */
:root {
  --text-xs: 12px;      /* 超小文本 */
  --text-sm: 14px;      /* 小文本 */
  --text-base: 16px;    /* 基础文本 */
  --text-lg: 18px;      /* 大文本 */
  --text-xl: 20px;      /* 超大文本 */
  --text-2xl: 24px;     /* 小标题 */
  --text-3xl: 30px;     /* 中标题 */
  --text-4xl: 36px;     /* 大标题 */
  --text-5xl: 48px;     /* 超大标题 */
}

/* 行高系统 */
:root {
  --leading-tight: 1.25;
  --leading-normal: 1.5;
  --leading-relaxed: 1.75;
}
```

### 字重系统
```css
:root {
  --font-light: 300;
  --font-normal: 400;
  --font-medium: 500;
  --font-semibold: 600;
  --font-bold: 700;
}
```

## 🧩 组件规范

### 卡片组件
```css
.metric-card {
  @apply glass-card;
  padding: 24px;
  min-height: 120px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.metric-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.metric-card__title {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  font-weight: var(--font-medium);
}

.metric-card__value {
  font-size: var(--text-3xl);
  color: var(--text-primary);
  font-weight: var(--font-bold);
  font-family: var(--font-mono);
}

.metric-card__change {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  display: flex;
  align-items: center;
  gap: 4px;
}

.metric-card__change--positive { color: var(--success-primary); }
.metric-card__change--negative { color: var(--error-primary); }
.metric-card__change--neutral { color: var(--text-tertiary); }
```

### 按钮组件
```css
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 24px;
  border-radius: 8px;
  font-weight: var(--font-medium);
  font-size: var(--text-sm);
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  cursor: pointer;
  border: none;
  outline: none;
}

.btn--primary {
  background: var(--info-primary);
  color: white;
}

.btn--primary:hover {
  background: var(--info-dark);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
}

.btn--ghost {
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border-primary);
}

.btn--ghost:hover {
  background: rgba(71, 85, 105, 0.3);
  border-color: var(--border-secondary);
}
```

### 状态指示器
```css
.status-indicator {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 20px;
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
}

.status-indicator__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.status-indicator--success {
  background: var(--success-bg);
  color: var(--success-primary);
}

.status-indicator--success .status-indicator__dot {
  background: var(--success-primary);
  animation: pulse 2s infinite;
}

.status-indicator--error {
  background: var(--error-bg);
  color: var(--error-primary);
}

.status-indicator--warning {
  background: var(--warning-bg);
  color: var(--warning-primary);
}
```

## 🎭 动画系统

### 基础动画
```css
/* 淡入动画 */
@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

/* 滑入动画 */
@keyframes slideInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* 脉冲动画 */
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* 加载旋转动画 */
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
```

### 过渡效果
```css
/* 标准过渡 */
.transition-standard {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

/* 快速过渡 */
.transition-fast {
  transition: all 0.15s cubic-bezier(0.4, 0, 0.2, 1);
}

/* 慢速过渡 */
.transition-slow {
  transition: all 0.5s cubic-bezier(0.4, 0, 0.2, 1);
}

/* 弹性过渡 */
.transition-bounce {
  transition: all 0.4s cubic-bezier(0.68, -0.55, 0.265, 1.55);
}
```

### 页面切换动画
```css
.page-enter {
  opacity: 0;
  transform: translateX(30px);
}

.page-enter-active {
  opacity: 1;
  transform: translateX(0);
  transition: all 0.3s ease;
}

.page-exit {
  opacity: 1;
  transform: translateX(0);
}

.page-exit-active {
  opacity: 0;
  transform: translateX(-30px);
  transition: all 0.3s ease;
}
```

## 📱 移动端适配

### 触摸优化
```css
/* 触摸目标最小尺寸 */
.touch-target {
  min-height: 44px;
  min-width: 44px;
}

/* 触摸反馈 */
.touch-feedback {
  -webkit-tap-highlight-color: rgba(59, 130, 246, 0.2);
  -webkit-touch-callout: none;
  -webkit-user-select: none;
  user-select: none;
}
```

### 移动端布局
```css
@media (max-width: 768px) {
  /* 移动端间距调整 */
  .grid { gap: 12px; padding: 16px; }
  
  /* 移动端卡片调整 */
  .metric-card { padding: 16px; min-height: 100px; }
  
  /* 移动端字体调整 */
  .metric-card__value { font-size: var(--text-2xl); }
  
  /* 移动端按钮调整 */
  .btn { padding: 14px 20px; font-size: var(--text-base); }
}

/* 超小屏适配 */
@media (max-width: 480px) {
  .container { padding-left: 12px; padding-right: 12px; }
  .grid { gap: 8px; padding: 12px; }
  .metric-card { padding: 12px; }
}
```

## 🌙 暗色模式

### 主题切换
```css
/* 暗色模式已经是默认主题 */
[data-theme="dark"] {
  --primary-bg: #0f172a;
  --text-primary: #f8fafc;
}

/* 亮色模式 (可选) */
[data-theme="light"] {
  --primary-bg: #ffffff;
  --secondary-bg: #f8fafc;
  --text-primary: #1e293b;
  --text-secondary: #475569;
}
```

## ♿ 无障碍访问

### 颜色对比度
```css
/* 确保文本对比度符合WCAG AA标准 */
.high-contrast {
  color: #ffffff;
  background: #000000;
}

/* 焦点指示器 */
.focusable:focus {
  outline: 2px solid var(--info-primary);
  outline-offset: 2px;
}
```

### 屏幕阅读器支持
```css
/* 屏幕阅读器专用文本 */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
```

## 🎯 最佳实践

### 1. 性能优化
- 使用CSS变量提高可维护性
- 避免过度使用backdrop-filter
- 合理使用动画，避免影响性能

### 2. 一致性原则
- 统一使用设计令牌
- 保持组件间距和样式一致
- 遵循既定的颜色和字体规范

### 3. 响应式设计
- 移动端优先的设计策略
- 确保所有交互元素在触摸设备上可用
- 合理调整移动端的信息密度

### 4. 可访问性
- 确保足够的颜色对比度
- 提供清晰的焦点指示器
- 支持键盘导航

这个UI设计规范为前端团队提供了完整的视觉设计指导，确保能够实现与现有modern UI一致的专业金融级界面。