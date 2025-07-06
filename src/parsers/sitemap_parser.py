"""
Sitemap解析器
支持标准XML sitemap、sitemap index、gzip压缩和递归解析
"""

import aiohttp
import asyncio
from typing import List, Set, Optional
import xml.etree.ElementTree as ET
import gzip
from urllib.parse import urljoin, urlparse
import logging
from io import BytesIO

try:
    from ..config.schemas import SpecialSitemapConfig, URLExtractionRule
    from .special_sitemap_handler import SpecialSitemapHandler
    from ..utils.log_security import LogSecurity
except ImportError:
    # 当作为独立模块运行时的导入
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    from config.schemas import SpecialSitemapConfig, URLExtractionRule
    from parsers.special_sitemap_handler import SpecialSitemapHandler


class SitemapParser:
    """Sitemap解析器"""
    
    def __init__(self, session: aiohttp.ClientSession, max_depth: int = 5):
        """
        初始化Sitemap解析器

        Args:
            session: aiohttp客户端会话
            max_depth: 最大递归深度，防止无限递归
        """
        self.session = session
        self.max_depth = max_depth
        self.logger = logging.getLogger(__name__)
        self.special_handler = SpecialSitemapHandler(session)

        # XML命名空间（支持http和https）
        self.namespaces = {
            'sitemap': 'http://www.sitemaps.org/schemas/sitemap/0.9',
            'sitemapindex': 'http://www.sitemaps.org/schemas/sitemap/0.9',
            'sitemap_https': 'https://www.sitemaps.org/schemas/sitemap/0.9',
            'sitemapindex_https': 'https://www.sitemaps.org/schemas/sitemap/0.9'
        }

    async def parse_sitemap_with_special_handler(self, url: str, special_config: Optional[SpecialSitemapConfig] = None, rule: Optional[URLExtractionRule] = None, depth: int = 0) -> Set[str]:
        """
        使用特殊处理器解析sitemap

        Args:
            url: sitemap URL
            special_config: 特殊处理配置
            rule: URL提取规则（用于过滤）
            depth: 当前递归深度

        Returns:
            Set[str]: 解析出的URL集合
        """
        # 如果有特殊处理配置，使用特殊处理器
        if special_config:
            # 使用安全日志记录，隐藏敏感URL
            safe_url = LogSecurity.sanitize_url(url)
            self.logger.info(f"使用特殊处理器处理sitemap: {safe_url}")
            urls = await self.special_handler.handle_special_sitemap(url, special_config)
        else:
            # 使用标准解析
            urls = await self.parse_sitemap(url, depth)

        # 应用URL过滤规则
        if rule:
            domain = urlparse(url).netloc
            urls = self.apply_url_filters(urls, domain, rule)

        return urls
    
    async def parse_sitemap(self, url: str, depth: int = 0) -> Set[str]:
        """
        解析sitemap，返回URL集合
        
        Args:
            url: sitemap URL
            depth: 当前递归深度
            
        Returns:
            Set[str]: 解析出的URL集合
            
        Raises:
            ValueError: URL格式错误
            aiohttp.ClientError: 网络请求错误
        """
        if depth > self.max_depth:
            safe_url = LogSecurity.sanitize_url(url)
            self.logger.warning(f"达到最大递归深度 {self.max_depth}，跳过: {safe_url}")
            return set()
        
        try:
            # 使用安全日志记录，隐藏敏感URL
            safe_url = LogSecurity.sanitize_url(url)
            self.logger.debug(f"解析sitemap (深度 {depth}): {safe_url}")

            # 检查是否是RSS格式
            if self._is_rss_url(url):
                self.logger.debug(f"检测到RSS格式，使用RSS解析器")
                return await self._parse_rss(url)

            # 下载sitemap内容
            content = await self.download_sitemap(url)
            if not content:
                return set()

            # 检测文件格式
            if url.endswith('.txt') or not content.strip().startswith('<?xml'):
                # TXT格式sitemap
                return self._parse_txt_sitemap(content, url)

            # 解析XML
            root = ET.fromstring(content)

            # 检查是否是RSS格式（通过XML内容判断）
            if self._is_rss_content(root):
                self.logger.info(f"检测到RSS内容，使用RSS解析器")
                return self._parse_rss_content(root, url)

            # 判断是sitemap index还是普通sitemap
            if self._is_sitemap_index(root):
                return await self._parse_sitemap_index(root, url, depth)
            else:
                return self._extract_urls_from_sitemap(root, url)
                
        except ET.ParseError as e:
            safe_url = LogSecurity.sanitize_url(url)
            self.logger.error(f"XML解析错误 {safe_url}: {e}")
            return set()
        except Exception as e:
            # 使用安全日志记录，隐藏敏感URL
            safe_url = LogSecurity.sanitize_url(url)
            self.logger.error(f"解析sitemap失败 {safe_url}: {e}")
            return set()

    def _parse_txt_sitemap(self, content: str, url: str) -> Set[str]:
        """
        解析TXT格式的sitemap

        Args:
            content: TXT内容
            url: sitemap URL

        Returns:
            Set[str]: URL集合
        """
        # 使用安全日志记录，隐藏敏感URL
        safe_url = LogSecurity.sanitize_url(url)
        self.logger.info(f"解析TXT格式sitemap: {safe_url}")

        urls = set()
        lines = content.strip().split('\n')

        for line in lines:
            line = line.strip()
            if line and line.startswith('http'):
                urls.add(line)

        self.logger.info(f"从TXT sitemap提取 {len(urls)} 个URL")
        return urls

    def apply_url_filters(self, urls: Set[str], domain: str, rule: Optional[URLExtractionRule] = None) -> Set[str]:
        """
        应用URL过滤规则

        Args:
            urls: 原始URL集合
            domain: 域名
            rule: URL提取规则（包含排除模式）

        Returns:
            Set[str]: 过滤后的URL集合
        """
        if not rule or not rule.exclude_patterns:
            return urls

        import re
        filtered_urls = set()
        excluded_count = 0

        for url in urls:
            should_exclude = False

            # 检查排除模式
            for pattern in rule.exclude_patterns:
                if re.search(pattern, url):
                    should_exclude = True
                    excluded_count += 1
                    break

            if not should_exclude:
                filtered_urls.add(url)

        self.logger.info(f"URL过滤结果 {domain}: 原始 {len(urls)}, 过滤后 {len(filtered_urls)}, 排除 {excluded_count}")

        # 显示一些被排除的URL示例
        if excluded_count > 0:
            excluded_examples = []
            for url in urls:
                if url not in filtered_urls:
                    excluded_examples.append(url)
                    if len(excluded_examples) >= 3:
                        break

            if excluded_examples:
                self.logger.info(f"排除的URL示例: {excluded_examples}")

        return filtered_urls

    async def download_sitemap(self, url: str) -> Optional[str]:
        """
        下载sitemap内容，支持gzip压缩
        
        Args:
            url: sitemap URL
            
        Returns:
            Optional[str]: XML内容，失败返回None
        """
        try:
            # 检查是否需要特殊处理
            if self._needs_special_headers(url):
                return await self._download_with_special_headers(url)

            async with self.session.get(url, timeout=30) as response:
                if response.status != 200:
                    safe_url = LogSecurity.sanitize_url(url)
                    self.logger.error(f"HTTP错误 {response.status}: {safe_url}")
                    return None
                
                content = await response.read()
                
                # 检查是否为gzip压缩
                if self._is_gzipped(content):
                    try:
                        content = gzip.decompress(content)
                    except gzip.BadGzipFile:
                        safe_url = LogSecurity.sanitize_url(url)
                        self.logger.error(f"gzip解压失败: {safe_url}")
                        return None
                
                # 解码为字符串
                try:
                    return content.decode('utf-8')
                except UnicodeDecodeError:
                    # 尝试其他编码
                    for encoding in ['gbk', 'gb2312', 'latin1']:
                        try:
                            return content.decode(encoding)
                        except UnicodeDecodeError:
                            continue
                    
                    safe_url = LogSecurity.sanitize_url(url)
                    self.logger.error(f"无法解码内容: {safe_url}")
                    return None

        except asyncio.TimeoutError:
            safe_url = LogSecurity.sanitize_url(url)
            self.logger.error(f"请求超时: {safe_url}")
            return None
        except aiohttp.ClientError as e:
            safe_url = LogSecurity.sanitize_url(url)
            self.logger.error(f"网络请求错误 {safe_url}: {e}")
            return None
    
    def _is_gzipped(self, content: bytes) -> bool:
        """
        检查内容是否为gzip压缩
        
        Args:
            content: 字节内容
            
        Returns:
            bool: 是否为gzip压缩
        """
        return content.startswith(b'\x1f\x8b')
    
    def _is_sitemap_index(self, root: ET.Element) -> bool:
        """
        判断是否为sitemap index
        
        Args:
            root: XML根元素
            
        Returns:
            bool: 是否为sitemap index
        """
        # 检查根元素标签
        if root.tag.endswith('sitemapindex'):
            return True
        
        # 检查是否包含sitemap子元素
        sitemap_elements = root.findall('.//sitemap', self.namespaces)
        if not sitemap_elements:
            sitemap_elements = root.findall('.//sitemap')
        
        return len(sitemap_elements) > 0
    
    async def _parse_sitemap_index(self, root: ET.Element, base_url: str, depth: int) -> Set[str]:
        """
        解析sitemap index，递归处理子sitemap
        
        Args:
            root: XML根元素
            base_url: 基础URL
            depth: 当前深度
            
        Returns:
            Set[str]: 所有子sitemap中的URL集合
        """
        all_urls = set()
        
        # 查找所有sitemap元素，处理命名空间
        sitemap_elements = []

        # 尝试使用命名空间查找
        for ns_prefix, ns_uri in self.namespaces.items():
            elements = root.findall(f'.//{{{ns_uri}}}sitemap')
            if elements:
                sitemap_elements.extend(elements)
                break

        # 如果命名空间查找失败，尝试不使用命名空间
        if not sitemap_elements:
            sitemap_elements = root.findall('.//sitemap')
        
        self.logger.info(f"发现 {len(sitemap_elements)} 个子sitemap")
        
        # 创建并发任务
        tasks = []
        for sitemap_elem in sitemap_elements:
            # 尝试查找loc元素，处理命名空间
            loc_elem = None

            # 尝试使用命名空间查找
            for ns_prefix, ns_uri in self.namespaces.items():
                loc_elem = sitemap_elem.find(f'{{{ns_uri}}}loc')
                if loc_elem is not None:
                    break

            # 如果命名空间查找失败，尝试不使用命名空间
            if loc_elem is None:
                loc_elem = sitemap_elem.find('loc')
            
            if loc_elem is not None and loc_elem.text:
                sitemap_url = self._resolve_url(loc_elem.text.strip(), base_url)
                task = self.parse_sitemap(sitemap_url, depth + 1)
                tasks.append(task)
        
        # 并发执行所有任务
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, Exception):
                    self.logger.error(f"子sitemap解析失败: {result}")
                elif isinstance(result, set):
                    all_urls.update(result)
        
        return all_urls
    
    def _extract_urls_from_sitemap(self, root: ET.Element, base_url: str) -> Set[str]:
        """
        从普通sitemap中提取URL
        
        Args:
            root: XML根元素
            base_url: 基础URL
            
        Returns:
            Set[str]: URL集合
        """
        urls = set()
        
        # 查找所有url元素，智能处理命名空间
        url_elements = []

        # 首先尝试从根元素自动检测命名空间
        detected_namespace = None
        if root.tag.startswith('{'):
            # 提取命名空间
            detected_namespace = root.tag[1:root.tag.find('}')]

        # 如果检测到命名空间，优先使用
        if detected_namespace:
            url_elements = root.findall(f'.//{{{detected_namespace}}}url')

        # 如果没有找到，尝试预定义的命名空间
        if not url_elements:
            for ns_prefix, ns_uri in self.namespaces.items():
                elements = root.findall(f'.//{{{ns_uri}}}url')
                if elements:
                    url_elements.extend(elements)
                    detected_namespace = ns_uri
                    break

        # 如果命名空间查找失败，尝试不使用命名空间
        if not url_elements:
            url_elements = root.findall('.//url')
        
        for url_elem in url_elements:
            # 尝试查找loc元素，智能处理命名空间
            loc_elem = None

            # 优先使用检测到的命名空间
            if detected_namespace:
                loc_elem = url_elem.find(f'{{{detected_namespace}}}loc')

            # 如果没有找到，尝试预定义的命名空间
            if loc_elem is None:
                for ns_prefix, ns_uri in self.namespaces.items():
                    loc_elem = url_elem.find(f'{{{ns_uri}}}loc')
                    if loc_elem is not None:
                        break

            # 如果命名空间查找失败，尝试不使用命名空间
            if loc_elem is None:
                loc_elem = url_elem.find('loc')
            
            if loc_elem is not None and loc_elem.text:
                url = self._resolve_url(loc_elem.text.strip(), base_url)
                if self._is_valid_url(url):
                    urls.add(url)
        
        self.logger.info(f"从sitemap提取 {len(urls)} 个URL")
        return urls
    
    def _resolve_url(self, url: str, base_url: str) -> str:
        """
        解析相对URL为绝对URL
        
        Args:
            url: 待解析的URL
            base_url: 基础URL
            
        Returns:
            str: 绝对URL
        """
        return urljoin(base_url, url)
    
    def _is_valid_url(self, url: str) -> bool:
        """
        验证URL是否有效

        Args:
            url: 待验证的URL

        Returns:
            bool: URL是否有效
        """
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False

    def _is_rss_url(self, url: str) -> bool:
        """
        检查URL是否是RSS格式

        Args:
            url: 待检查的URL

        Returns:
            bool: 是否是RSS URL
        """
        url_lower = url.lower()
        return (
            '/rss' in url_lower or
            url_lower.endswith('/rss/') or
            url_lower.endswith('.rss') or
            'feed' in url_lower
        )

    def _is_rss_content(self, root: ET.Element) -> bool:
        """
        检查XML内容是否是RSS格式

        Args:
            root: XML根元素

        Returns:
            bool: 是否是RSS内容
        """
        return (
            root.tag.lower() == 'rss' or
            root.tag.lower() == 'feed' or
            'rss' in root.tag.lower()
        )

    async def _parse_rss(self, rss_url: str) -> Set[str]:
        """
        解析RSS格式的URL

        Args:
            rss_url: RSS URL

        Returns:
            Set[str]: 提取到的URL集合
        """
        try:
            content = await self.download_sitemap(rss_url)
            if not content:
                return set()

            root = ET.fromstring(content)
            return self._parse_rss_content(root, rss_url)

        except Exception as e:
            self.logger.error(f"RSS解析失败 {rss_url}: {e}")
            return set()

    def _parse_rss_content(self, root: ET.Element, base_url: str) -> Set[str]:
        """
        解析RSS内容提取URL

        Args:
            root: RSS XML根元素
            base_url: 基础URL

        Returns:
            Set[str]: 提取到的URL集合
        """
        urls = set()

        try:
            # RSS 2.0格式
            if root.tag.lower() == 'rss':
                items = root.findall('.//item')
                for item in items:
                    # 尝试从不同字段提取URL
                    link_elem = item.find('link')
                    guid_elem = item.find('guid')

                    if link_elem is not None and link_elem.text:
                        url = link_elem.text.strip()
                        if self._is_valid_url(url):
                            urls.add(url)
                    elif guid_elem is not None and guid_elem.text:
                        # 有些RSS使用guid作为URL
                        url = guid_elem.text.strip()
                        if self._is_valid_url(url):
                            urls.add(url)

            # Atom格式
            elif 'feed' in root.tag.lower():
                entries = root.findall('.//{http://www.w3.org/2005/Atom}entry')
                for entry in entries:
                    link_elem = entry.find('.//{http://www.w3.org/2005/Atom}link')
                    if link_elem is not None:
                        href = link_elem.get('href')
                        if href and self._is_valid_url(href):
                            urls.add(href)

            # 使用安全日志记录，隐藏敏感URL
            safe_url = LogSecurity.sanitize_url(base_url)
            self.logger.info(f"RSS解析完成: {safe_url}, 提取到 {len(urls)} 个URL")

        except Exception as e:
            self.logger.error(f"RSS内容解析失败 {base_url}: {e}")

        return urls

    def _needs_special_headers(self, url: str) -> bool:
        """
        检查URL是否需要特殊的HTTP头处理

        Args:
            url: 待检查的URL

        Returns:
            bool: 是否需要特殊处理
        """
        domain = url.lower()
        special_domains = [
            'gamesgames.com',
            'spel.nl',
            'girlsgogames.it',
            'games.co.id',
            'agame.com'
        ]

        return any(special_domain in domain for special_domain in special_domains)

    async def _download_with_special_headers(self, url: str) -> Optional[str]:
        """
        使用特殊HTTP头下载sitemap

        Args:
            url: sitemap URL

        Returns:
            Optional[str]: sitemap内容，失败返回None
        """
        # 尝试不同的HTTP头配置
        header_configs = [
            {
                "User-Agent": "Googlebot/2.1 (+http://www.google.com/bot.html)",
                "Accept": "*/*",
                "Accept-Encoding": "gzip, deflate"
            },
            {
                "User-Agent": "Mozilla/5.0 (compatible; Bingbot/2.0; +http://www.bing.com/bingbot.htm)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Encoding": "gzip, deflate"
            },
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1"
            }
        ]

        for i, headers in enumerate(header_configs):
            try:
                safe_url = LogSecurity.sanitize_url(url)
                self.logger.info(f"尝试特殊配置 {i+1}/{len(header_configs)}: {safe_url}")

                timeout = aiohttp.ClientTimeout(total=30)
                async with aiohttp.ClientSession(headers=headers, timeout=timeout) as special_session:
                    async with special_session.get(url) as response:
                        if response.status == 200:
                            content = await response.read()

                            # 处理gzip压缩
                            if self._is_gzipped(content):
                                try:
                                    content = gzip.decompress(content)
                                except gzip.BadGzipFile:
                                    safe_url = LogSecurity.sanitize_url(url)
                                    self.logger.error(f"gzip解压失败: {safe_url}")
                                    continue

                            # 解码为字符串
                            try:
                                result = content.decode('utf-8')
                                safe_url = LogSecurity.sanitize_url(url)
                                self.logger.info(f"特殊配置 {i+1} 成功: {safe_url}")
                                return result
                            except UnicodeDecodeError:
                                # 尝试其他编码
                                for encoding in ['gbk', 'gb2312', 'latin1']:
                                    try:
                                        result = content.decode(encoding)
                                        safe_url = LogSecurity.sanitize_url(url)
                                        self.logger.info(f"特殊配置 {i+1} 成功 (编码 {encoding}): {safe_url}")
                                        return result
                                    except UnicodeDecodeError:
                                        continue
                        else:
                            safe_url = LogSecurity.sanitize_url(url)
                            self.logger.warning(f"特殊配置 {i+1} HTTP错误 {response.status}: {safe_url}")

            except Exception as e:
                safe_url = LogSecurity.sanitize_url(url)
                self.logger.warning(f"特殊配置 {i+1} 失败 {safe_url}: {e}")
                continue

        safe_url = LogSecurity.sanitize_url(url)
        self.logger.error(f"所有特殊配置都失败: {safe_url}")
        return None


