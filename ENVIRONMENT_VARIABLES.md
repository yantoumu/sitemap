# 环境变量配置说明

## 当前必需的环境变量

### 1. 简化后端API (必需)
```bash
# Sitemap关键词提交API地址
SITEMAP_API_URL=http://localhost:5001/api/sitemap/keywords

# Sitemap API认证密钥
SITEMAP_SECRET_KEY=your-secret-key-2024
```

### 2. Sitemap监控 (必需)
```bash
# 要监控的sitemap URL列表（多个URL用逗号分隔）
SITEMAP_URLS=https://site1.com/sitemap.xml,https://site2.com/sitemap.xml,https://site3.com/sitemap.xml
```

### 3. 数据加密 (必需)
```bash
# 数据加密密钥（推荐使用66字符吉利密钥）
ENCRYPTION_KEY=your-66-character-lucky-encryption-key-with-letters-and-numbers
```

## 可选环境变量

### GitHub Actions支持
```bash
# GitHub Actions环境标识 (自动设置)
GITHUB_ACTIONS=true
```

### 开发调试
```bash
# 日志级别 (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL=INFO

# 是否启用调试模式
DEBUG_MODE=false
```

## 已废弃的环境变量

以下环境变量在简化后不再使用，可以从你的 `.env` 文件中删除：

### ❌ SEO API配置 (已移除)
```bash
# SEO查询功能已完全移除，不再需要
SEO_API_URLS=https://k3.seokey.vip,https://ads.seokey.vip
```

### ❌ 原后端API配置 (已替换)
```bash
# 已被 SITEMAP_API_URL 替代
BACKEND_API_URL=https://work.example.com

# 已被 SITEMAP_SECRET_KEY 替代
BACKEND_API_TOKEN=your-backend-api-token-here
```


## 配置文件设置

### 快速开始
1. 复制 `.env.example` 为 `.env`：
   ```bash
   cp .env.example .env
   ```

2. 编辑 `.env` 文件，设置必需的环境变量：
   - `SITEMAP_API_URL`: 你的后端API地址
   - `SITEMAP_SECRET_KEY`: 你的API认证密钥
   - `SITEMAP_URLS`: 要监控的sitemap URL列表（逗号分隔）
   - `ENCRYPTION_KEY`: 66字符的加密密钥

### 密钥生成

使用项目内置工具生成安全的密钥：

```bash
# 生成66字符吉利加密密钥
python -c "from src.utils.crypto import LuckyCrypto; print('ENCRYPTION_KEY=' + LuckyCrypto.generate_lucky_key())"

# 生成API认证密钥
python -c "from src.utils.crypto import CryptoUtils; print('SITEMAP_SECRET_KEY=' + CryptoUtils.generate_api_key())"
```

## 迁移指南

如果你正在从旧版本升级，请按以下步骤迁移：

### 步骤 1: 更新环境变量
```bash
# 旧变量 → 新变量
BACKEND_API_URL → SITEMAP_API_URL
BACKEND_API_TOKEN → SITEMAP_SECRET_KEY
# 删除 SEO_API_URLS (不再需要)
# SITEMAP_URLS 保持不变 (仍然需要)
```

### 步骤 2: 验证配置
```bash
python -c "
from src.config.config import ConfigLoader
loader = ConfigLoader('config/config.yaml', 'config/game_url_rules.yaml')
status = loader.check_env_vars()
print('环境变量检查:', status)
"
```

### 步骤 3: 测试连接
```bash
python -c "
import asyncio
from src.api.simplified_backend_client import SimplifiedBackendClient
async def test(): 
    client = SimplifiedBackendClient()
    result = await client.test_connection()
    print('连接测试:', '成功' if result else '失败')
asyncio.run(test())
"
```

## 安全建议

1. **密钥轮换**: 定期更换 `SITEMAP_SECRET_KEY` 和 `ENCRYPTION_KEY`
2. **访问控制**: 确保只有授权用户可以访问 `.env` 文件
3. **生产环境**: 使用环境变量或密钥管理服务，不要硬编码密钥
4. **监控**: 定期检查API访问日志，确保没有异常访问