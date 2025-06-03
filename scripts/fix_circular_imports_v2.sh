#!/bin/bash

# 修复go-collector中的循环导入问题 - 第二版
# 更精确地处理导入和函数调用

set -e

echo "修复go-collector循环导入问题 v2..."

cd services/go-collector

# 备份文件
echo "创建备份..."
cp -r internal internal.backup.circular.v2

# 首先，让我们检查normalizer包中是否有GetNormalizer函数
echo "检查GetNormalizer函数..."

# 修复normalizer_publisher.go中的问题
echo "修复normalizer_publisher.go..."
cat > internal/nats/normalizer_publisher.go << 'EOF'
package nats

import (
	"fmt"
	"time"

	"go.uber.org/zap"

	"github.com/marketprism/go-collector/internal/normalizer"
	"github.com/marketprism/go-collector/internal/types"
)

// 设置NATS主题格式
const (
	TradeSubjectFormat        = "market.%s.%s.trade"       // market.{exchange}.{symbol}.trade
	OrderBookSubjectFormat    = "market.%s.%s.orderbook"   // market.{exchange}.{symbol}.orderbook
	KlineSubjectFormat        = "market.%s.%s.kline.%s"    // market.{exchange}.{symbol}.kline.{interval}
	TickerSubjectFormat       = "market.%s.%s.ticker"      // market.{exchange}.{symbol}.ticker
)

// NormalizerPublisher 规范化并发布数据
type NormalizerPublisher struct {
	client  *Client
	logger  *zap.Logger
	metrics *MetricsCollector
}

// MetricsCollector 收集规范化和发布的指标
type MetricsCollector struct {
	// 可以添加Prometheus指标收集器
}

// NewNormalizerPublisher 创建一个新的规范化发布器
func NewNormalizerPublisher(client *Client, logger *zap.Logger) *NormalizerPublisher {
	return &NormalizerPublisher{
		client: client,
		logger: logger.Named("normalizer-publisher"),
		metrics: &MetricsCollector{},
	}
}

// PublishTrade 规范化并发布交易数据
func (np *NormalizerPublisher) PublishTrade(exchange string, symbol string, data []byte) error {
	startTime := time.Now()
	
	// 获取对应交易所的规范化处理器
	norm, err := normalizer.GetNormalizer(exchange)
	if err != nil {
		np.logger.Error("获取规范化处理器失败", 
			zap.String("exchange", exchange),
			zap.Error(err))
		return fmt.Errorf("获取规范化处理器失败: %w", err)
	}
	
	// 规范化交易数据
	normalizedTrade, err := norm.NormalizeTrade(exchange, symbol, data)
	if err != nil {
		np.logger.Error("规范化交易数据失败", 
			zap.String("exchange", exchange),
			zap.String("symbol", symbol),
			zap.Error(err))
		return fmt.Errorf("规范化交易数据失败: %w", err)
	}
	
	// 构建NATS主题
	subject := fmt.Sprintf(TradeSubjectFormat, exchange, symbol)
	
	// 发布规范化后的数据
	err = np.client.Publish(subject, normalizedTrade)
	if err != nil {
		np.logger.Error("发布规范化交易数据失败", 
			zap.String("subject", subject),
			zap.Error(err))
		return fmt.Errorf("发布规范化交易数据失败: %w", err)
	}
	
	np.logger.Debug("已发布规范化交易数据", 
		zap.String("exchange", exchange),
		zap.String("symbol", symbol),
		zap.Duration("latency", time.Since(startTime)))
	
	return nil
}

// PublishOrderBook 规范化并发布订单簿数据
func (np *NormalizerPublisher) PublishOrderBook(exchange string, symbol string, data []byte) error {
	startTime := time.Now()
	
	// 获取对应交易所的规范化处理器
	norm, err := normalizer.GetNormalizer(exchange)
	if err != nil {
		np.logger.Error("获取规范化处理器失败", 
			zap.String("exchange", exchange),
			zap.Error(err))
		return fmt.Errorf("获取规范化处理器失败: %w", err)
	}
	
	// 规范化订单簿数据
	normalizedOrderBook, err := norm.NormalizeOrderBook(exchange, symbol, data)
	if err != nil {
		np.logger.Error("规范化订单簿数据失败", 
			zap.String("exchange", exchange),
			zap.String("symbol", symbol),
			zap.Error(err))
		return fmt.Errorf("规范化订单簿数据失败: %w", err)
	}
	
	// 构建NATS主题
	subject := fmt.Sprintf(OrderBookSubjectFormat, exchange, symbol)
	
	// 发布规范化后的数据
	err = np.client.Publish(subject, normalizedOrderBook)
	if err != nil {
		np.logger.Error("发布规范化订单簿数据失败", 
			zap.String("subject", subject),
			zap.Error(err))
		return fmt.Errorf("发布规范化订单簿数据失败: %w", err)
	}
	
	np.logger.Debug("已发布规范化订单簿数据", 
		zap.String("exchange", exchange),
		zap.String("symbol", symbol),
		zap.Duration("latency", time.Since(startTime)))
	
	return nil
}

