# 使用说明

## 快速开始

### 1. 配置环境变量
```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，设置必需的环境变量
nano .env
```

必需配置：
- `SITEMAP_API_URL` - 后端API地址
- `SITEMAP_SECRET_KEY` - API认证密钥
- `SITEMAP_URLS` - 要监控的sitemap URL列表（逗号分隔）
- `ENCRYPTION_KEY` - 数据加密密钥

### 2. 运行程序

#### 基本用法
```bash
# 处理所有配置的sitemap URL
python main.py

# 试运行模式（不实际提交数据）
python main.py --dry-run

# 启用调试日志
python main.py --log-level DEBUG
```

#### 健康检查
```bash
# 检查所有组件状态
python main.py --health-check
```

#### 创建环境变量模板
```bash
# 生成 .env 文件模板
python main.py --create-env
```

## 命令行选项

```
--config CONFIG       系统配置文件路径 (默认: config/config.yaml)
--rules RULES         URL规则配置文件路径 (默认: config/game_url_rules.yaml)
--sitemaps SITEMAPS   Sitemap列表文件路径 (默认使用环境变量 SITEMAP_URLS)
--log-level LEVEL     日志级别 (DEBUG,INFO,WARNING,ERROR，默认: INFO)
--log-file FILE       日志文件路径 (默认: logs/sitemap_analyzer.log)
--health-check        执行健康检查
--create-env          创建环境变量文件模板
--dry-run             试运行模式，不实际提交数据
```

## 典型工作流程

### 日常处理
```bash
# 1. 健康检查
python main.py --health-check

# 2. 试运行检查
python main.py --dry-run

# 3. 正式处理
python main.py
```

### 调试问题
```bash
# 启用详细日志
python main.py --log-level DEBUG --log-file logs/debug.log

# 查看日志
tail -f logs/debug.log
```

## 输出说明

### 成功运行的输出
```
从环境变量 SITEMAP_URLS 加载了 4 个sitemap URL
开始处理 4 个sitemap

处理结果摘要:
--------------------------------------------------
发现URL总数:     5764
新URL数量:       5749  
保存URL数量:     5745
提交记录数量:    5745
--------------------------------------------------
分析任务完成
```

### 健康检查输出
```
健康检查结果:
----------------------------------------
simplified_backend: ✓ 正常
backend_api    : ✗ 异常 (已废弃，可忽略)
storage        : ✓ 正常
config         : ✓ 正常
----------------------------------------
```

## 故障排除

### 常见问题

1. **连接失败**
   ```
   ❌ 连接测试失败！
   ```
   - 检查 `SITEMAP_API_URL` 是否正确
   - 确认后端服务正在运行
   - 验证 `SITEMAP_SECRET_KEY` 是否正确

2. **环境变量未设置**
   ```
   请在 .env 文件中设置 SITEMAP_URLS 环境变量
   ```
   - 确保 `.env` 文件存在
   - 检查 `SITEMAP_URLS` 是否已配置

3. **解析失败**
   ```
   HTTP错误 403: https://example.com/sitemap.xml
   ```
   - 某些网站可能阻止访问，这是正常的
   - 系统会继续处理其他URL

### 检查日志
```bash
# 查看最新日志
tail -100 logs/sitemap_analyzer.log

# 实时监控日志
tail -f logs/sitemap_analyzer.log
```

## GitHub Actions 自动化

项目支持 GitHub Actions 自动运行，会自动：
- 定期处理配置的sitemap URL
- 提交处理结果到后端
- 更新数据文件

查看 `.github/workflows/schedule.yml` 了解详细配置。