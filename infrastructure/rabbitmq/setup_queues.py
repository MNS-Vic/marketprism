#!/usr/bin/env python3
"""
MarketPrism RabbitMQ队列和Exchange设置脚本
"""

import requests
import json
import time
import sys

# RabbitMQ配置
RABBITMQ_HOST = "localhost"
RABBITMQ_PORT = 15672
RABBITMQ_USER = "marketprism"
RABBITMQ_PASS = "marketprism_monitor_2024"
RABBITMQ_VHOST = "/monitoring"

# API基础URL
BASE_URL = f"http://{RABBITMQ_HOST}:{RABBITMQ_PORT}/api"

def wait_for_rabbitmq():
    """等待RabbitMQ完全启动"""
    print("等待RabbitMQ启动...")
    for i in range(30):
        try:
            response = requests.get(f"{BASE_URL}/overview", 
                                  auth=(RABBITMQ_USER, RABBITMQ_PASS),
                                  timeout=5)
            if response.status_code == 200:
                print("✅ RabbitMQ已启动")
                return True
        except Exception as e:
            print(f"等待中... ({i+1}/30)")
            time.sleep(2)
    
    print("❌ RabbitMQ启动超时")
    return False

def create_vhost():
    """创建虚拟主机"""
    print(f"创建虚拟主机: {RABBITMQ_VHOST}")
    
    response = requests.put(
        f"{BASE_URL}/vhosts/{RABBITMQ_VHOST.replace('/', '%2F')}",
        auth=(RABBITMQ_USER, RABBITMQ_PASS),
        headers={'Content-Type': 'application/json'}
    )
    
    if response.status_code in [201, 204]:
        print("✅ 虚拟主机创建成功")
    else:
        print(f"❌ 虚拟主机创建失败: {response.status_code}")

def set_permissions():
    """设置用户权限"""
    print("设置用户权限...")
    
    permissions = {
        "configure": ".*",
        "write": ".*", 
        "read": ".*"
    }
    
    response = requests.put(
        f"{BASE_URL}/permissions/{RABBITMQ_VHOST.replace('/', '%2F')}/{RABBITMQ_USER}",
        auth=(RABBITMQ_USER, RABBITMQ_PASS),
        headers={'Content-Type': 'application/json'},
        data=json.dumps(permissions)
    )
    
    if response.status_code in [201, 204]:
        print("✅ 权限设置成功")
    else:
        print(f"❌ 权限设置失败: {response.status_code}")

def create_exchanges():
    """创建Exchange"""
    exchanges = [
        {
            "name": "monitoring.direct",
            "type": "direct",
            "durable": True,
            "auto_delete": False,
            "arguments": {}
        },
        {
            "name": "monitoring.topic", 
            "type": "topic",
            "durable": True,
            "auto_delete": False,
            "arguments": {}
        },
        {
            "name": "monitoring.fanout",
            "type": "fanout",
            "durable": True,
            "auto_delete": False,
            "arguments": {}
        },
        {
            "name": "monitoring.dlx",
            "type": "direct",
            "durable": True,
            "auto_delete": False,
            "arguments": {}
        }
    ]
    
    for exchange in exchanges:
        print(f"创建Exchange: {exchange['name']}")
        
        response = requests.put(
            f"{BASE_URL}/exchanges/{RABBITMQ_VHOST.replace('/', '%2F')}/{exchange['name']}",
            auth=(RABBITMQ_USER, RABBITMQ_PASS),
            headers={'Content-Type': 'application/json'},
            data=json.dumps(exchange)
        )
        
        if response.status_code in [201, 204]:
            print(f"✅ Exchange {exchange['name']} 创建成功")
        else:
            print(f"❌ Exchange {exchange['name']} 创建失败: {response.status_code}")

