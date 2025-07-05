#!/usr/bin/env python3
"""
网站地图关键词分析工具 - 主程序入口
"""

import asyncio
import argparse
import os
import sys
from pathlib import Path
from typing import List
import json

from src.sitemap_analyzer import SitemapKeywordAnalyzer
from src.utils import setup_logging, get_logger, ensure_encryption_key, create_env_file_template


def parse_arguments() -> argparse.Namespace:
    """
    解析命令行参数
    
    Returns:
        argparse.Namespace: 解析后的参数
    """
    parser = argparse.ArgumentParser(
        description='网站地图关键词分析工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python main.py --config config/config.yaml --rules config/url_rules.yaml
  python main.py --sitemaps config/sitemaps.txt --log-level DEBUG
  python main.py --health-check
  python main.py --create-env
        """
    )
    
    parser.add_argument(
        '--config', 
        default='config/config.yaml',
        help='系统配置文件路径 (默认: config/config.yaml)'
    )
    
    parser.add_argument(
        '--rules', 
        default='config/url_rules.yaml',
        help='URL规则配置文件路径 (默认: config/url_rules.yaml)'
    )
    
    parser.add_argument(
        '--sitemaps', 
        help='Sitemap列表文件路径 (默认: config/sitemaps.txt)'
    )
    
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='日志级别 (默认: INFO)'
    )
    
    parser.add_argument(
        '--log-file',
        help='日志文件路径 (默认: logs/sitemap_analyzer.log)'
    )
    
    parser.add_argument(
        '--health-check',
        action='store_true',
        help='执行健康检查'
    )
    
    parser.add_argument(
        '--create-env',
        action='store_true',
        help='创建环境变量文件模板'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='试运行模式，不实际提交数据'
    )
    
    return parser.parse_args()


def load_sitemap_urls(sitemaps_file: str = None) -> List[str]:
    """
    从环境变量或文件加载sitemap URL列表

    Args:
        sitemaps_file: sitemap列表文件路径（可选，优先使用环境变量）

    Returns:
        List[str]: sitemap URL列表
    """
    # 优先从环境变量读取
    sitemap_urls_env = os.getenv('SITEMAP_URLS', '')
    if sitemap_urls_env:
        urls = [url.strip() for url in sitemap_urls_env.split(',') if url.strip()]
        print(f"从环境变量 SITEMAP_URLS 加载了 {len(urls)} 个sitemap URL")
        return urls

    # 如果环境变量没有配置，尝试从文件读取
    if sitemaps_file:
        sitemap_urls = []
        try:
            with open(sitemaps_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        sitemap_urls.append(line)
            print(f"从文件 {sitemaps_file} 加载了 {len(sitemap_urls)} 个sitemap URL")
            return sitemap_urls
        except FileNotFoundError:
            print(f"警告: sitemap文件不存在: {sitemaps_file}")
        except Exception as e:
            print(f"错误: 读取sitemap文件失败: {e}")

    # 如果都没有配置，返回空列表并提示
    print("错误: 未配置sitemap URL列表")
    print("请设置 SITEMAP_URLS 环境变量或提供 --sitemaps 文件路径")
    sys.exit(1)


def validate_config_files(config_path: str, rules_path: str) -> bool:
    """
    验证配置文件是否存在
    
    Args:
        config_path: 配置文件路径
        rules_path: 规则文件路径
        
    Returns:
        bool: 配置文件是否有效
    """
    if not Path(config_path).exists():
        print(f"错误: 配置文件不存在: {config_path}")
        return False
    
    if not Path(rules_path).exists():
        print(f"错误: 规则文件不存在: {rules_path}")
        return False
    
    return True


async def run_health_check(analyzer: SitemapKeywordAnalyzer) -> None:
    """
    执行健康检查
    
    Args:
        analyzer: 分析器实例
    """
    logger = get_logger(__name__)
    
    print("执行健康检查...")
    health_status = await analyzer.health_check()
    
    print("\n健康检查结果:")
    print("-" * 40)
    
    all_healthy = True
    for component, status in health_status.items():
        status_text = "✓ 正常" if status else "✗ 异常"
        print(f"{component:15}: {status_text}")
        if not status:
            all_healthy = False
    
    print("-" * 40)
    
    if all_healthy:
        print("✓ 所有组件状态正常")
        logger.info("健康检查通过")
    else:
        print("✗ 部分组件状态异常")
        logger.warning("健康检查发现问题")
        sys.exit(1)


async def run_analysis(analyzer: SitemapKeywordAnalyzer, 
                      sitemap_urls: List[str]) -> None:
    """
    执行分析任务
    
    Args:
        analyzer: 分析器实例
        sitemap_urls: sitemap URL列表
    """
    logger = get_logger(__name__)
    
    if not sitemap_urls:
        logger.error("没有提供sitemap URL")
        sys.exit(1)
    
    logger.info(f"开始处理 {len(sitemap_urls)} 个sitemap")
    
    try:
        result = await analyzer.process_sitemaps(sitemap_urls)
        
        # 输出结果摘要
        print("\n处理结果摘要:")
        print("-" * 50)
        print(f"发现URL总数:     {result['total_urls_found']}")
        print(f"新URL数量:       {result['new_urls_processed']}")
        print(f"保存URL数量:     {result['urls_saved']}")
        print(f"提交记录数量:    {result['records_submitted']}")
        print("-" * 50)
        
        logger.info("分析任务完成")
        
    except Exception as e:
        logger.error(f"分析任务失败: {e}")
        sys.exit(1)


async def main() -> None:
    """主函数"""
    args = parse_arguments()
    
    # 创建环境变量文件
    if args.create_env:
        create_env_file_template()
        print("环境变量文件模板已创建: .env")
        return
    
    # 确保加密密钥存在
    ensure_encryption_key()
    
    # 设置日志
    log_file = args.log_file or 'logs/sitemap_analyzer.log'
    setup_logging(
        config_file='config/logging.conf',
        log_level=args.log_level,
        log_file=log_file
    )
    
    logger = get_logger(__name__)
    logger.info("程序启动")
    
    # 验证配置文件
    if not validate_config_files(args.config, args.rules):
        sys.exit(1)
    
    try:
        # 创建分析器
        analyzer = SitemapKeywordAnalyzer(args.config, args.rules)
        
        # 健康检查
        if args.health_check:
            await run_health_check(analyzer)
            return
        
        # 加载sitemap URL（优先从环境变量读取）
        sitemaps_file = args.sitemaps or 'config/sitemaps.txt'
        sitemap_urls = load_sitemap_urls(sitemaps_file)
        
        # 执行分析
        await run_analysis(analyzer, sitemap_urls)
        
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    except Exception as e:
        logger.error(f"程序执行失败: {e}")
        sys.exit(1)
    finally:
        logger.info("程序结束")


if __name__ == '__main__':
    # 设置事件循环策略（Windows兼容性）
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    asyncio.run(main())