class SitemapParserFactory:
    """Sitemap解析器工厂类"""
    
    @staticmethod
    def create_parser(max_depth: int = 5, timeout: int = 30) -> SitemapParser:
        """
        创建Sitemap解析器实例
        
        Args:
            max_depth: 最大递归深度
            timeout: 请求超时时间
            
        Returns:
            SitemapParser: 解析器实例
        """
        # 创建aiohttp会话
        timeout_config = aiohttp.ClientTimeout(total=timeout)
        session = aiohttp.ClientSession(timeout=timeout_config)
        
        return SitemapParser(session, max_depth)
        """
        检查XML内容是否是RSS格式

        Args:
            root: XML根元素

        Returns:
            bool: 是否是RSS内容
        """
        return (
            root.tag.lower() == 'rss' or
            root.tag.lower() == 'feed' or
            'rss' in root.tag.lower()
        )

    async def _parse_rss(self, rss_url: str) -> Set[str]:
        """
        解析RSS格式的URL

        Args:
            rss_url: RSS URL

        Returns:
            Set[str]: 提取到的URL集合
        """
        try:
            content = await self.download_sitemap(rss_url)
            if not content:
                return set()

            root = ET.fromstring(content)
            return self._parse_rss_content(root, rss_url)

        except Exception as e:
            self.logger.error(f"RSS解析失败 {rss_url}: {e}")
            return set()

    def _parse_rss_content(self, root: ET.Element, base_url: str) -> Set[str]:
        """
        解析RSS内容提取URL

        Args:
            root: RSS XML根元素
            base_url: 基础URL

        Returns:
            Set[str]: 提取到的URL集合
        """
        urls = set()

        try:
            # RSS 2.0格式
            if root.tag.lower() == 'rss':
                items = root.findall('.//item')
                for item in items:
                    # 尝试从不同字段提取URL
                    link_elem = item.find('link')
                    guid_elem = item.find('guid')

                    if link_elem is not None and link_elem.text:
                        url = link_elem.text.strip()
                        if self._is_valid_url(url):
                            urls.add(url)
                    elif guid_elem is not None and guid_elem.text:
                        # 有些RSS使用guid作为URL
                        url = guid_elem.text.strip()
                        if self._is_valid_url(url):
                            urls.add(url)

            # Atom格式
            elif 'feed' in root.tag.lower():
                entries = root.findall('.//{http://www.w3.org/2005/Atom}entry')
                for entry in entries:
                    link_elem = entry.find('.//{http://www.w3.org/2005/Atom}link')
                    if link_elem is not None:
                        href = link_elem.get('href')
                        if href and self._is_valid_url(href):
                            urls.add(href)

            # 使用安全日志记录，隐藏敏感URL
            safe_url = LogSecurity.sanitize_url(base_url)
            self.logger.info(f"RSS解析完成: {safe_url}, 提取到 {len(urls)} 个URL")

        except Exception as e:
            self.logger.error(f"RSS内容解析失败 {base_url}: {e}")

        return urls

    def _needs_special_headers(self, url: str) -> bool:
        """
        检查URL是否需要特殊的HTTP头处理

        Args:
            url: 待检查的URL

        Returns:
            bool: 是否需要特殊处理
        """
        domain = url.lower()
        special_domains = [
            'gamesgames.com',
            'spel.nl',
            'girlsgogames.it',
            'games.co.id',
            'agame.com'
        ]

        return any(special_domain in domain for special_domain in special_domains)

    async def _download_with_special_headers(self, url: str) -> Optional[str]:
        """
        使用特殊HTTP头下载sitemap

        Args:
            url: sitemap URL

        Returns:
            Optional[str]: sitemap内容，失败返回None
        """
        # 尝试不同的HTTP头配置
        header_configs = [
            {
                "User-Agent": "Googlebot/2.1 (+http://www.google.com/bot.html)",
                "Accept": "*/*",
                "Accept-Encoding": "gzip, deflate"
            },
            {
                "User-Agent": "Mozilla/5.0 (compatible; Bingbot/2.0; +http://www.bing.com/bingbot.htm)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Encoding": "gzip, deflate"
            },
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1"
            }
        ]

        for i, headers in enumerate(header_configs):
            try:
                safe_url = LogSecurity.sanitize_url(url)
                self.logger.info(f"尝试特殊配置 {i+1}/{len(header_configs)}: {safe_url}")

                timeout = aiohttp.ClientTimeout(total=30)
                async with aiohttp.ClientSession(headers=headers, timeout=timeout) as special_session:
                    async with special_session.get(url) as response:
                        if response.status == 200:
                            content = await response.read()

                            # 处理gzip压缩
                            if self._is_gzipped(content):
                                try:
                                    content = gzip.decompress(content)
                                except gzip.BadGzipFile:
                                    safe_url = LogSecurity.sanitize_url(url)
                                    self.logger.error(f"gzip解压失败: {safe_url}")
                                    continue

                            # 解码为字符串
                            try:
                                result = content.decode('utf-8')
                                safe_url = LogSecurity.sanitize_url(url)
                                self.logger.info(f"特殊配置 {i+1} 成功: {safe_url}")
                                return result
                            except UnicodeDecodeError:
                                # 尝试其他编码
                                for encoding in ['gbk', 'gb2312', 'latin1']:
                                    try:
                                        result = content.decode(encoding)
                                        safe_url = LogSecurity.sanitize_url(url)
                                        self.logger.info(f"特殊配置 {i+1} 成功 (编码 {encoding}): {safe_url}")
                                        return result
                                    except UnicodeDecodeError:
                                        continue
                        else:
                            safe_url = LogSecurity.sanitize_url(url)
                            self.logger.warning(f"特殊配置 {i+1} HTTP错误 {response.status}: {safe_url}")

            except Exception as e:
                safe_url = LogSecurity.sanitize_url(url)
                self.logger.warning(f"特殊配置 {i+1} 失败 {safe_url}: {e}")
                continue

        safe_url = LogSecurity.sanitize_url(url)
        self.logger.error(f"所有特殊配置都失败: {safe_url}")
        return None
