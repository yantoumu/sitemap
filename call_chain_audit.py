#!/usr/bin/env python3
"""
调用链错误处理和数据完整性审查脚本
"""

import sys
import os
import asyncio
import traceback
sys.path.append('.')

from src.extractors import RuleEngine, KeywordExtractor
from src.data_processor import URLProcessor, DataProcessor
from src.config import ConfigLoader

def audit_extract_keywords_call_chain():
    """审查extract_keywords调用链的错误处理"""
    print("🔍 5. extract_keywords调用链错误处理审查")
    print("=" * 60)
    
    config_loader = ConfigLoader('config/config.yaml', 'config/url_rules.yaml')
    url_rules = config_loader.load_url_rules()
    rule_engine = RuleEngine(url_rules)
    keyword_extractor = KeywordExtractor()
    url_processor = URLProcessor(rule_engine, keyword_extractor)
    
    # 测试各种异常情况
    test_cases = [
        ("", "空URL"),
        ("invalid-url", "无效URL格式"),
        ("https://", "不完整URL"),
        ("https://example.com/", "根目录URL"),
        ("https://example.com/test%20with%20spaces", "包含空格的URL"),
        ("https://example.com/测试中文路径", "中文路径"),
        ("https://example.com/" + "a" * 1000, "超长路径"),
        (None, "None值"),
    ]
    
    print("🧪 异常URL处理测试:")
    error_count = 0
    
    for test_url, description in test_cases:
        try:
            if test_url is None:
                # 测试None值处理
                result = url_processor.extract_all_keywords([None])
            else:
                result = url_processor.extract_all_keywords([test_url])
            
            print(f"   ✅ {description}: 返回 {type(result)} (长度: {len(result)})")
            
            # 验证返回类型
            if not isinstance(result, dict):
                print(f"      ⚠️  返回类型错误: 期望dict，得到{type(result)}")
                error_count += 1
                
        except Exception as e:
            print(f"   ❌ {description}: 异常 {type(e).__name__}: {e}")
            error_count += 1
    
    return error_count

def audit_data_type_conversions():
    """审查数据类型转换过程中的潜在bug"""
    print("\n🔍 6. 数据类型转换审查")
    print("=" * 60)
    
    from src.data_processor import DataProcessor
    
    data_processor = DataProcessor(None, None, None)
    
    # 测试各种数据类型转换
    test_cases = [
        ({}, "空字典"),
        ({"url1": {"keyword1"}}, "正常字典"),
        ({"url1": ["keyword1"]}, "字典值为列表"),
        ({"url1": "keyword1"}, "字典值为字符串"),
        ([], "空列表"),
        (["url1", "url2"], "URL列表"),
        (None, "None值"),
        ("string", "字符串"),
        (123, "数字"),
        ({"url1": None}, "字典值为None"),
    ]
    
    print("🔄 数据类型转换测试:")
    error_count = 0
    
    for test_data, description in test_cases:
        try:
            result = data_processor._validate_and_convert_url_keywords_map(test_data)
            print(f"   ✅ {description}: {type(test_data)} → {type(result)} (长度: {len(result)})")
            
            # 验证结果类型
            if not isinstance(result, dict):
                print(f"      ⚠️  转换失败: 期望dict，得到{type(result)}")
                error_count += 1
                
        except Exception as e:
            print(f"   ❌ {description}: 异常 {type(e).__name__}: {e}")
            error_count += 1
    
    return error_count

def audit_concurrent_processing():
    """审查并发处理中的数据竞争问题"""
    print("\n🔍 7. 并发处理数据一致性审查")
    print("=" * 60)
    
    config_loader = ConfigLoader('config/config.yaml', 'config/url_rules.yaml')
    url_rules = config_loader.load_url_rules()
    rule_engine = RuleEngine(url_rules)
    keyword_extractor = KeywordExtractor()
    url_processor = URLProcessor(rule_engine, keyword_extractor)
    
    # 创建大量测试URL
    test_urls = [f"https://example.com/game/test-game-{i}" for i in range(100)]
    
    print("🔄 并发处理一致性测试:")
    
    try:
        # 多次运行并发提取，检查结果一致性
        results = []
        for run in range(3):
            result = url_processor.extract_all_keywords(test_urls)
            results.append(result)
            print(f"   运行 {run + 1}: 提取到 {len(result)} 个URL的关键词")
        
        # 检查结果一致性
        if len(set(len(r) for r in results)) == 1:
            print("   ✅ 多次运行结果数量一致")
        else:
            print("   ⚠️  多次运行结果数量不一致")
            return 1
        
        # 检查具体内容一致性
        first_result = results[0]
        for i, result in enumerate(results[1:], 2):
            if result == first_result:
                print(f"   ✅ 运行 {i} 与运行 1 结果完全一致")
            else:
                print(f"   ⚠️  运行 {i} 与运行 1 结果不一致")
                return 1
        
    except Exception as e:
        print(f"   ❌ 并发测试异常: {e}")
        return 1
    
    return 0

