# 简化的URL-关键词提交流程

## 概述

新的简化流程移除了SEO数据查询步骤，直接从sitemap提取URL和关键词后提交到后端API。

## 主要变更

### 1. 移除的功能
- ❌ EnhancedSEOAPIManager - 不再查询SEO数据
- ❌ SEO API调用 - 不再调用外部SEO API
- ❌ 增量保存和Git提交 - 简化为直接提交

### 2. 新增的功能
- ✅ SimplifiedBackendClient - 直接提交URL-关键词映射
- ✅ Gzip压缩 - 减少网络传输数据量
- ✅ 批量处理 - 每批100条记录

### 3. 新的数据流程

```
原流程:
Sitemap → URL提取 → 关键词提取 → SEO查询 → 数据处理 → 存储+提交

新流程:
Sitemap → URL提取 → 关键词提取 → 直接提交
```

## 配置说明

### 环境变量

在 `.env` 文件中添加：

```bash
# 简化后端API配置
SITEMAP_API_URL=http://localhost:5001/api/sitemap/keywords
SITEMAP_SECRET_KEY=your-secret-key-2024
```

### 提交格式

```json
{
  "key": "your-secret-key-2024",
  "data": {
    "https://example.com/page1": "关键词1, 关键词2",
    "https://example.com/page2": "关键词3, 关键词4"
  }
}
```

注意：
- 多个关键词用逗号分隔合并为一个字符串
- 数据使用gzip压缩后发送
- 每批最多100条记录

## 使用方法

### 1. 正常运行

```bash
python main.py --config config/config.yaml --rules config/url_rules.yaml
```

### 2. 测试新流程

```bash
python test_simplified_flow.py
```

### 3. 健康检查

```bash
python main.py --health-check
```

## API响应处理

### 成功响应 (200)
```json
{
  "status": "success",
  "message": "Data received",
  "count": 100
}
```

### 错误响应
```json
{
  "status": "error",
  "message": "Invalid key"
}
```

## 性能优化

1. **批量处理**: 自动将数据分批，每批100条
2. **并发提交**: 多个批次并发提交
3. **Gzip压缩**: 减少70-80%的数据传输量
4. **连接复用**: 使用aiohttp会话复用连接

## 错误处理

1. **连接失败**: 自动重试（可配置）
2. **认证失败**: 检查SECRET_KEY配置
3. **超时处理**: 默认30秒超时
4. **批次失败**: 记录失败批次，继续处理其他批次

## 监控和日志

### 统计信息
- total_submitted: 总提交记录数
- total_batches: 总批次数
- failed_batches: 失败批次数
- success_rate: 成功率

### 日志级别
- INFO: 正常操作日志
- DEBUG: 详细调试信息
- ERROR: 错误和异常

## 注意事项

1. **关键词映射**: 如果一个URL有多个关键词，会合并为逗号分隔的字符串
2. **API限制**: 确保后端API能处理批量请求
3. **网络要求**: 需要稳定的网络连接
4. **数据大小**: 单批数据压缩后不应超过10MB