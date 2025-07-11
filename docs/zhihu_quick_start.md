# 知乎增强功能快速上手指南

## 🚀 快速开始

### 1. 启用问题详情功能

问题详情功能**默认启用**，无需额外配置！当爬取回答类型的内容时，会自动获取对应问题的详细信息。

### 2. 启用热门评论功能

编辑 `config/base_config.py`：

```python
# 启用热门评论模式
ENABLE_HOT_COMMENTS = True

# 获取前10条热门评论
HOT_COMMENTS_COUNT = 10

# 只获取点赞数≥5的评论
MIN_COMMENT_LIKES = 5
```

### 3. 运行爬虫

```bash
python main.py --platform zhihu --lt qrcode --type 5
```

## 📊 数据输出示例

### 问题详情数据

```json
{
  "content_id": "123456789",
  "content_type": "answer",
  "title": "如何学习Python爬虫？",
  "question_id": "987654321",
  "question_title": "Python爬虫学习路径推荐",
  "question_detail": "想要系统学习Python爬虫技术，应该从哪些方面入手？",
  "question_tags": ["Python", "爬虫", "编程学习"],
  "question_follower_count": 1500,
  "question_answer_count": 200,
  "question_view_count": 50000
}
```

### 热门评论数据

```json
{
  "comment_id": "comment_123",
  "content": "非常详细的回答，受益匪浅！",
  "like_count": 128,
  "user_nickname": "Python学习者",
  "publish_time": "2025-07-10 15:30:00"
}
```

## ⚙️ 配置建议

### 不同场景的配置推荐

**学术研究场景**：
```python
ENABLE_HOT_COMMENTS = True
HOT_COMMENTS_COUNT = 20
MIN_COMMENT_LIKES = 10
```

**内容分析场景**：
```python
ENABLE_HOT_COMMENTS = True
HOT_COMMENTS_COUNT = 50
MIN_COMMENT_LIKES = 5
```

**快速浏览场景**：
```python
ENABLE_HOT_COMMENTS = True
HOT_COMMENTS_COUNT = 5
MIN_COMMENT_LIKES = 20
```

## 🔍 功能验证

### 检查问题详情是否正常获取

1. 运行爬虫后，检查输出的JSON文件
2. 查找 `question_title` 字段是否有值
3. 观察日志中的缓存命中信息

### 检查热门评论是否正常筛选

1. 启用热门评论模式
2. 检查评论数量是否符合配置
3. 验证评论按点赞数降序排列

## 📝 常见问题

**Q: 问题详情获取失败怎么办？**
A: 检查网络连接和日志错误信息，问题详情获取失败不会影响主要爬取流程。

**Q: 热门评论数量不够怎么办？**
A: 降低 `MIN_COMMENT_LIKES` 阈值，或者检查内容是否有足够的评论。

**Q: 如何关闭新功能？**
A: 问题详情功能无法关闭（不影响性能），热门评论功能设置 `ENABLE_HOT_COMMENTS = False` 即可。

## 🎯 最佳实践

1. **首次使用**：建议先用默认配置测试
2. **性能优化**：观察问题详情缓存命中率
3. **数据质量**：根据需求调整热门评论阈值
4. **监控日志**：关注错误和警告信息

---

💡 **提示**：更详细的功能说明请参考 [完整使用指南](zhihu_enhancement_guide.md)
