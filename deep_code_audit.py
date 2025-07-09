#!/usr/bin/env python3
"""
深度代码审查脚本 - 检查关键词过滤系统的潜在问题
"""

import sys
import os
import re
sys.path.append('.')

from src.extractors import RuleEngine, KeywordExtractor, KeywordProcessor
from src.config import ConfigLoader
from urllib.parse import urlparse

def audit_exclude_patterns():
    """审查URL排除模式是否过于严格"""
    print("🔍 1. URL排除模式审查")
    print("=" * 60)
    
    config_loader = ConfigLoader('config/config.yaml', 'config/url_rules.yaml')
    url_rules = config_loader.load_url_rules()
    rule_engine = RuleEngine(url_rules)
    
    # 获取默认规则的排除模式
    default_rule = rule_engine.default_rule
    exclude_patterns = default_rule.exclude_patterns
    
    print("📋 默认排除模式:")
    for i, pattern in enumerate(exclude_patterns, 1):
        print(f"   {i:2d}. {pattern}")
    
    # 测试可能被误杀的游戏URL
    test_game_urls = [
        "https://example.com/game/action-adventure",  # 正常游戏页面
        "https://example.com/category/action",        # 可能有价值的分类页面
        "https://example.com/tag/multiplayer",        # 可能有价值的标签页面
        "https://example.com/games/",                 # 目录页面（被排除）
        "https://example.com/page/2",                 # 分页（被排除）
        "https://example.com/api/games",              # API（被排除）
        "https://example.com/admin/games",            # 管理页面（被排除）
        "https://example.com/css/game-style.css",     # 静态资源（被排除）
    ]
    
    print("\n🎯 测试游戏URL过滤结果:")
    potentially_valuable_filtered = []
    
    for url in test_game_urls:
        parsed_url = urlparse(url)
        path = parsed_url.path
        
        excluded = False
        matching_pattern = None
        
        for pattern in exclude_patterns:
            if re.search(pattern, path):
                excluded = True
                matching_pattern = pattern
                break
        
        status = "❌ 被排除" if excluded else "✅ 通过"
        print(f"   {status}: {url}")
        if excluded:
            print(f"      匹配模式: {matching_pattern}")
            # 检查是否可能误杀有价值内容
            if any(keyword in url.lower() for keyword in ['game', 'play', 'action', 'adventure']):
                if 'category' in matching_pattern or 'tag' in matching_pattern:
                    potentially_valuable_filtered.append((url, matching_pattern))
    
    if potentially_valuable_filtered:
        print("\n⚠️  可能误杀的有价值URL:")
        for url, pattern in potentially_valuable_filtered:
            print(f"   • {url} (被模式 {pattern} 排除)")
    
    return len(potentially_valuable_filtered)

def audit_stop_words():
    """审查停用词列表是否包含游戏相关有效关键词"""
    print("\n🔍 2. 停用词列表审查")
    print("=" * 60)
    
    processor = KeywordProcessor()
    
    # 获取默认停用词
    default_stop_words = processor.default_stop_words
    
    # 游戏相关可能有价值的词汇
    game_related_words = {
        'game', 'games', 'play', 'online', 'free', 'action', 'adventure', 
        'puzzle', 'strategy', 'racing', 'sports', 'arcade', 'rpg', 'fps',
        'multiplayer', 'single', 'player', 'mobile', 'html5', 'flash',
        'io', 'battle', 'war', 'fight', 'run', 'jump', 'shoot', 'drive'
    }
    
    # 检查哪些游戏词汇被列为停用词
    problematic_stop_words = game_related_words.intersection(default_stop_words)
    
    print(f"📊 默认停用词总数: {len(default_stop_words)}")
    print(f"🎮 游戏相关测试词汇: {len(game_related_words)}")
    print(f"⚠️  被误列为停用词的游戏词汇: {len(problematic_stop_words)}")
    
    if problematic_stop_words:
        print("\n❌ 可能误删的游戏关键词:")
        for word in sorted(problematic_stop_words):
            print(f"   • '{word}' - 可能是有价值的游戏类型/特征词")
    
    # 测试具体的游戏关键词提取
    test_keywords = {
        'action adventure', 'puzzle game', 'racing car', 'online multiplayer',
        'free games', 'html5 game', 'io games', 'battle royale'
    }
    
    print(f"\n🧪 测试关键词过滤:")
    for keyword in test_keywords:
        words = keyword.split()
        filtered_words = [w for w in words if w not in default_stop_words]
        result = ' '.join(filtered_words)
        
        if len(filtered_words) < len(words):
            removed = [w for w in words if w in default_stop_words]
            print(f"   '{keyword}' → '{result}' (移除: {removed})")
        else:
            print(f"   '{keyword}' → '{result}' (无变化)")
    
    return len(problematic_stop_words)

