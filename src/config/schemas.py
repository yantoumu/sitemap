"""
配置数据模型定义
使用Pydantic进行数据验证和类型检查
"""

from pydantic import BaseModel, Field, validator, model_validator
from typing import List, Optional, Dict
from datetime import timedelta


class SpecialSitemapConfig(BaseModel):
    """特殊sitemap处理配置"""
    handler_type: str = Field(..., description="处理器类型: itch_io_games, game_game_index等")
    include_patterns: List[str] = Field(default_factory=list, description="包含的sitemap URL模式")
    exclude_patterns: List[str] = Field(default_factory=list, description="排除的sitemap URL模式")
    max_concurrent: int = Field(default=5, description="最大并发处理数")

    @validator('handler_type')
    def validate_handler_type(cls, v):
        allowed_types = ['itch_io_games', 'game_game_index', 'poki_index', 'play_games_index', 'playgame24_index', 'megaigry_rss', 'hahagames_sitemap']
        if v not in allowed_types:
            raise ValueError(f'处理器类型必须是: {", ".join(allowed_types)}')
        return v


class ExtractRule(BaseModel):
    """URL关键词提取规则"""
    type: str = Field(..., description="提取类型: path_segment, query_param, custom_regex")
    position: Optional[int] = Field(None, description="路径段位置，负数表示从末尾开始")
    param_name: Optional[str] = Field(None, description="查询参数名称")
    regex: Optional[str] = Field(None, description="自定义正则表达式")
    split_chars: Optional[str] = Field("-_", description="分割字符")
    clean_regex: Optional[str] = Field(None, description="清理正则表达式")

    @validator('type')
    def validate_type(cls, v):
        allowed_types = ['path_segment', 'query_param', 'custom_regex']
        if v not in allowed_types:
            raise ValueError(f'提取类型必须是: {", ".join(allowed_types)}')
        return v

    @validator('position')
    def validate_position(cls, v, values):
        if values.get('type') == 'path_segment' and v is None:
            raise ValueError('path_segment类型必须指定position')
        return v

    @validator('param_name')
    def validate_param_name(cls, v, values):
        if values.get('type') == 'query_param' and not v:
            raise ValueError('query_param类型必须指定param_name')
        return v

    @validator('regex')
    def validate_regex(cls, v, values):
        if values.get('type') == 'custom_regex' and not v:
            raise ValueError('custom_regex类型必须指定regex')
        return v


class URLExtractionRule(BaseModel):
    """URL提取规则配置"""
    domain: str = Field(..., description="适用域名")
    description: str = Field(..., description="规则描述")
    patterns: List[str] = Field(..., description="URL匹配模式列表")
    extract_rules: List[ExtractRule] = Field(..., description="关键词提取规则列表")
    exclude_patterns: List[str] = Field(default_factory=list, description="排除模式列表")
    stop_words: List[str] = Field(default_factory=list, description="停用词列表")
    special_sitemap_handler: Optional[SpecialSitemapConfig] = Field(default=None, description="特殊sitemap处理配置")

    @validator('domain')
    def validate_domain(cls, v):
        if not v or not isinstance(v, str):
            raise ValueError('域名不能为空')
        return v.lower().strip()

    @validator('patterns')
    def validate_patterns(cls, v):
        if not v:
            raise ValueError('至少需要一个URL匹配模式')
        return v

    @validator('extract_rules')
    def validate_extract_rules(cls, v):
        if not v:
            raise ValueError('至少需要一个提取规则')
        return v


class SEOAPIConfig(BaseModel):
    """SEO API配置"""
    urls: List[str] = Field(..., description="API端点URL列表")
    interval: float = Field(1.0, description="请求间隔（秒）")
    batch_size: int = Field(5, description="批量查询大小")
    timeout: int = Field(30, description="请求超时时间（秒）")

    @validator('urls')
    def validate_urls(cls, v):
        if not v:
            raise ValueError('至少需要一个API端点')
        for url in v:
            if not url.startswith(('http://', 'https://')):
                raise ValueError(f'无效的API URL: {url}')
        return v

    @validator('interval')
    def validate_interval(cls, v):
        if v < 0.1:
            raise ValueError('请求间隔不能小于0.1秒')
        return v

    @validator('batch_size')
    def validate_batch_size(cls, v):
        if v < 1 or v > 10:
            raise ValueError('批量大小必须在1-10之间')
        return v


class KeywordAPIConfig(BaseModel):
    """关键词批量查询API配置"""
    api_endpoints: List[str] = Field(..., description="API端点URL列表")
    batch_size: int = Field(5, description="每批关键词数量，固定为5")
    interval_seconds: int = Field(60, description="请求间隔时间（秒），生产环境建议60秒")
    timeout_seconds: int = Field(30, description="单个请求超时时间（秒）")
    max_retries: int = Field(3, description="最大重试次数")
    retry_delay: float = Field(5.0, description="重试延迟（秒）")
    test_mode: bool = Field(False, description="测试模式，允许较短的间隔时间")

    @validator('api_endpoints')
    def validate_api_endpoints(cls, v):
        if not v:
            raise ValueError('至少需要一个API端点')
        if len(v) != 2:
            raise ValueError('必须提供恰好2个API端点')
        for url in v:
            if not url.startswith(('http://', 'https://')):
                raise ValueError(f'无效的API URL: {url}')
        return v

    @validator('batch_size')
    def validate_batch_size(cls, v):
        if v != 5:
            raise ValueError('批量大小必须为5')
        return v



    @validator('timeout_seconds')
    def validate_timeout_seconds(cls, v):
        if v < 5 or v > 300:
            raise ValueError('超时时间必须在5-300秒之间')
        return v

    @validator('max_retries')
    def validate_max_retries(cls, v):
        if v < 0 or v > 10:
            raise ValueError('最大重试次数必须在0-10之间')
        return v

    @model_validator(mode='after')
    def validate_config(self):
        """验证配置的整体一致性"""
        if self.test_mode:
            # 测试模式允许1-60秒的间隔
            if self.interval_seconds < 1 or self.interval_seconds > 60:
                raise ValueError('测试模式下请求间隔必须在1-60秒之间')
        else:
            # 生产模式建议60秒间隔，但允许30-120秒的范围
            if self.interval_seconds < 30 or self.interval_seconds > 120:
                raise ValueError('生产模式下请求间隔建议在30-120秒之间')

        return self


