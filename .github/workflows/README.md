# GitHub Actions 工作流说明

本目录包含了网站地图关键词分析工具的自动化工作流配置。

## 工作流概览

### 主要分析任务 (`schedule.yml`)

**触发方式:**
- 🕐 **定时执行**: 每4小时自动运行
- 🔧 **手动触发**: 支持GitHub界面手动执行

**功能特性:**
- ✅ 完整的sitemap关键词分析流程
- ✅ 环境变量验证和配置检查
- ✅ 内置健康检查功能
- ✅ 试运行模式支持
- ✅ 执行结果自动存档
- ✅ 详细的执行报告生成

**手动触发参数:**
- `log_level`: 日志级别 (DEBUG/INFO/WARNING/ERROR)
- `dry_run`: 试运行模式，不实际提交数据
- `health_check_only`: 仅执行健康检查

**内置健康检查:**
- ✅ Python语法验证
- ✅ 模块导入验证
- ✅ 配置文件格式验证
- ✅ API连接测试
- ✅ 基础功能验证



## 必需的GitHub Secrets

在使用这些工作流之前，需要在GitHub仓库设置中配置以下Secrets:

| Secret名称 | 描述 | 示例值 |
|-----------|------|--------|
| `SEO_API_URLS` | SEO API端点URL列表 | `https://api1.example.com,https://api2.example.com` |
| `BACKEND_API_URL` | 后端API URL | `https://your-backend.com/api/keywords` |
| `BACKEND_API_TOKEN` | 后端API认证令牌 | `your_api_token_here` |
| `SITEMAP_URLS` | 监控的sitemap URL列表 | `https://site1.com/sitemap.xml,https://site2.com/sitemap.xml` |
| `ENCRYPTION_KEY` | 数据加密密钥 | `66字符的吉利密钥` |

### 设置Secrets步骤:

1. 进入GitHub仓库页面
2. 点击 `Settings` → `Secrets and variables` → `Actions`
3. 点击 `New repository secret`
4. 输入Secret名称和值
5. 点击 `Add secret`

## 使用指南

### 首次部署

1. **配置Secrets**: 按照上述说明配置所有必需的Secrets
2. **健康检查**: 手动运行工作流并启用 `health_check_only` 参数
3. **测试分析**: 手动运行工作流并启用 `dry_run` 模式进行测试
4. **生产运行**: 确认测试无误后启用正常模式

### 日常运维

- **监控定时任务**: 检查每4小时的自动执行结果
- **健康状态检查**: 使用 `health_check_only` 参数定期检查系统状态
- **手动干预**: 需要时手动触发分析任务
- **问题排查**: 查看工作流日志和上传的报告文件

### 故障排查

**常见问题:**

1. **Secrets未配置**
   - 症状: 部署验证失败，提示缺少环境变量
   - 解决: 检查并配置所有必需的Secrets

2. **API连接失败**
   - 症状: 健康检查或分析任务中API测试失败
   - 解决: 验证API URL和认证令牌的正确性

3. **配置文件错误**
   - 症状: 配置验证步骤失败
   - 解决: 检查YAML文件格式和内容完整性

4. **权限问题**
   - 症状: 文件写入失败
   - 解决: 检查目录权限和工作流权限设置

## 工作流输出

每个工作流都会生成以下输出:

### 日志文件
- 存储在 `logs/` 目录
- 自动上传为GitHub Artifacts
- 保留期: 7-30天

### 数据文件
- 存储在 `data/` 目录
- 包含处理结果和统计信息
- 自动上传为GitHub Artifacts

### 执行报告
- Markdown格式的详细报告
- 包含执行摘要和统计信息
- 自动上传为GitHub Artifacts

## 监控和告警

建议设置以下监控:

1. **工作流失败告警**: 配置GitHub通知或第三方集成
2. **定期检查**: 人工检查工作流执行历史
3. **数据质量监控**: 检查处理的URL数量和成功率
4. **API配额监控**: 关注SEO API的使用情况

## 自定义配置

可以根据需要修改以下配置:

- **执行频率**: 修改 `schedule.yml` 中的cron表达式
- **超时时间**: 调整 `timeout-minutes` 参数
- **保留期**: 修改artifacts的 `retention-days`
- **Python版本**: 更新 `PYTHON_VERSION` 环境变量

## 安全注意事项

1. **Secrets保护**: 确保Secrets不会在日志中泄露
2. **权限最小化**: 工作流只使用必需的权限
3. **数据加密**: 敏感数据使用加密存储
4. **访问控制**: 限制手动触发工作流的权限

## 支持和维护

- **文档更新**: 配置变更时及时更新此文档
- **版本管理**: 重要变更时创建Git标签
- **测试验证**: 修改后在测试环境验证
- **回滚准备**: 保留工作版本的备份