def create_queues():
    """创建队列"""
    queues = [
        {
            "name": "metrics.prometheus.queue",
            "durable": True,
            "auto_delete": False,
            "arguments": {
                "x-message-ttl": 300000,  # 5分钟TTL
                "x-dead-letter-exchange": "monitoring.dlx",
                "x-dead-letter-routing-key": "metrics.prometheus.dlq"
            }
        },
        {
            "name": "alerts.p1.queue",
            "durable": True,
            "auto_delete": False,
            "arguments": {
                "x-message-ttl": 3600000,  # 1小时TTL
                "x-dead-letter-exchange": "monitoring.dlx",
                "x-dead-letter-routing-key": "alerts.p1.dlq"
            }
        },
        {
            "name": "alerts.p2.queue",
            "durable": True,
            "auto_delete": False,
            "arguments": {
                "x-message-ttl": 1800000,  # 30分钟TTL
                "x-dead-letter-exchange": "monitoring.dlx",
                "x-dead-letter-routing-key": "alerts.p2.dlq"
            }
        },
        {
            "name": "alerts.p3.queue",
            "durable": True,
            "auto_delete": False,
            "arguments": {
                "x-message-ttl": 900000,  # 15分钟TTL
                "x-dead-letter-exchange": "monitoring.dlx",
                "x-dead-letter-routing-key": "alerts.p3.dlq"
            }
        },
        {
            "name": "alerts.p4.queue",
            "durable": True,
            "auto_delete": False,
            "arguments": {
                "x-message-ttl": 600000,  # 10分钟TTL
                "x-dead-letter-exchange": "monitoring.dlx",
                "x-dead-letter-routing-key": "alerts.p4.dlq"
            }
        },
        {
            "name": "dashboard.realtime.queue",
            "durable": True,
            "auto_delete": False,
            "arguments": {
                "x-message-ttl": 60000,  # 1分钟TTL
                "x-dead-letter-exchange": "monitoring.dlx",
                "x-dead-letter-routing-key": "dashboard.realtime.dlq"
            }
        },
        {
            "name": "services.health.queue",
            "durable": True,
            "auto_delete": False,
            "arguments": {
                "x-message-ttl": 120000,  # 2分钟TTL
                "x-dead-letter-exchange": "monitoring.dlx",
                "x-dead-letter-routing-key": "services.health.dlq"
            }
        }
    ]
    
    for queue in queues:
        print(f"创建队列: {queue['name']}")
        
        response = requests.put(
            f"{BASE_URL}/queues/{RABBITMQ_VHOST.replace('/', '%2F')}/{queue['name']}",
            auth=(RABBITMQ_USER, RABBITMQ_PASS),
            headers={'Content-Type': 'application/json'},
            data=json.dumps(queue)
        )
        
        if response.status_code in [201, 204]:
            print(f"✅ 队列 {queue['name']} 创建成功")
        else:
            print(f"❌ 队列 {queue['name']} 创建失败: {response.status_code}")

def create_bindings():
    """创建绑定关系"""
    bindings = [
        {
            "source": "monitoring.topic",
            "destination": "metrics.prometheus.queue",
            "destination_type": "queue",
            "routing_key": "metrics.prometheus.*"
        },
        {
            "source": "monitoring.direct",
            "destination": "alerts.p1.queue",
            "destination_type": "queue",
            "routing_key": "alert.p1"
        },
        {
            "source": "monitoring.direct",
            "destination": "alerts.p2.queue",
            "destination_type": "queue",
            "routing_key": "alert.p2"
        },
        {
            "source": "monitoring.direct",
            "destination": "alerts.p3.queue",
            "destination_type": "queue",
            "routing_key": "alert.p3"
        },
        {
            "source": "monitoring.direct",
            "destination": "alerts.p4.queue",
            "destination_type": "queue",
            "routing_key": "alert.p4"
        },
        {
            "source": "monitoring.fanout",
            "destination": "dashboard.realtime.queue",
            "destination_type": "queue",
            "routing_key": ""
        },
        {
            "source": "monitoring.topic",
            "destination": "services.health.queue",
            "destination_type": "queue",
            "routing_key": "services.health.*"
        }
    ]
    
    for binding in bindings:
        print(f"创建绑定: {binding['source']} -> {binding['destination']}")
        
        response = requests.post(
            f"{BASE_URL}/bindings/{RABBITMQ_VHOST.replace('/', '%2F')}/e/{binding['source']}/q/{binding['destination']}",
            auth=(RABBITMQ_USER, RABBITMQ_PASS),
            headers={'Content-Type': 'application/json'},
            data=json.dumps({"routing_key": binding["routing_key"], "arguments": {}})
        )
        
        if response.status_code in [201, 204]:
            print(f"✅ 绑定 {binding['source']} -> {binding['destination']} 创建成功")
        else:
            print(f"❌ 绑定创建失败: {response.status_code}")

def main():
    """主函数"""
    print("🚀 开始设置MarketPrism RabbitMQ消息架构")
    
    if not wait_for_rabbitmq():
        sys.exit(1)
    
    create_vhost()
    set_permissions()
    create_exchanges()
    create_queues()
    create_bindings()
    
    print("🎉 RabbitMQ消息架构设置完成！")
    print(f"管理界面: http://{RABBITMQ_HOST}:{RABBITMQ_PORT}")
    print(f"用户名: {RABBITMQ_USER}")
    print(f"密码: {RABBITMQ_PASS}")

if __name__ == "__main__":
    main()