def audit_keyword_length_limits():
    """审查关键词长度限制是否合理"""
    print("\n🔍 3. 关键词长度限制审查")
    print("=" * 60)
    
    processor = KeywordProcessor()
    
    # 测试各种长度的游戏关键词
    test_cases = [
        ("a", "单字符"),
        ("io", "2字符"),
        ("rpg", "3字符缩写"),
        ("action", "6字符常见词"),
        ("multiplayer", "11字符"),
        ("action adventure game", "21字符组合"),
        ("super mario bros world championship", "34字符长游戏名"),
        ("the legend of zelda breath of the wild special edition", "54字符超长名称"),
        ("a" * 60, "60字符超长测试")
    ]
    
    print("📏 长度限制测试 (当前限制: 1-50字符):")
    problematic_cases = []
    
    for keyword, description in test_cases:
        is_valid = processor.validate_keyword(keyword)
        normalized = processor.normalize_keyword(keyword)
        
        status = "✅ 有效" if is_valid else "❌ 无效"
        print(f"   {status}: '{keyword}' ({len(keyword)}字符) - {description}")
        
        if not is_valid and len(keyword) > 1 and len(keyword) <= 60:
            if any(game_word in keyword.lower() for game_word in ['game', 'mario', 'zelda', 'action']):
                problematic_cases.append((keyword, description))
    
    if problematic_cases:
        print(f"\n⚠️  可能过于严格的长度限制案例:")
        for keyword, description in problematic_cases:
            print(f"   • '{keyword}' - {description}")
    
    return len(problematic_cases)

def audit_deduplication_mechanism():
    """审查关键词去重机制"""
    print("\n🔍 4. 关键词去重机制审查")
    print("=" * 60)
    
    processor = KeywordProcessor()
    
    # 测试边界情况
    test_cases = [
        {"Action Adventure", "action adventure", "ACTION ADVENTURE"},  # 大小写
        {"racing-car", "racing car", "racing_car"},                    # 分隔符
        {"puzzle game", "puzzle  game", "puzzle\tgame"},               # 空白字符
        {"RPG Game", "rpg game", "Rpg Game"},                          # 混合大小写
        {"io games", "IO Games", "Io Games"},                          # 缩写大小写
    ]
    
    print("🔄 去重机制测试:")
    for i, test_set in enumerate(test_cases, 1):
        print(f"\n   测试组 {i}: {test_set}")
        
        # 标准化处理
        normalized_set = set()
        for keyword in test_set:
            normalized = processor.normalize_keyword(keyword)
            if normalized:
                normalized_set.add(normalized)
        
        print(f"   去重后: {normalized_set}")
        print(f"   去重效果: {len(test_set)} → {len(normalized_set)}")
        
        if len(normalized_set) > 1:
            print(f"   ⚠️  去重不完全，可能存在重复")
    
    return 0

def main():
    """主函数"""
    print("🔍 Sitemap处理系统深度代码审查")
    print("=" * 80)
    
    issues_found = 0
    
    try:
        # 1. URL排除模式审查
        issues_found += audit_exclude_patterns()
        
        # 2. 停用词审查
        issues_found += audit_stop_words()
        
        # 3. 长度限制审查
        issues_found += audit_keyword_length_limits()
        
        # 4. 去重机制审查
        issues_found += audit_deduplication_mechanism()
        
        print(f"\n📊 审查总结")
        print("=" * 60)
        print(f"发现潜在问题: {issues_found} 个")
        
        if issues_found == 0:
            print("✅ 未发现明显的过度过滤问题")
        else:
            print("⚠️  建议检查上述问题，可能导致有价值数据丢失")
        
    except Exception as e:
        print(f"❌ 审查过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