def audit_data_flow_integrity():
    """审查数据流完整性"""
    print("\n🔍 8. 数据流完整性审查")
    print("=" * 60)
    
    # 模拟完整的数据流
    test_urls = [
        "https://1games.io/game/action-adventure",
        "https://1games.io/game/puzzle-game", 
        "https://1games.io/sitemap.xml",  # 应该被过滤
        "https://azgames.io/play/racing-car",
        "https://azgames.io/category/sports",  # 应该被过滤
    ]
    
    print(f"📊 数据流追踪 (输入: {len(test_urls)} 个URL):")
    
    try:
        config_loader = ConfigLoader('config/config.yaml', 'config/url_rules.yaml')
        url_rules = config_loader.load_url_rules()
        rule_engine = RuleEngine(url_rules)
        keyword_extractor = KeywordExtractor()
        url_processor = URLProcessor(rule_engine, keyword_extractor)
        
        # 步骤1: URL过滤和关键词提取
        url_keywords_map = url_processor.extract_all_keywords(test_urls)
        print(f"   步骤1 - 关键词提取: {len(test_urls)} → {len(url_keywords_map)} 个有效URL")
        
        # 步骤2: 关键词去重
        all_keywords = set()
        for keywords in url_keywords_map.values():
            all_keywords.update(keywords)
        print(f"   步骤2 - 关键词去重: {sum(len(kw) for kw in url_keywords_map.values())} → {len(all_keywords)} 个唯一关键词")
        
        # 步骤3: 数据验证
        data_processor = DataProcessor(None, None, None)
        validated_map = data_processor._validate_and_convert_url_keywords_map(url_keywords_map)
        print(f"   步骤3 - 数据验证: {len(url_keywords_map)} → {len(validated_map)} 个验证通过的URL")
        
        # 检查数据完整性
        if len(validated_map) != len(url_keywords_map):
            print("   ⚠️  数据验证过程中丢失了数据")
            return 1
        
        # 检查关键词映射完整性
        original_keywords = sum(len(kw) for kw in url_keywords_map.values())
        validated_keywords = sum(len(kw) for kw in validated_map.values())
        
        if original_keywords != validated_keywords:
            print(f"   ⚠️  关键词数量不一致: {original_keywords} → {validated_keywords}")
            return 1
        
        print("   ✅ 数据流完整性检查通过")
        
    except Exception as e:
        print(f"   ❌ 数据流测试异常: {e}")
        traceback.print_exc()
        return 1
    
    return 0

def main():
    """主函数"""
    print("🔍 调用链错误处理和数据完整性审查")
    print("=" * 80)
    
    total_issues = 0
    
    try:
        # 5. 调用链错误处理审查
        total_issues += audit_extract_keywords_call_chain()
        
        # 6. 数据类型转换审查
        total_issues += audit_data_type_conversions()
        
        # 7. 并发处理审查
        total_issues += audit_concurrent_processing()
        
        # 8. 数据流完整性审查
        total_issues += audit_data_flow_integrity()
        
        print(f"\n📊 调用链审查总结")
        print("=" * 60)
        print(f"发现问题: {total_issues} 个")
        
        if total_issues == 0:
            print("✅ 调用链错误处理和数据完整性良好")
        else:
            print("⚠️  发现调用链或数据完整性问题")
        
    except Exception as e:
        print(f"❌ 审查过程中发生错误: {e}")
        traceback.print_exc()
        return 1
    
    return total_issues

if __name__ == "__main__":
    sys.exit(main())