class KeywordQueryProgress(BaseModel):
    """关键词查询进度信息"""
    total_keywords: int = Field(..., description="总关键词数量")
    processed_keywords: int = Field(0, description="已处理关键词数量")
    successful_keywords: int = Field(0, description="成功查询的关键词数量")
    failed_keywords: int = Field(0, description="失败的关键词数量")
    current_batch: int = Field(0, description="当前批次号")
    total_batches: int = Field(..., description="总批次数")
    start_time: Optional[str] = Field(None, description="开始时间")
    estimated_completion_time: Optional[str] = Field(None, description="预计完成时间")
    current_api_endpoint: Optional[str] = Field(None, description="当前使用的API端点")

    @property
    def progress_percentage(self) -> float:
        """计算进度百分比"""
        if self.total_keywords == 0:
            return 0.0
        return (self.processed_keywords / self.total_keywords) * 100

    @property
    def success_rate(self) -> float:
        """计算成功率"""
        if self.processed_keywords == 0:
            return 0.0
        return (self.successful_keywords / self.processed_keywords) * 100


class BackendAPIConfig(BaseModel):
    """后端API配置"""
    url: str = Field(..., description="后端API URL")
    auth_token: Optional[str] = Field(None, description="认证令牌")
    batch_size: int = Field(100, description="批量提交大小")
    timeout: int = Field(30, description="请求超时时间（秒）")

    @validator('url')
    def validate_url(cls, v):
        if not v.startswith(('http://', 'https://')):
            raise ValueError(f'无效的后端API URL: {v}')
        return v

    @validator('batch_size')
    def validate_batch_size(cls, v):
        if v < 1 or v > 1000:
            raise ValueError('批量大小必须在1-1000之间')
        return v


class SystemConfig(BaseModel):
    """系统配置"""
    max_concurrent: int = Field(10, description="最大并发数")
    retry_times: int = Field(3, description="重试次数")
    retry_delay: float = Field(1.0, description="重试延迟（秒）")

    @validator('max_concurrent')
    def validate_max_concurrent(cls, v):
        if v < 1 or v > 100:
            raise ValueError('最大并发数必须在1-100之间')
        return v

    @validator('retry_times')
    def validate_retry_times(cls, v):
        if v < 0 or v > 10:
            raise ValueError('重试次数必须在0-10之间')
        return v


class StorageConfig(BaseModel):
    """存储配置"""
    encryption_key: str = Field(..., description="加密密钥")
    storage_file: str = Field("data/processed_urls.json", description="存储文件路径")
    data_retention_days: int = Field(30, description="数据保留天数")

    @validator('encryption_key')
    def validate_encryption_key(cls, v):
        # 支持44字符Fernet密钥和66字符吉利密钥
        if len(v) == 44:
            # 44字符Fernet密钥验证
            try:
                import base64
                base64.urlsafe_b64decode(v.encode())
            except Exception:
                raise ValueError("44字符密钥格式无效，应为有效的Base64编码")
        elif len(v) == 66:
            # 66字符吉利密钥验证
            if not v.isalnum():
                raise ValueError("66字符密钥只能包含字母和数字")
        else:
            raise ValueError("加密密钥长度必须为44字符（Fernet）或66字符（吉利密钥）")
        return v

    @validator('data_retention_days')
    def validate_retention_days(cls, v):
        if v < 1 or v > 365:
            raise ValueError('数据保留天数必须在1-365之间')
        return v


class CacheConfig(BaseModel):
    """缓存配置"""
    ttl: int = Field(604800, description="缓存TTL（秒），默认7天")

    @validator('ttl')
    def validate_ttl(cls, v):
        if v < 60 or v > 2592000:  # 1分钟到30天
            raise ValueError('缓存TTL必须在60-2592000秒之间')
        return v


class LoggingConfig(BaseModel):
    """日志配置"""
    level: str = Field("INFO", description="日志级别")
    format: str = Field(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="日志格式"
    )
    file: str = Field("logs/sitemap_analyzer.log", description="日志文件路径")
    max_size: str = Field("10MB", description="日志文件最大大小")
    backup_count: int = Field(5, description="备份文件数量")

    @validator('level')
    def validate_level(cls, v):
        allowed_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in allowed_levels:
            raise ValueError(f'日志级别必须是: {", ".join(allowed_levels)}')
        return v.upper()


class AppConfig(BaseModel):
    """应用程序总配置"""
    seo_api: SEOAPIConfig
    backend_api: BackendAPIConfig
    system: SystemConfig
    storage: StorageConfig
    cache: CacheConfig
    logging: LoggingConfig

    class Config:
        """Pydantic配置"""
        validate_assignment = True
        extra = "forbid"  # 禁止额外字段
