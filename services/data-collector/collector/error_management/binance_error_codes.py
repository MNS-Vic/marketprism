"""
Binance官方错误码管理系统
基于官方文档：
- 现货：https://developers.binance.com/docs/zh-CN/binance-spot-api-docs/errors
- 衍生品：https://developers.binance.com/docs/zh-CN/derivatives/usds-margined-futures/error-code
"""

from enum import Enum
from typing import Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class ErrorInfo:
    """错误信息数据类"""
    code: int
    name: str
    description: str
    category: str
    severity: str  # 'critical', 'high', 'medium', 'low'
    retry_recommended: bool
    user_action: str


class BinanceErrorCategory(Enum):
    """Binance错误分类"""
    SERVER_NETWORK = "server_network"  # 10xx - 服务器或网络问题
    REQUEST_ISSUES = "request_issues"  # 11xx - 请求内容问题
    PROCESSING = "processing"  # 20xx - 处理问题
    FILTERS = "filters"  # 40xx - 过滤器和其他问题
    EXECUTION = "execution"  # 50xx - 订单执行问题


class BinanceErrorSeverity(Enum):
    """错误严重程度"""
    CRITICAL = "critical"  # 系统级错误，需要立即处理
    HIGH = "high"  # 高优先级错误，影响核心功能
    MEDIUM = "medium"  # 中等错误，可能影响部分功能
    LOW = "low"  # 低优先级错误，不影响核心功能


