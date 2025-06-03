#!/bin/bash

# 修复go-collector中的循环导入问题
# 主要问题：processors包导入了normalizer包，但它们应该是独立的

set -e

echo "修复go-collector循环导入问题..."

cd services/go-collector

# 备份文件
echo "创建备份..."
cp -r internal/normalizer/processors internal/normalizer/processors.backup.circular

# 修复processors包中的导入问题
# 将normalizer包的类型定义移动到一个共享的types包中

# 创建types包
mkdir -p internal/types

# 创建types.go文件，包含所有共享的类型定义
cat > internal/types/types.go << 'EOF'
package types

import "time"

// NormalizedTrade 标准化的交易数据
type NormalizedTrade struct {
	ExchangeName  string    `json:"exchange_name"`
	SymbolName    string    `json:"symbol_name"`
	TradeID       string    `json:"trade_id"`
	Price         float64   `json:"price"`
	Quantity      float64   `json:"quantity"`
	QuoteQuantity float64   `json:"quote_quantity"`
	Time          time.Time `json:"time"`
	IsBuyerMaker  bool      `json:"is_buyer_maker"`
	IsBestMatch   bool      `json:"is_best_match"`
}

// PriceLevel 价格档位
type PriceLevel struct {
	Price    float64 `json:"price"`
	Quantity float64 `json:"quantity"`
}

// NormalizedOrderBook 标准化的订单簿数据
type NormalizedOrderBook struct {
	ExchangeName string       `json:"exchange_name"`
	SymbolName   string       `json:"symbol_name"`
	LastUpdateID int64        `json:"last_update_id"`
	Bids         []PriceLevel `json:"bids"`
	Asks         []PriceLevel `json:"asks"`
	Time         time.Time    `json:"time"`
}

// NormalizedKline 标准化的K线数据
type NormalizedKline struct {
	ExchangeName        string    `json:"exchange_name"`
	SymbolName          string    `json:"symbol_name"`
	OpenTime            time.Time `json:"open_time"`
	CloseTime           time.Time `json:"close_time"`
	Interval            string    `json:"interval"`
	Open                float64   `json:"open"`
	High                float64   `json:"high"`
	Low                 float64   `json:"low"`
	Close               float64   `json:"close"`
	Volume              float64   `json:"volume"`
	QuoteVolume         float64   `json:"quote_volume"`
	TradeCount          int64     `json:"trade_count"`
	TakerBuyVolume      float64   `json:"taker_buy_volume"`
	TakerBuyQuoteVolume float64   `json:"taker_buy_quote_volume"`
}

// NormalizedTicker 标准化的行情数据
type NormalizedTicker struct {
	ExchangeName       string    `json:"exchange_name"`
	SymbolName         string    `json:"symbol_name"`
	LastPrice          float64   `json:"last_price"`
	OpenPrice          float64   `json:"open_price"`
	HighPrice          float64   `json:"high_price"`
	LowPrice           float64   `json:"low_price"`
	Volume             float64   `json:"volume"`
	QuoteVolume        float64   `json:"quote_volume"`
	PriceChange        float64   `json:"price_change"`
	PriceChangePercent float64   `json:"price_change_percent"`
	WeightedAvgPrice   float64   `json:"weighted_avg_price"`
	LastQuantity       float64   `json:"last_quantity"`
	BestBidPrice       float64   `json:"best_bid_price"`
	BestBidQuantity    float64   `json:"best_bid_quantity"`
	BestAskPrice       float64   `json:"best_ask_price"`
	BestAskQuantity    float64   `json:"best_ask_quantity"`
	OpenTime           time.Time `json:"open_time"`
	CloseTime          time.Time `json:"close_time"`
	FirstTradeID       int64     `json:"first_trade_id"`
	LastTradeID        int64     `json:"last_trade_id"`
	TradeCount         int64     `json:"trade_count"`
	Time               time.Time `json:"time"`
}

// Normalizer 数据归一化接口
type Normalizer interface {
	NormalizeTrade(exchange string, symbol string, data []byte) (*NormalizedTrade, error)
	NormalizeOrderBook(exchange string, symbol string, data []byte) (*NormalizedOrderBook, error)
	NormalizeKline(exchange string, symbol string, data []byte) (*NormalizedKline, error)
	NormalizeTicker(exchange string, symbol string, data []byte) (*NormalizedTicker, error)
}
EOF

echo "已创建types包"

# 更新processors包中的文件，使用types包而不是normalizer包
for file in internal/normalizer/processors/*.go; do
    if [[ -f "$file" ]]; then
        echo "更新 $file"
        sed -i.bak 's|"github.com/marketprism/go-collector/internal/normalizer"|"github.com/marketprism/go-collector/internal/types"|g' "$file"
        sed -i.bak 's|normalizer\.|types.|g' "$file"
    fi
done

# 更新normalizer包中的文件，使用types包
for file in internal/normalizer/*.go; do
    if [[ -f "$file" && ! -d "$file" ]]; then
        echo "更新 $file"
        # 添加types包导入
        if ! grep -q '"github.com/marketprism/go-collector/internal/types"' "$file"; then
            sed -i.bak '/^import (/a\
	"github.com/marketprism/go-collector/internal/types"
' "$file"
        fi
        # 替换类型引用
        sed -i.bak 's|NormalizedTrade|types.NormalizedTrade|g' "$file"
        sed -i.bak 's|NormalizedOrderBook|types.NormalizedOrderBook|g' "$file"
        sed -i.bak 's|NormalizedKline|types.NormalizedKline|g' "$file"
        sed -i.bak 's|NormalizedTicker|types.NormalizedTicker|g' "$file"
        sed -i.bak 's|PriceLevel|types.PriceLevel|g' "$file"
        sed -i.bak 's|Normalizer|types.Normalizer|g' "$file"
    fi
done

# 更新nats包中的文件
for file in internal/nats/*.go; do
    if [[ -f "$file" ]]; then
        echo "更新 $file"
        # 添加types包导入
        if ! grep -q '"github.com/marketprism/go-collector/internal/types"' "$file"; then
            sed -i.bak '/^import (/a\
	"github.com/marketprism/go-collector/internal/types"
' "$file"
        fi
        # 替换normalizer包导入为types包
        sed -i.bak 's|"github.com/marketprism/go-collector/internal/normalizer"|"github.com/marketprism/go-collector/internal/types"|g' "$file"
        sed -i.bak 's|normalizer\.|types.|g' "$file"
    fi
done

echo "循环导入修复完成"
echo "请检查修复结果并测试编译" 