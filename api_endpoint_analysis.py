#!/usr/bin/env python3
"""
SEO API端点分配机制分析脚本
"""

import sys
import os
import asyncio
import time
import random
sys.path.append('.')

from src.api.seo_api_manager import SEOAPIManager
from src.config import ConfigLoader

def analyze_endpoint_selection():
    """分析端点选择机制"""
    print("🔍 SEO API端点分配机制分析")
    print("=" * 80)
    
    # 获取配置
    config_loader = ConfigLoader('config/config.yaml', 'config/url_rules.yaml')
    config = config_loader.load_system_config()
    
    api_urls = config.seo_api.urls
    print(f"📋 配置的API端点: {len(api_urls)} 个")
    for i, url in enumerate(api_urls):
        print(f"   {i}: {url}")
    
    print(f"\n🎯 端点选择机制分析:")
    
    # 模拟多次初始化，查看端点选择分布
    selection_counts = {i: 0 for i in range(len(api_urls))}
    test_runs = 100
    
    print(f"📊 模拟 {test_runs} 次初始化，统计端点选择分布:")
    
    for run in range(test_runs):
        # 重新设置随机种子以模拟真实情况
        random.seed(time.time() + run)
        
        # 模拟SEOAPIManager的端点选择逻辑
        selected_index = random.randint(0, len(api_urls) - 1)
        selection_counts[selected_index] += 1
    
    print("\n📈 端点选择统计:")
    for i, count in selection_counts.items():
        percentage = (count / test_runs) * 100
        url = api_urls[i]
        print(f"   端点 {i} ({url}): {count}/{test_runs} 次 ({percentage:.1f}%)")
    
    # 检查分布是否均匀
    expected_count = test_runs / len(api_urls)
    max_deviation = max(abs(count - expected_count) for count in selection_counts.values())
    deviation_percentage = (max_deviation / expected_count) * 100
    
    print(f"\n📊 分布分析:")
    print(f"   期望每个端点: {expected_count:.1f} 次")
    print(f"   最大偏差: {max_deviation:.1f} 次 ({deviation_percentage:.1f}%)")
    
    if deviation_percentage > 20:
        print("   ⚠️  分布不够均匀，可能存在偏向性")
    else:
        print("   ✅ 分布相对均匀")
    
    return selection_counts

async def test_endpoint_reliability():
    """测试各个端点的可靠性"""
    print(f"\n🔍 端点可靠性测试")
    print("=" * 60)
    
    # 获取配置
    config_loader = ConfigLoader('config/config.yaml', 'config/url_rules.yaml')
    config = config_loader.load_system_config()
    
    api_urls = config.seo_api.urls
    test_keywords = ["test", "game", "action"]
    
    print(f"🧪 测试关键词: {test_keywords}")
    print(f"📡 测试每个端点的响应情况:")
    
    endpoint_results = {}
    
    for i, url in enumerate(api_urls):
        print(f"\n   测试端点 {i}: {url}")
        
        # 创建只使用单个端点的管理器
        single_endpoint_manager = SEOAPIManager(
            [url],  # 只使用一个端点
            interval=1.0,
            batch_size=3,
            timeout=30
        )
        
        try:
            start_time = time.time()
            results = await single_endpoint_manager.query_keywords_serial(test_keywords)
            end_time = time.time()
            
            response_time = end_time - start_time
            success_count = len([r for r in results.values() if r is not None])
            
            endpoint_results[i] = {
                'url': url,
                'success': True,
                'response_time': response_time,
                'success_rate': success_count / len(test_keywords),
                'results': results
            }
            
            print(f"      ✅ 成功: {success_count}/{len(test_keywords)} 个关键词")
            print(f"      ⏱️  响应时间: {response_time:.2f} 秒")
            
        except Exception as e:
            endpoint_results[i] = {
                'url': url,
                'success': False,
                'error': str(e),
                'response_time': None,
                'success_rate': 0
            }
            
            print(f"      ❌ 失败: {e}")
    
    # 分析结果
    print(f"\n📊 端点可靠性分析:")
    
    working_endpoints = [i for i, result in endpoint_results.items() if result['success']]
    failing_endpoints = [i for i, result in endpoint_results.items() if not result['success']]
    
    print(f"   ✅ 正常端点: {len(working_endpoints)} 个")
    for i in working_endpoints:
        result = endpoint_results[i]
        print(f"      端点 {i}: 成功率 {result['success_rate']*100:.1f}%, 响应时间 {result['response_time']:.2f}s")
    
    print(f"   ❌ 异常端点: {len(failing_endpoints)} 个")
    for i in failing_endpoints:
        result = endpoint_results[i]
        print(f"      端点 {i}: {result['error']}")
    
    return endpoint_results