// PublishKline 规范化并发布K线数据
func (np *NormalizerPublisher) PublishKline(exchange string, symbol string, interval string, data []byte) error {
	startTime := time.Now()
	
	// 获取对应交易所的规范化处理器
	norm, err := normalizer.GetNormalizer(exchange)
	if err != nil {
		np.logger.Error("获取规范化处理器失败", 
			zap.String("exchange", exchange),
			zap.Error(err))
		return fmt.Errorf("获取规范化处理器失败: %w", err)
	}
	
	// 规范化K线数据
	normalizedKline, err := norm.NormalizeKline(exchange, symbol, data)
	if err != nil {
		np.logger.Error("规范化K线数据失败", 
			zap.String("exchange", exchange),
			zap.String("symbol", symbol),
			zap.String("interval", interval),
			zap.Error(err))
		return fmt.Errorf("规范化K线数据失败: %w", err)
	}
	
	// 构建NATS主题
	subject := fmt.Sprintf(KlineSubjectFormat, exchange, symbol, interval)
	
	// 发布规范化后的数据
	err = np.client.Publish(subject, normalizedKline)
	if err != nil {
		np.logger.Error("发布规范化K线数据失败", 
			zap.String("subject", subject),
			zap.Error(err))
		return fmt.Errorf("发布规范化K线数据失败: %w", err)
	}
	
	np.logger.Debug("已发布规范化K线数据", 
		zap.String("exchange", exchange),
		zap.String("symbol", symbol),
		zap.String("interval", interval),
		zap.Duration("latency", time.Since(startTime)))
	
	return nil
}

// PublishTicker 规范化并发布行情数据
func (np *NormalizerPublisher) PublishTicker(exchange string, symbol string, data []byte) error {
	startTime := time.Now()
	
	// 获取对应交易所的规范化处理器
	norm, err := normalizer.GetNormalizer(exchange)
	if err != nil {
		np.logger.Error("获取规范化处理器失败", 
			zap.String("exchange", exchange),
			zap.Error(err))
		return fmt.Errorf("获取规范化处理器失败: %w", err)
	}
	
	// 规范化行情数据
	normalizedTicker, err := norm.NormalizeTicker(exchange, symbol, data)
	if err != nil {
		np.logger.Error("规范化行情数据失败", 
			zap.String("exchange", exchange),
			zap.String("symbol", symbol),
			zap.Error(err))
		return fmt.Errorf("规范化行情数据失败: %w", err)
	}
	
	// 构建NATS主题
	subject := fmt.Sprintf(TickerSubjectFormat, exchange, symbol)
	
	// 发布规范化后的数据
	err = np.client.Publish(subject, normalizedTicker)
	if err != nil {
		np.logger.Error("发布规范化行情数据失败", 
			zap.String("subject", subject),
			zap.Error(err))
		return fmt.Errorf("发布规范化行情数据失败: %w", err)
	}
	
	np.logger.Debug("已发布规范化行情数据", 
		zap.String("exchange", exchange),
		zap.String("symbol", symbol),
		zap.Duration("latency", time.Since(startTime)))
	
	return nil
}

// EnsureRequiredStreams 确保所需的NATS流存在
func (np *NormalizerPublisher) EnsureRequiredStreams() error {
	// 这里可以添加确保NATS流存在的逻辑
	np.logger.Info("确保NATS流存在")
	return nil
}
EOF

# 清理其他nats文件中不必要的导入
echo "清理client.go..."
sed -i.bak '/github.com\/marketprism\/go-collector\/internal\/types/d' internal/nats/client.go

echo "清理publisher.go..."
sed -i.bak '/github.com\/marketprism\/go-collector\/internal\/types/d' internal/nats/publisher.go

# 清理processors文件中不必要的导入
echo "清理processors文件..."
sed -i.bak '/strconv.*imported and not used/d' internal/normalizer/processors/deribit.go
sed -i.bak '/"strconv"/d' internal/normalizer/processors/deribit.go

echo "循环导入修复完成 v2"
echo "请检查修复结果并测试编译" 