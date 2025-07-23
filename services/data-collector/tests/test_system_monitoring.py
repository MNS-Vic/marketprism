#!/usr/bin/env python3
"""
MarketPrism系统资源监控测试脚本
测试新的系统资源监控功能
"""

import sys
import time
import json
from pathlib import Path

# 添加项目路径
sys.path.append(str(Path(__file__).parent))

from external_memory_analysis import find_collector_process, analyze_process_memory


def test_system_resource_monitoring():
    """测试系统资源监控功能"""
    print("🔍 MarketPrism系统资源监控测试")
    print("=" * 80)
    
    # 查找数据收集器进程
    print("\n📋 查找数据收集器进程...")
    proc = find_collector_process()
    
    if not proc:
        print("❌ 未找到运行中的数据收集器进程")
        return False
    
    print(f"✅ 找到进程: PID {proc.pid}")
    
    # 分析当前资源使用情况
    print(f"\n📊 当前系统资源状态:")
    analysis = analyze_process_memory(proc)
    
    if not analysis:
        print("❌ 无法分析进程资源")
        return False
    
    # 显示详细的资源信息
    print(f"物理内存(RSS): {analysis['memory_rss_mb']:.2f} MB")
    print(f"虚拟内存(VMS): {analysis['memory_vms_mb']:.2f} MB")
    print(f"内存占用率: {analysis['memory_percent']:.2f}%")
    print(f"CPU使用率: {analysis['cpu_percent']:.1f}%")
    print(f"运行时间: {analysis['run_time_minutes']:.1f} 分钟")
    print(f"文件描述符: {analysis['num_fds']}")
    print(f"线程数量: {analysis['num_threads']}")
    print(f"网络连接: {analysis['num_connections']} (TCP: {analysis['tcp_connections']})")
    
    # 验证阈值检查
    print(f"\n⚠️  阈值检查:")
    
    # 内存阈值检查
    if analysis['memory_rss_mb'] > 800:
        print(f"🔴 内存使用超过严重阈值 ({analysis['memory_rss_mb']:.1f}MB > 800MB)")
    elif analysis['memory_rss_mb'] > 500:
        print(f"🟡 内存使用超过警告阈值 ({analysis['memory_rss_mb']:.1f}MB > 500MB)")
    else:
        print(f"🟢 内存使用正常 ({analysis['memory_rss_mb']:.1f}MB < 500MB)")
    
    # CPU阈值检查
    if analysis['cpu_percent'] > 80:
        print(f"🔴 CPU使用率超过严重阈值 ({analysis['cpu_percent']:.1f}% > 80%)")
    elif analysis['cpu_percent'] > 60:
        print(f"🟡 CPU使用率超过警告阈值 ({analysis['cpu_percent']:.1f}% > 60%)")
    else:
        print(f"🟢 CPU使用率正常 ({analysis['cpu_percent']:.1f}% < 60%)")
    
    # 文件描述符阈值检查（假设系统限制1024）
    fd_usage_percent = (analysis['num_fds'] / 1024) * 100
    if fd_usage_percent > 85:
        print(f"🔴 文件描述符使用率超过严重阈值 ({fd_usage_percent:.1f}% > 85%)")
    elif fd_usage_percent > 70:
        print(f"🟡 文件描述符使用率超过警告阈值 ({fd_usage_percent:.1f}% > 70%)")
    else:
        print(f"🟢 文件描述符使用率正常 ({fd_usage_percent:.1f}% < 70%)")
    
    # 连接数阈值检查
    if analysis['num_connections'] > 100:
        print(f"🔴 网络连接数超过严重阈值 ({analysis['num_connections']} > 100)")
    elif analysis['num_connections'] > 50:
        print(f"🟡 网络连接数超过警告阈值 ({analysis['num_connections']} > 50)")
    else:
        print(f"🟢 网络连接数正常 ({analysis['num_connections']} < 50)")
    
    # 线程数阈值检查
    if analysis['num_threads'] > 50:
        print(f"🔴 线程数超过严重阈值 ({analysis['num_threads']} > 50)")
    elif analysis['num_threads'] > 20:
        print(f"🟡 线程数超过警告阈值 ({analysis['num_threads']} > 20)")
    else:
        print(f"🟢 线程数正常 ({analysis['num_threads']} < 20)")
    
    # 监控趋势测试
    print(f"\n📈 短期趋势监控测试 (2分钟):")
    samples = []
    
    for i in range(4):  # 4次采样，每30秒一次
        try:
            current_analysis = analyze_process_memory(proc)
            if current_analysis:
                sample = {
                    'timestamp': time.time(),
                    'memory_mb': current_analysis['memory_rss_mb'],
                    'cpu_percent': current_analysis['cpu_percent'],
                    'num_fds': current_analysis['num_fds'],
                    'num_connections': current_analysis['num_connections']
                }
                samples.append(sample)
                
                print(f"[{i+1}/4] 内存: {sample['memory_mb']:6.1f}MB  "
                      f"CPU: {sample['cpu_percent']:5.1f}%  "
                      f"FDs: {sample['num_fds']:3d}  "
                      f"连接: {sample['num_connections']:2d}")
                
                if i < 3:  # 不在最后一次等待
                    time.sleep(30)
            
        except (KeyboardInterrupt, Exception) as e:
            print(f"\n监控被中断: {e}")
            break
    
    # 分析趋势
    if len(samples) >= 2:
        print(f"\n📊 趋势分析:")
        
        # 内存趋势
        memory_start = samples[0]['memory_mb']
        memory_end = samples[-1]['memory_mb']
        memory_change = memory_end - memory_start
        
        if abs(memory_change) < 1.0:
            memory_trend = "稳定"
        elif memory_change > 2.0:
            memory_trend = "快速增长"
        elif memory_change > 0.5:
            memory_trend = "缓慢增长"
        elif memory_change < -0.5:
            memory_trend = "下降"
        else:
            memory_trend = "基本稳定"
        
        print(f"内存趋势: {memory_trend} ({memory_change:+.1f}MB)")
        
        # CPU趋势
        cpu_start = samples[0]['cpu_percent']
        cpu_end = samples[-1]['cpu_percent']
        cpu_change = cpu_end - cpu_start
        
        if abs(cpu_change) < 5.0:
            cpu_trend = "稳定"
        elif cpu_change > 10.0:
            cpu_trend = "快速增长"
        elif cpu_change > 5.0:
            cpu_trend = "缓慢增长"
        else:
            cpu_trend = "基本稳定"
        
        print(f"CPU趋势: {cpu_trend} ({cpu_change:+.1f}%)")
        
        # 文件描述符趋势
        fd_start = samples[0]['num_fds']
        fd_end = samples[-1]['num_fds']
        fd_change = fd_end - fd_start
        
        if abs(fd_change) < 2:
            fd_trend = "稳定"
        elif fd_change > 5:
            fd_trend = "增长"
        else:
            fd_trend = "基本稳定"
        
        print(f"文件描述符趋势: {fd_trend} ({fd_change:+d})")
        
        # 连接数趋势
        conn_start = samples[0]['num_connections']
        conn_end = samples[-1]['num_connections']
        conn_change = conn_end - conn_start
        
        if abs(conn_change) < 1:
            conn_trend = "稳定"
        elif conn_change > 2:
            conn_trend = "增长"
        else:
            conn_trend = "基本稳定"
        
        print(f"连接数趋势: {conn_trend} ({conn_change:+d})")
    
    # 测试结果评估
    print(f"\n✅ 系统资源监控测试结果:")
    
    # 基本功能测试
    basic_tests = [
        ("进程发现", True),
        ("资源数据收集", analysis is not None),
        ("内存监控", analysis['memory_rss_mb'] > 0),
        ("CPU监控", analysis['cpu_percent'] >= 0),
        ("文件描述符监控", analysis['num_fds'] > 0),
        ("网络连接监控", analysis['num_connections'] >= 0),
        ("线程监控", analysis['num_threads'] > 0)
    ]
    
    passed_tests = 0
    for test_name, result in basic_tests:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {test_name}: {status}")
        if result:
            passed_tests += 1
    
    # 阈值检查测试
    threshold_tests = [
        ("内存阈值检查", analysis['memory_rss_mb'] < 1000),  # 不超过最大阈值
        ("CPU阈值检查", analysis['cpu_percent'] < 95),      # 不超过最大阈值
        ("文件描述符检查", analysis['num_fds'] < 1000),      # 合理范围
        ("连接数检查", analysis['num_connections'] < 200),   # 合理范围
        ("线程数检查", analysis['num_threads'] < 100)        # 合理范围
    ]
    
    for test_name, result in threshold_tests:
        status = "✅ 通过" if result else "⚠️  警告"
        print(f"  {test_name}: {status}")
        if result:
            passed_tests += 1
    
    total_tests = len(basic_tests) + len(threshold_tests)
    success_rate = (passed_tests / total_tests) * 100
    
    print(f"\n📊 测试总结:")
    print(f"通过测试: {passed_tests}/{total_tests} ({success_rate:.1f}%)")
    
    if success_rate >= 90:
        print("🎉 系统资源监控功能运行良好！")
        return True
    elif success_rate >= 70:
        print("⚠️  系统资源监控基本正常，但有一些警告")
        return True
    else:
        print("❌ 系统资源监控存在问题，需要检查")
        return False


if __name__ == "__main__":
    try:
        success = test_system_resource_monitoring()
        print("\n" + "=" * 80)
        if success:
            print("测试完成 - 系统资源监控功能正常")
        else:
            print("测试完成 - 发现问题，需要进一步检查")
    except KeyboardInterrupt:
        print("\n测试被用户中断")
    except Exception as e:
        print(f"\n测试异常: {e}")
        import traceback
        traceback.print_exc()