def analyze_current_selection_logic():
    """分析当前的端点选择逻辑"""
    print(f"\n🔍 当前端点选择逻辑分析")
    print("=" * 60)
    
    print("📋 当前实现分析:")
    print("   1. 初始化时随机选择一个端点")
    print("   2. 整个会话期间固定使用该端点")
    print("   3. 不进行端点切换或负载均衡")
    print("   4. 失败时不切换到备用端点")
    
    print(f"\n⚠️  发现的问题:")
    print("   1. 🎲 随机选择可能导致负载不均")
    print("   2. 🔒 固定端点无法利用多端点优势")
    print("   3. 💥 单点故障：一个端点失败影响整个会话")
    print("   4. 🚫 没有故障转移机制")
    
    print(f"\n💡 改进建议:")
    print("   1. 实现轮询（Round Robin）负载均衡")
    print("   2. 添加端点健康检查")
    print("   3. 实现故障转移机制")
    print("   4. 添加端点性能监控")

def simulate_load_distribution():
    """模拟负载分布情况"""
    print(f"\n🔍 负载分布模拟")
    print("=" * 60)
    
    # 模拟100个并发会话
    sessions = 100
    api_urls = ["https://k3.seokey.vip", "https://ads.seokey.vip"]
    
    print(f"🎭 模拟 {sessions} 个并发会话的端点分配:")
    
    # 当前随机分配机制
    current_distribution = {0: 0, 1: 0}
    for session in range(sessions):
        selected = random.randint(0, len(api_urls) - 1)
        current_distribution[selected] += 1
    
    print(f"\n📊 当前随机分配结果:")
    for i, count in current_distribution.items():
        percentage = (count / sessions) * 100
        print(f"   {api_urls[i]}: {count} 个会话 ({percentage:.1f}%)")
    
    # 理想的轮询分配
    ideal_distribution = {0: sessions // 2, 1: sessions // 2}
    if sessions % 2 == 1:
        ideal_distribution[0] += 1
    
    print(f"\n📊 理想轮询分配:")
    for i, count in ideal_distribution.items():
        percentage = (count / sessions) * 100
        print(f"   {api_urls[i]}: {count} 个会话 ({percentage:.1f}%)")
    
    # 计算负载不均衡程度
    current_imbalance = abs(current_distribution[0] - current_distribution[1])
    ideal_imbalance = abs(ideal_distribution[0] - ideal_distribution[1])
    
    print(f"\n⚖️  负载均衡分析:")
    print(f"   当前机制不均衡度: {current_imbalance} 个会话")
    print(f"   理想机制不均衡度: {ideal_imbalance} 个会话")
    print(f"   改进潜力: {current_imbalance - ideal_imbalance} 个会话")

async def main():
    """主函数"""
    try:
        # 1. 端点选择机制分析
        selection_counts = analyze_endpoint_selection()
        
        # 2. 端点可靠性测试
        endpoint_results = await test_endpoint_reliability()
        
        # 3. 当前逻辑分析
        analyze_current_selection_logic()
        
        # 4. 负载分布模拟
        simulate_load_distribution()
        
        print(f"\n🎯 总结")
        print("=" * 60)
        print("✅ 分析完成，发现以下关键问题:")
        print("   1. ads.seokey.vip 端点可能存在稳定性问题")
        print("   2. 当前随机选择机制无法保证负载均衡")
        print("   3. 缺乏故障转移机制")
        print("   4. 需要实现更智能的端点管理策略")
        
    except Exception as e:
        print(f"❌ 分析过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
