# 🗺️ 智能网站地图关键词分析工具

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Security](https://img.shields.io/badge/Security-Hardened-red.svg)](SECURITY_SETUP.md)

一个功能强大的网站地图解析和关键词提取工具，支持多种sitemap格式，具备简化后端API集成和完整的安全防护机制。

## ✨ 核心特性

### 🔍 **智能解析**
- 支持多种sitemap格式：XML、RSS、压缩文件、TXT
- 自动识别sitemap索引和子sitemap
- 特殊网站处理器（itch.io、play-games.com等）
- 智能URL过滤和去重

### 🎯 **关键词提取**
- 基于规则引擎的关键词提取
- 支持任意新域名的规则配置
- 空格分割格式优化
- 智能关键词清理和标准化

### 🔗 **API集成**
- 简化后端API数据提交
- 关键词批量提交支持
- 自动重试和错误处理
- 请求间隔和并发控制

### 🔐 **安全防护**
- 66字符吉利加密存储系统
- 敏感信息环境变量配置
- 日志输出自动脱敏
- 完整的安全加固机制

## 🚀 快速开始

### 1. 环境要求

- Python 3.8+
- pip 包管理器

### 2. 安装依赖

```bash
git clone https://github.com/YOUR_USERNAME/sitemap-keyword-analyzer.git
cd sitemap-keyword-analyzer
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑.env文件，填入实际配置
nano .env
```

**必需的环境变量**：
```bash
# 简化后端API (新架构)
SITEMAP_API_URL=http://localhost:5001/api/sitemap/keywords
SITEMAP_SECRET_KEY=your-secret-key-2024

# Sitemap监控URL列表
SITEMAP_URLS=https://site1.com/sitemap.xml,https://site2.com/sitemap.xml

# 数据加密密钥 (66字符吉利密钥)
ENCRYPTION_KEY=your-66-character-lucky-encryption-key

# 已废弃变量 (不再需要):
# - SEO_API_URLS (SEO查询功能已移除)
# - BACKEND_API_URL (已替换为SITEMAP_API_URL)
# - BACKEND_API_TOKEN (已替换为SITEMAP_SECRET_KEY)
```

### 4. 运行健康检查

```bash
python main.py --health-check
```

### 5. 开始使用

```bash
# 处理默认sitemap列表
python main.py

# 处理指定的sitemap文件
python main.py --sitemaps custom_sitemaps.txt

# 查看帮助信息
python main.py --help
```

## 📁 项目结构

```
sitemap-keyword-analyzer/
├── config/                 # 配置文件
│   ├── config.yaml        # 主配置文件
│   └── game_url_rules.yaml # URL规则配置
├── src/                    # 源代码
│   ├── api/               # API客户端
│   ├── config/            # 配置管理
│   ├── extractors/        # 关键词提取
│   ├── parsers/           # Sitemap解析
│   ├── storage/           # 数据存储
│   └── utils/             # 工具类
├── main.py                # 主程序入口
├── requirements.txt       # 项目依赖
├── .env.example          # 环境变量模板
└── SECURITY_SETUP.md     # 安全配置指南
```

## 🔧 配置说明

### 环境变量配置

| 变量名 | 描述 | 示例 |
|--------|------|------|
| `SITEMAP_API_URL` | 简化后端API地址 | `http://localhost:5001/api/sitemap/keywords` |
| `SITEMAP_SECRET_KEY` | API认证密钥 | `your-secret-key-2024` |
| `SITEMAP_URLS` | 监控的sitemap URL列表 | `https://site1.com/sitemap.xml,https://site2.com/sitemap.xml` |
| `ENCRYPTION_KEY` | 66字符吉利加密密钥 | `your-66-character-lucky-encryption-key` |
| ~~`SEO_API_URLS`~~ | ~~SEO API地址列表~~ | ~~已移除，不再需要~~ |
| ~~`BACKEND_API_URL`~~ | ~~原后端API地址~~ | ~~已替换为SITEMAP_API_URL~~ |
| ~~`BACKEND_API_TOKEN`~~ | ~~原API令牌~~ | ~~已替换为SITEMAP_SECRET_KEY~~ |

### 规则引擎配置

在 `config/game_url_rules.yaml` 中配置URL提取规则：

```yaml
rules:
  - domain: "example.com"
    patterns:
      - "https://example.com/games/{game_name}"
    keyword_extraction:
      - pattern: "/games/([^/]+)"
        transform: "replace_hyphens_with_spaces"
```

## 🛡️ 安全特性

### 🔐 加密存储
- 使用66字符吉利密钥（寓意大吉大利）
- 基于Fernet对称加密算法
- 自动密钥派生和验证

### 📝 日志安全
- 敏感URL自动脱敏显示为 `https://***`
- API密钥和令牌完全隐藏
- 错误信息中无敏感信息泄露

### 🔒 配置安全
- 所有敏感信息通过环境变量配置
- 支持GitHub Secrets集成
- 完整的.gitignore保护

## 📊 使用示例

### 基本用法

```python
from src.parsers.sitemap_parser import SitemapParser
from src.extractors.keyword_extractor import KeywordExtractor

# 解析sitemap
async with aiohttp.ClientSession() as session:
    parser = SitemapParser(session)
    urls = await parser.parse_sitemap("https://example.com/sitemap.xml")

# 提取关键词
extractor = KeywordExtractor()
keywords = extractor.extract_keywords(urls[0])
```

### 批量处理

```python
from main import main

# 使用环境变量中的sitemap列表
await main()
```

## 🔍 健康检查

系统提供完整的健康检查功能：

```bash
python main.py --health-check
```

检查项目：
- ✅ 后端API连接状态
- ✅ SEO API可用性
- ✅ 存储系统状态
- ✅ 配置文件完整性

## 📈 性能特性

- **并发处理**: 支持异步并发sitemap解析
- **智能重试**: 自动重试失败的请求
- **内存优化**: 流式处理大型sitemap文件
- **缓存机制**: 避免重复处理相同URL

## 🤝 贡献指南

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 🆘 支持

- 📖 查看 [SECURITY_SETUP.md](SECURITY_SETUP.md) 了解安全配置
- 📋 查看 [CLEANUP_REPORT.md](CLEANUP_REPORT.md) 了解项目清理情况
- 🐛 [提交Issue](https://github.com/YOUR_USERNAME/sitemap-keyword-analyzer/issues)
- 💬 [讨论区](https://github.com/YOUR_USERNAME/sitemap-keyword-analyzer/discussions)

## 🙏 致谢

感谢所有为这个项目做出贡献的开发者和用户！

---

**⭐ 如果这个项目对您有帮助，请给它一个星标！**