class BinanceErrorManager:
    """Binance错误码管理器"""
    
    def __init__(self):
        self._error_codes = self._initialize_error_codes()
    
    def _initialize_error_codes(self) -> Dict[int, ErrorInfo]:
        """初始化错误码映射"""
        return {
            # 10xx - 服务器或网络问题
            -1000: ErrorInfo(-1000, "UNKNOWN", "未知错误", "server_network", "critical", True, "重试请求，如果持续失败请联系技术支持"),
            -1001: ErrorInfo(-1001, "DISCONNECTED", "连接断开", "server_network", "high", True, "检查网络连接，重试请求"),
            -1002: ErrorInfo(-1002, "UNAUTHORIZED", "未授权", "server_network", "high", False, "检查API密钥权限和IP白名单"),
            -1003: ErrorInfo(-1003, "TOO_MANY_REQUESTS", "请求过多", "server_network", "high", True, "减少请求频率，使用WebSocket获取实时数据"),
            -1006: ErrorInfo(-1006, "UNEXPECTED_RESP", "非常规响应", "server_network", "medium", True, "重试请求，检查订单状态"),
            -1007: ErrorInfo(-1007, "TIMEOUT", "超时", "server_network", "medium", True, "重试请求，检查网络连接"),
            -1008: ErrorInfo(-1008, "SERVER_BUSY", "服务器繁忙", "server_network", "medium", True, "等待几分钟后重试"),
            -1013: ErrorInfo(-1013, "INVALID_MESSAGE", "消息无效", "server_network", "medium", False, "检查请求参数和过滤器设置"),
            -1014: ErrorInfo(-1014, "UNKNOWN_ORDER_COMPOSITION", "不支持的订单参数组合", "server_network", "medium", False, "检查订单参数组合"),
            -1015: ErrorInfo(-1015, "TOO_MANY_ORDERS", "订单太多", "server_network", "medium", True, "减少订单数量或等待后重试"),
            -1016: ErrorInfo(-1016, "SERVICE_SHUTTING_DOWN", "服务器下线", "server_network", "critical", True, "等待服务恢复"),
            -1020: ErrorInfo(-1020, "UNSUPPORTED_OPERATION", "不支持的操作", "server_network", "medium", False, "检查API文档，使用支持的操作"),
            -1021: ErrorInfo(-1021, "INVALID_TIMESTAMP", "时间同步问题", "server_network", "high", False, "同步系统时间，调整recvWindow参数"),
            -1022: ErrorInfo(-1022, "INVALID_SIGNATURE", "签名不正确", "server_network", "high", False, "检查API密钥和签名算法"),
            
            # 11xx - 请求内容问题
            -1100: ErrorInfo(-1100, "ILLEGAL_CHARS", "非法字符", "request_issues", "medium", False, "检查参数中的特殊字符"),
            -1101: ErrorInfo(-1101, "TOO_MANY_PARAMETERS", "参数太多", "request_issues", "medium", False, "减少请求参数数量"),
            -1102: ErrorInfo(-1102, "MANDATORY_PARAM_EMPTY_OR_MALFORMED", "缺少必须参数", "request_issues", "medium", False, "添加必需的参数"),
            -1103: ErrorInfo(-1103, "UNKNOWN_PARAM", "无法识别的参数", "request_issues", "medium", False, "移除未知参数"),
            -1104: ErrorInfo(-1104, "UNREAD_PARAMETERS", "冗余参数", "request_issues", "low", False, "移除多余参数"),
            -1105: ErrorInfo(-1105, "PARAM_EMPTY", "空参数", "request_issues", "medium", False, "为参数提供有效值"),
            -1106: ErrorInfo(-1106, "PARAM_NOT_REQUIRED", "非必需参数", "request_issues", "low", False, "移除不需要的参数"),
            -1108: ErrorInfo(-1108, "BAD_PRECISION", "参数溢出", "request_issues", "medium", False, "调整参数精度"),
            -1111: ErrorInfo(-1111, "BAD_PRECISION", "精度过高", "request_issues", "medium", False, "降低参数精度"),
            -1112: ErrorInfo(-1112, "NO_DEPTH", "空白的orderbook", "request_issues", "medium", False, "选择有流动性的交易对"),
            -1114: ErrorInfo(-1114, "TIF_NOT_REQUIRED", "错误地发送了不需要的TIF参数", "request_issues", "medium", False, "移除TimeInForce参数"),
            -1115: ErrorInfo(-1115, "INVALID_TIF", "无效的TIF参数", "request_issues", "medium", False, "使用有效的TimeInForce值"),
            -1116: ErrorInfo(-1116, "INVALID_ORDER_TYPE", "无效的订单类型", "request_issues", "medium", False, "使用有效的订单类型"),
            -1117: ErrorInfo(-1117, "INVALID_SIDE", "无效的订单方向", "request_issues", "medium", False, "使用BUY或SELL"),
            -1118: ErrorInfo(-1118, "EMPTY_NEW_CL_ORD_ID", "空白的newClientOrderId", "request_issues", "medium", False, "提供有效的客户订单ID"),
            -1119: ErrorInfo(-1119, "EMPTY_ORG_CL_ORD_ID", "空白的originalClientOrderId", "request_issues", "medium", False, "提供有效的原始客户订单ID"),
            -1120: ErrorInfo(-1120, "BAD_INTERVAL", "无效的间隔", "request_issues", "medium", False, "使用有效的时间间隔"),
            -1121: ErrorInfo(-1121, "BAD_SYMBOL", "无效的交易对", "request_issues", "medium", False, "使用有效的交易对符号"),
            -1122: ErrorInfo(-1122, "INVALID_SYMBOL_STATUS", "无效的交易对状态", "request_issues", "medium", False, "检查交易对是否可交易"),
            -1125: ErrorInfo(-1125, "INVALID_LISTEN_KEY", "无效的listenKey", "request_issues", "medium", False, "重新生成listenKey"),
            -1127: ErrorInfo(-1127, "MORE_THAN_XX_HOURS", "查询间隔过长", "request_issues", "medium", False, "缩短查询时间范围"),
            -1128: ErrorInfo(-1128, "OPTIONAL_PARAMS_BAD_COMBO", "无效的可选参数组合", "request_issues", "medium", False, "检查参数组合"),
            -1130: ErrorInfo(-1130, "INVALID_PARAMETER", "无效参数值", "request_issues", "medium", False, "提供有效的参数值"),
            
            # 20xx - 处理问题
            -2010: ErrorInfo(-2010, "NEW_ORDER_REJECTED", "新订单被拒绝", "processing", "high", False, "检查订单参数和账户状态"),
            -2011: ErrorInfo(-2011, "CANCEL_REJECTED", "撤销订单被拒绝", "processing", "medium", False, "检查订单ID和状态"),
            -2013: ErrorInfo(-2013, "NO_SUCH_ORDER", "不存在的订单", "processing", "medium", False, "检查订单ID是否正确"),
            -2014: ErrorInfo(-2014, "BAD_API_KEY_FMT", "API Key格式无效", "processing", "high", False, "检查API Key格式"),
            -2015: ErrorInfo(-2015, "REJECTED_MBX_KEY", "API Key权限问题", "processing", "high", False, "检查API Key权限和IP限制"),
            -2016: ErrorInfo(-2016, "NO_TRADING_WINDOW", "非交易窗口", "processing", "medium", False, "在交易时间内操作"),
            -2018: ErrorInfo(-2018, "BALANCE_NOT_SUFFICIENT", "余额不足", "processing", "high", False, "充值或减少订单金额"),
            -2019: ErrorInfo(-2019, "MARGIN_NOT_SUFFICIENT", "保证金不足", "processing", "high", False, "增加保证金或减少仓位"),
            
            # 40xx - 过滤器和其他问题
            -4000: ErrorInfo(-4000, "INVALID_ORDER_STATUS", "订单状态不正确", "filters", "medium", False, "检查订单状态"),
            -4001: ErrorInfo(-4001, "PRICE_LESS_THAN_ZERO", "价格小于0", "filters", "medium", False, "设置正确的价格"),
            -4002: ErrorInfo(-4002, "PRICE_GREATER_THAN_MAX_PRICE", "价格超过最大值", "filters", "medium", False, "降低价格"),
            -4003: ErrorInfo(-4003, "QTY_LESS_THAN_ZERO", "数量小于0", "filters", "medium", False, "设置正确的数量"),
            -4004: ErrorInfo(-4004, "QTY_LESS_THAN_MIN_QTY", "数量小于最小值", "filters", "medium", False, "增加订单数量"),
            -4005: ErrorInfo(-4005, "QTY_GREATER_THAN_MAX_QTY", "数量大于最大值", "filters", "medium", False, "减少订单数量"),
            -4164: ErrorInfo(-4164, "MIN_NOTIONAL", "订单金额过小", "filters", "medium", False, "增加订单金额至5USDT以上"),

            # 50xx - 订单执行问题
            -5021: ErrorInfo(-5021, "FOK_ORDER_REJECT", "FOK订单被拒绝", "execution", "medium", False, "订单无法完全成交，使用其他订单类型"),
            -5022: ErrorInfo(-5022, "GTX_ORDER_REJECT", "Post Only订单被拒绝", "execution", "medium", False, "订单无法仅做maker，调整价格"),

            # 衍生品特有错误码
            -2020: ErrorInfo(-2020, "UNABLE_TO_FILL", "无法成交", "processing", "medium", False, "调整价格或数量"),
            -2021: ErrorInfo(-2021, "ORDER_WOULD_IMMEDIATELY_TRIGGER", "订单可能被立刻触发", "processing", "medium", False, "调整触发价格"),
            -2022: ErrorInfo(-2022, "REDUCE_ONLY_REJECT", "ReduceOnly订单被拒绝", "processing", "medium", False, "检查持仓方向和数量"),
            -2023: ErrorInfo(-2023, "USER_IN_LIQUIDATION", "用户正处于被强平模式", "processing", "critical", False, "等待强平完成或增加保证金"),
            -2024: ErrorInfo(-2024, "POSITION_NOT_SUFFICIENT", "持仓不足", "processing", "medium", False, "检查持仓数量"),
            -2025: ErrorInfo(-2025, "MAX_OPEN_ORDER_EXCEEDED", "挂单量达到上限", "processing", "medium", False, "取消部分挂单"),
            -2027: ErrorInfo(-2027, "MAX_LEVERAGE_RATIO", "超过最大杠杆", "processing", "high", False, "降低杠杆或减少仓位"),
            -2028: ErrorInfo(-2028, "MIN_LEVERAGE_RATIO", "杠杆过低", "processing", "medium", False, "增加保证金余额"),

            # 更多过滤器错误
            -4006: ErrorInfo(-4006, "STOP_PRICE_LESS_THAN_ZERO", "触发价小于0", "filters", "medium", False, "设置正确的触发价"),
            -4007: ErrorInfo(-4007, "STOP_PRICE_GREATER_THAN_MAX_PRICE", "触发价超过最大值", "filters", "medium", False, "降低触发价"),
            -4013: ErrorInfo(-4013, "PRICE_LESS_THAN_MIN_PRICE", "价格小于最小价格", "filters", "medium", False, "提高价格"),
            -4014: ErrorInfo(-4014, "PRICE_NOT_INCREASED_BY_TICK_SIZE", "价格精度不正确", "filters", "medium", False, "调整价格精度"),
            -4015: ErrorInfo(-4015, "INVALID_CL_ORD_ID_LEN", "客户订单ID长度错误", "filters", "medium", False, "客户订单ID长度不超过36字符"),
            -4131: ErrorInfo(-4131, "MARKET_ORDER_REJECT", "市价单被拒绝", "filters", "medium", False, "对手价格不满足PERCENT_PRICE过滤器"),
            -4192: ErrorInfo(-4192, "COOLING_OFF_PERIOD", "合约冷静期", "filters", "high", False, "等待冷静期结束"),

            # API限流相关
            -1034: ErrorInfo(-1034, "TOO_MANY_CONNECTIONS", "连接太多", "server_network", "high", True, "减少并发连接数"),
            -1181: ErrorInfo(-1181, "TOO_MANY_MESSAGES", "消息太多", "server_network", "high", True, "减少消息发送频率"),

            # 权限相关
            -4087: ErrorInfo(-4087, "REDUCE_ONLY_ORDER_PERMISSION", "只能下仅减仓订单", "filters", "high", False, "账户被限制，只能平仓"),
            -4088: ErrorInfo(-4088, "NO_PLACE_ORDER_PERMISSION", "无下单权限", "filters", "critical", False, "账户被限制交易"),
            -4400: ErrorInfo(-4400, "TRADING_QUANTITATIVE_RULE", "违反量化交易规则", "filters", "critical", False, "账户被设置为仅减仓"),
            -4401: ErrorInfo(-4401, "LARGE_POSITION_SYM_RULE", "大持仓风控规则", "filters", "critical", False, "减少持仓规模"),
        }
    
    def get_error_info(self, error_code: int) -> Optional[ErrorInfo]:
        """获取错误信息"""
        return self._error_codes.get(error_code)
    
    def is_retryable_error(self, error_code: int) -> bool:
        """判断错误是否可重试"""
        error_info = self.get_error_info(error_code)
        return error_info.retry_recommended if error_info else False
    
    def get_error_severity(self, error_code: int) -> str:
        """获取错误严重程度"""
        error_info = self.get_error_info(error_code)
        return error_info.severity if error_info else "unknown"
    
    def get_user_action(self, error_code: int) -> str:
        """获取用户建议操作"""
        error_info = self.get_error_info(error_code)
        return error_info.user_action if error_info else "未知错误，请联系技术支持"
    
    def format_error_message(self, error_code: int, original_message: str = "") -> str:
        """格式化错误消息"""
        error_info = self.get_error_info(error_code)
        if not error_info:
            return f"未知错误码 {error_code}: {original_message}"
        
        return f"[{error_info.name}] {error_info.description} - {error_info.user_action}"
    
    def categorize_error(self, error_code: int) -> str:
        """错误分类"""
        error_info = self.get_error_info(error_code)
        return error_info.category if error_info else "unknown"


# 全局错误管理器实例
binance_error_manager = BinanceErrorManager()
