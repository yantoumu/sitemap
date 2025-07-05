"""
特殊sitemap处理器
处理需要特殊逻辑的网站sitemap，如itch.io的游戏sitemap索引
"""

import asyncio
import aiohttp
import xml.etree.ElementTree as ET
from typing import Set, List, Optional
from urllib.parse import urljoin
import logging

try:
    from ..config.schemas import SpecialSitemapConfig
    from ..utils.log_security import LogSecurity
except ImportError:
    # 当作为独立模块运行时的导入
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    from config.schemas import SpecialSitemapConfig
    from utils.log_security import LogSecurity


class SpecialSitemapHandler:
    """特殊sitemap处理器"""
    
    def __init__(self, session: aiohttp.ClientSession):
        """
        初始化特殊处理器
        
        Args:
            session: HTTP会话对象
        """
        self.session = session
        self.logger = logging.getLogger(__name__)
        
        # 注册处理器
        self.handlers = {
            'itch_io_games': self._handle_itch_io_games,
            'game_game_index': self._handle_game_game_index,
            'poki_index': self._handle_poki_index,
            'play_games_index': self._handle_play_games_index,
            'playgame24_index': self._handle_playgame24_index,
            'megaigry_rss': self._handle_megaigry_rss,
            'hahagames_sitemap': self._handle_hahagames_sitemap
        }
    
    async def handle_special_sitemap(self, url: str, config: SpecialSitemapConfig) -> Set[str]:
        """
        处理特殊sitemap
        
        Args:
            url: sitemap URL
            config: 特殊处理配置
            
        Returns:
            Set[str]: 提取的URL集合
        """
        handler = self.handlers.get(config.handler_type)
        if not handler:
            self.logger.error(f"未知的处理器类型: {config.handler_type}")
            return set()
        
        try:
            # 使用安全日志记录，隐藏敏感URL
            safe_url = LogSecurity.sanitize_url(url)
            self.logger.info(f"使用特殊处理器 {config.handler_type} 处理: {LogSecurity.sanitize_url(safe_url)}")
            return await handler(url, config)
        except Exception as e:
            self.logger.error(f"特殊处理器执行失败 {config.handler_type}: {e}")
            return set()
    
    async def _handle_itch_io_games(self, url: str, config: SpecialSitemapConfig) -> Set[str]:
        """
        处理itch.io的游戏sitemap索引
        
        Args:
            url: itch.io sitemap索引URL
            config: 处理配置
            
        Returns:
            Set[str]: 所有游戏URL集合
        """
        # 使用安全日志记录，隐藏敏感URL
        safe_url = LogSecurity.sanitize_url(url)
        self.logger.info(f"🎮 开始处理itch.io游戏sitemap索引: {LogSecurity.sanitize_url(safe_url)}")
        
        try:
            # 1. 获取主sitemap索引
            async with self.session.get(url) as response:
                if response.status != 200:
                    self.logger.error(f"❌ 获取主sitemap失败: {response.status}")
                    return set()
                
                content = await response.text()
                self.logger.info(f"📄 主sitemap大小: {len(content)} 字符")
                
                # 2. 解析主sitemap，提取games相关的子sitemap
                root = ET.fromstring(content)
                
                # 查找所有sitemap元素
                sitemap_elements = (root.findall('.//sitemap') or 
                                  root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}sitemap'))
                
                self.logger.info(f"📋 找到 {len(sitemap_elements)} 个子sitemap")
                
                # 3. 过滤出games相关的sitemap
                games_sitemaps = []
                for sitemap_elem in sitemap_elements:
                    loc_elem = (sitemap_elem.find('loc') or 
                              sitemap_elem.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc'))
                    
                    if loc_elem is not None and loc_elem.text:
                        sitemap_url = loc_elem.text.strip()
                        
                        # 应用包含和排除模式
                        if self._should_include_sitemap(sitemap_url, config):
                            games_sitemaps.append(sitemap_url)
                
                self.logger.info(f"🎯 过滤后的games sitemap数量: {len(games_sitemaps)}")
                
                # 4. 批量处理所有games sitemap
                return await self._process_games_sitemaps(games_sitemaps, config.max_concurrent)
                
        except Exception as e:
            self.logger.error(f"❌ itch.io sitemap处理失败: {e}")
            return set()
    
    async def _handle_game_game_index(self, url: str, config: SpecialSitemapConfig) -> Set[str]:
        """
        处理game-game.com的sitemap索引
        
        Args:
            url: game-game.com sitemap索引URL
            config: 处理配置
            
        Returns:
            Set[str]: 所有游戏URL集合
        """
        # 类似itch.io的处理逻辑，但可能有不同的过滤规则
        return await self._handle_itch_io_games(url, config)
    
    async def _handle_poki_index(self, url: str, config: SpecialSitemapConfig) -> Set[str]:
        """
        处理poki.com的sitemap索引

        Args:
            url: poki.com sitemap索引URL
            config: 处理配置

        Returns:
            Set[str]: 所有游戏URL集合
        """
        # 类似的处理逻辑
        return await self._handle_itch_io_games(url, config)

    async def _handle_play_games_index(self, url: str, config: SpecialSitemapConfig) -> Set[str]:
        """
        处理play-games.com的sitemap索引

        Args:
            url: play-games.com sitemap索引URL
            config: 处理配置

        Returns:
            Set[str]: 所有游戏URL集合
        """
        # 使用安全日志记录，隐藏敏感URL
        safe_url = LogSecurity.sanitize_url(url)
        self.logger.info(f"🎮 开始处理play-games.com sitemap索引: {LogSecurity.sanitize_url(safe_url)}")

        try:
            # 1. 获取主sitemap索引（添加User-Agent避免403错误）
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            async with self.session.get(url, headers=headers) as response:
                if response.status != 200:
                    self.logger.error(f"❌ 获取主sitemap失败: {response.status}")
                    return set()

                content = await response.text()
                self.logger.info(f"📄 主sitemap大小: {len(content)} 字符")

                # 2. 解析主sitemap，提取子sitemap
                root = ET.fromstring(content)

                # 查找所有sitemap元素
                sitemap_elements = (root.findall('.//sitemap') or
                                  root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}sitemap'))

                self.logger.info(f"📋 找到 {len(sitemap_elements)} 个子sitemap")

                # 3. 过滤出符合条件的游戏sitemap
                games_sitemaps = []
                import re

                # 包含模式：只要gamessitemap-数字.xml格式的英文版本
                include_pattern = r'^https://www\.play-games\.com/sitemap/gamessitemap-\d+\.xml$'

                for sitemap_elem in sitemap_elements:
                    loc_elem = (sitemap_elem.find('loc') or
                              sitemap_elem.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc'))

                    if loc_elem is not None and loc_elem.text:
                        sitemap_url = loc_elem.text.strip()

                        # 检查是否匹配包含模式
                        if re.match(include_pattern, sitemap_url):
                            # 进一步检查排除模式（确保没有语言代码）
                            if self._should_include_sitemap(sitemap_url, config):
                                games_sitemaps.append(sitemap_url)
                                # 使用安全日志记录，隐藏敏感URL
                                safe_sitemap_url = LogSecurity.sanitize_url(sitemap_url)
                                self.logger.debug(f"✅ 包含sitemap: {LogSecurity.sanitize_url(LogSecurity.sanitize_url(safe_sitemap_url))}")
                            else:
                                # 使用安全日志记录，隐藏敏感URL
                                safe_sitemap_url = LogSecurity.sanitize_url(sitemap_url)
                                self.logger.debug(f"❌ 排除sitemap: {LogSecurity.sanitize_url(LogSecurity.sanitize_url(safe_sitemap_url))}")
                        else:
                            # 使用安全日志记录，隐藏敏感URL
                            safe_sitemap_url = LogSecurity.sanitize_url(sitemap_url)
                            self.logger.debug(f"🔍 不匹配模式: {LogSecurity.sanitize_url(LogSecurity.sanitize_url(safe_sitemap_url))}")

                self.logger.info(f"🎯 过滤后的游戏sitemap数量: {len(games_sitemaps)}")

                # 显示前几个符合条件的sitemap
                if games_sitemaps:
                    self.logger.info("📋 符合条件的sitemap示例:")
                    for i, sitemap_url in enumerate(games_sitemaps[:5]):
                        self.logger.info(f"  {i+1}. {LogSecurity.sanitize_url(LogSecurity.sanitize_url(sitemap_url))}")

                # 4. 批量处理所有符合条件的游戏sitemap
                if games_sitemaps:
                    return await self._process_games_sitemaps(games_sitemaps, config.max_concurrent)
                else:
                    self.logger.warning("⚠️ 没有找到符合条件的游戏sitemap")
                    return set()

        except Exception as e:
            self.logger.error(f"❌ play-games.com sitemap处理失败: {e}")
            return set()

    async def _handle_playgame24_index(self, url: str, config: SpecialSitemapConfig) -> Set[str]:
        """
        处理playgame24.com的sitemap索引
        只提取特定的两个子sitemap

        Args:
            url: playgame24.com sitemap索引URL
            config: 处理配置

        Returns:
            Set[str]: 所有游戏URL集合
        """
        self.logger.info(f"🎮 开始处理playgame24.com sitemap索引: {LogSecurity.sanitize_url(url)}")

        try:
            # 1. 获取主sitemap索引
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            async with self.session.get(url, headers=headers) as response:
                if response.status != 200:
                    self.logger.error(f"❌ 获取主sitemap失败: {response.status}")
                    return set()

                content = await response.text()
                self.logger.info(f"📄 主sitemap大小: {len(content)} 字符")

                # 2. 解析主sitemap，查找特定的子sitemap
                root = ET.fromstring(content)

                # 查找所有sitemap元素
                sitemap_elements = (root.findall('.//sitemap') or
                                  root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}sitemap'))

                self.logger.info(f"📋 找到 {len(sitemap_elements)} 个子sitemap")

                # 3. 查找特定的两个子sitemap
                target_sitemaps = [
                    "https://playgame24.com/sitemaps/sitemap_0_ru.xml",
                    "https://playgame24.com/sitemaps/sitemap_online_0_ru.xml"
                ]

                found_sitemaps = []

                for sitemap_elem in sitemap_elements:
                    loc_elem = (sitemap_elem.find('loc') or
                              sitemap_elem.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc'))

                    if loc_elem is not None and loc_elem.text:
                        sitemap_url = loc_elem.text.strip()

                        # 检查是否是我们要的特定sitemap
                        if sitemap_url in target_sitemaps:
                            found_sitemaps.append(sitemap_url)
                            self.logger.info(f"✅ 找到目标sitemap: {LogSecurity.sanitize_url(LogSecurity.sanitize_url(sitemap_url))}")
                        else:
                            self.logger.debug(f"🔍 跳过sitemap: {LogSecurity.sanitize_url(LogSecurity.sanitize_url(sitemap_url))}")

                self.logger.info(f"🎯 找到的目标sitemap数量: {len(found_sitemaps)}")

                # 验证是否找到了所有目标sitemap
                missing_sitemaps = set(target_sitemaps) - set(found_sitemaps)
                if missing_sitemaps:
                    self.logger.warning(f"⚠️ 未找到的目标sitemap: {list(missing_sitemaps)}")

                # 4. 批量处理找到的目标sitemap
                if found_sitemaps:
                    return await self._process_games_sitemaps(found_sitemaps, config.max_concurrent)
                else:
                    self.logger.warning("⚠️ 没有找到任何目标sitemap")
                    return set()

        except Exception as e:
            self.logger.error(f"❌ playgame24.com sitemap处理失败: {e}")
            return set()

    async def _handle_megaigry_rss(self, url: str, config: SpecialSitemapConfig) -> Set[str]:
        """
        处理megaigry.ru的RSS feed

        Args:
            url: RSS feed URL
            config: 处理配置

        Returns:
            Set[str]: 提取的游戏URL集合
        """
        self.logger.info(f"📡 开始处理megaigry.ru RSS feed: {LogSecurity.sanitize_url(url)}")

        try:
            # 1. 获取RSS feed内容
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/rss+xml, application/xml, text/xml, */*',
                'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8'
            }

            async with self.session.get(url, headers=headers) as response:
                if response.status != 200:
                    self.logger.error(f"❌ 获取RSS feed失败: {response.status}")
                    return set()

                content = await response.text()
                self.logger.info(f"📄 RSS feed大小: {len(content)} 字符")

                # 2. 解析RSS feed
                import xml.etree.ElementTree as ET
                root = ET.fromstring(content)

                # 查找所有item元素
                items = root.findall('.//item')
                self.logger.info(f"📋 找到 {len(items)} 个RSS条目")

                # 3. 提取游戏URL
                game_urls = set()
                for item in items:
                    # 尝试从link或guid元素获取URL
                    link_elem = item.find('link') or item.find('guid')
                    if link_elem is not None and link_elem.text:
                        url_text = link_elem.text.strip()
                        # 只包含游戏页面URL
                        if '/online-game/' in url_text:
                            game_urls.add(url_text)

                self.logger.info(f"✅ 从RSS feed提取 {LogSecurity.sanitize_url(LogSecurity.sanitize_url(len(game_urls)))} 个游戏URL")

                # 显示前几个URL作为验证
                if game_urls:
                    self.logger.info("📋 提取的游戏URL示例:")
                    for i, game_url in enumerate(list(game_urls)[:5]):
                        self.logger.info(f"  {i+1}. {LogSecurity.sanitize_url(LogSecurity.sanitize_url(game_url))}")

                return game_urls

        except Exception as e:
            self.logger.error(f"❌ megaigry.ru RSS处理失败: {e}")
            return set()

    async def _handle_hahagames_sitemap(self, url: str, config: SpecialSitemapConfig) -> Set[str]:
        """
        处理hahagames.com的sitemap，使用特殊的请求头避免403错误

        Args:
            url: sitemap URL
            config: 处理配置

        Returns:
            Set[str]: 提取的游戏URL集合
        """
        self.logger.info(f"🎮 开始处理hahagames.com sitemap: {LogSecurity.sanitize_url(url)}")

        try:
            # 1. 使用特殊的请求头避免403错误
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Cache-Control': 'max-age=0'
            }

            async with self.session.get(url, headers=headers) as response:
                if response.status != 200:
                    self.logger.error(f"❌ 获取sitemap失败: {response.status}")
                    return set()

                content = await response.text()
                self.logger.info(f"📄 sitemap大小: {len(content)} 字符")

                # 2. 解析sitemap XML
                import xml.etree.ElementTree as ET
                root = ET.fromstring(content)

                # 查找所有URL元素
                url_elements = (root.findall('.//url') or
                              root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}url'))

                self.logger.info(f"📋 找到 {LogSecurity.sanitize_url(len(url_elements))} 个URL元素")

                # 3. 提取游戏相关的URL
                game_urls = set()
                for url_elem in url_elements:
                    # 查找loc元素
                    loc_elem = (url_elem.find('loc') or
                              url_elem.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc'))

                    if loc_elem is not None and loc_elem.text:
                        url_text = loc_elem.text.strip()

                        # 过滤游戏相关的URL，排除语言首页和其他非游戏页面
                        if self._is_hahagames_game_url(url_text):
                            game_urls.add(url_text)

                self.logger.info(f"✅ 从sitemap提取 {LogSecurity.sanitize_url(LogSecurity.sanitize_url(len(game_urls)))} 个游戏URL")

                # 显示前几个URL作为验证
                if game_urls:
                    self.logger.info("📋 提取的游戏URL示例:")
                    for i, game_url in enumerate(list(game_urls)[:5]):
                        self.logger.info(f"  {i+1}. {LogSecurity.sanitize_url(LogSecurity.sanitize_url(game_url))}")

                return game_urls

        except Exception as e:
            self.logger.error(f"❌ hahagames.com sitemap处理失败: {e}")
            return set()

    def _is_hahagames_game_url(self, url: str) -> bool:
        """
        判断是否为hahagames.com的游戏URL

        Args:
            url: 要检查的URL

        Returns:
            bool: 是否为游戏URL
        """
        # 排除语言首页和其他非游戏页面
        exclude_patterns = [
            r'^https://www\.hahagames\.com/$',  # 主页
            r'^https://www\.hahagames\.com/[a-z]{2}$',  # 语言首页 (如 /es, /pt, /de)
            r'^https://www\.hahagames\.com/[a-z]{2}/$',  # 语言首页带斜杠
            r'.*/category/.*',  # 分类页面
            r'.*/tag/.*',       # 标签页面
            r'.*/search.*',     # 搜索页面
            r'.*/about.*',      # 关于页面
            r'.*/contact.*',    # 联系页面
            r'.*/privacy.*',    # 隐私页面
            r'.*/terms.*',      # 条款页面
            r'.*/sitemap.*',    # sitemap页面
            r'.*/robots.*',     # robots页面
        ]

        import re
        for pattern in exclude_patterns:
            if re.match(pattern, url):
                return False

        # 包含游戏相关的URL模式
        include_patterns = [
            r'.*/game/.*',      # 游戏页面
            r'.*/games/.*',     # 游戏列表页面
            r'.*-game$',        # 以-game结尾的URL
            r'.*-games$',       # 以-games结尾的URL
        ]

        for pattern in include_patterns:
            if re.search(pattern, url):
                return True

        # 如果URL包含游戏相关关键词，也认为是游戏URL
        game_keywords = ['play', 'puzzle', 'action', 'adventure', 'racing', 'sports', 'strategy']
        url_lower = url.lower()
        for keyword in game_keywords:
            if keyword in url_lower:
                return True

        return False

    def _should_include_sitemap(self, sitemap_url: str, config: SpecialSitemapConfig) -> bool:
        """
        判断是否应该包含某个sitemap
        
        Args:
            sitemap_url: sitemap URL
            config: 处理配置
            
        Returns:
            bool: 是否应该包含
        """
        import re
        
        # 检查包含模式
        if config.include_patterns:
            included = False
            for pattern in config.include_patterns:
                if re.search(pattern, sitemap_url):
                    included = True
                    break
            if not included:
                return False
        
        # 检查排除模式
        for pattern in config.exclude_patterns:
            if re.search(pattern, sitemap_url):
                return False
        
        return True
    
    async def _process_games_sitemaps(self, sitemap_urls: List[str], max_concurrent: int) -> Set[str]:
        """
        并发处理多个games sitemap
        
        Args:
            sitemap_urls: sitemap URL列表
            max_concurrent: 最大并发数
            
        Returns:
            Set[str]: 所有游戏URL集合
        """
        all_game_urls = set()
        
        # 创建信号量控制并发数
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def process_single_sitemap(sitemap_url: str) -> Set[str]:
            async with semaphore:
                try:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                    }
                    async with self.session.get(sitemap_url, headers=headers) as response:
                        if response.status == 200:
                            content = await response.text()
                            root = ET.fromstring(content)
                            
                            # 提取URL
                            url_elements = (root.findall('.//url') or 
                                          root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}url'))
                            
                            urls = set()
                            for url_elem in url_elements:
                                loc_elem = (url_elem.find('loc') or 
                                          url_elem.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc'))
                                if loc_elem is not None and loc_elem.text:
                                    urls.add(loc_elem.text.strip())
                            
                            self.logger.debug(f"✅ 从 {LogSecurity.sanitize_url(LogSecurity.sanitize_url(sitemap_url))} 提取 {len(urls)} 个URL")
                            return urls
                        else:
                            self.logger.warning(f"❌ 获取sitemap失败 {LogSecurity.sanitize_url(LogSecurity.sanitize_url(sitemap_url))}: {response.status}")
                            return set()
                            
                except Exception as e:
                    self.logger.error(f"❌ 处理sitemap失败 {LogSecurity.sanitize_url(LogSecurity.sanitize_url(sitemap_url))}: {e}")
                    return set()
        
        # 创建并发任务
        tasks = [process_single_sitemap(url) for url in sitemap_urls]
        
        # 执行任务并收集结果
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        processed_count = 0
        failed_count = 0
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                failed_count += 1
                self.logger.error(f"任务失败 {LogSecurity.sanitize_url(LogSecurity.sanitize_url(sitemap_urls[i]))}: {result}")
            else:
                processed_count += 1
                all_game_urls.update(result)
        
        self.logger.info(f"🎉 批量处理完成: 成功 {processed_count}, 失败 {failed_count}, 总URL {LogSecurity.sanitize_url(LogSecurity.sanitize_url(len(all_game_urls)))}")
        
        return all_game_urls
