# 🔥 MediaCrawler - 自媒体平台爬虫 🕷️

<div align="center">

<a href="https://trendshift.io/repositories/8291" target="_blank">
  <img src="https://trendshift.io/api/badge/repositories/8291" alt="NanmiCoder%2FMediaCrawler | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/>
</a>

[![GitHub Stars](https://img.shields.io/github/stars/NanmiCoder/MediaCrawler?style=social)](https://github.com/NanmiCoder/MediaCrawler/stargazers)
[![GitHub Forks](https://img.shields.io/github/forks/NanmiCoder/MediaCrawler?style=social)](https://github.com/NanmiCoder/MediaCrawler/network/members)
[![GitHub Issues](https://img.shields.io/github/issues/NanmiCoder/MediaCrawler)](https://github.com/NanmiCoder/MediaCrawler/issues)
[![GitHub Pull Requests](https://img.shields.io/github/issues-pr/NanmiCoder/MediaCrawler)](https://github.com/NanmiCoder/MediaCrawler/pulls)
[![License](https://img.shields.io/github/license/NanmiCoder/MediaCrawler)](https://github.com/NanmiCoder/MediaCrawler/blob/main/LICENSE)
[![中文](https://img.shields.io/badge/🇨🇳_中文-当前-blue)](README.md)
[![English](https://img.shields.io/badge/🇺🇸_English-Available-green)](README_en.md)
[![Español](https://img.shields.io/badge/🇪🇸_Español-Available-green)](README_es.md)
</div>



> **免责声明：**
> 
> 大家请以学习为目的使用本仓库⚠️⚠️⚠️⚠️，[爬虫违法违规的案件](https://github.com/HiddenStrawberry/Crawler_Illegal_Cases_In_China)  <br>
>
>本仓库的所有内容仅供学习和参考之用，禁止用于商业用途。任何人或组织不得将本仓库的内容用于非法用途或侵犯他人合法权益。本仓库所涉及的爬虫技术仅用于学习和研究，不得用于对其他平台进行大规模爬虫或其他非法行为。对于因使用本仓库内容而引起的任何法律责任，本仓库不承担任何责任。使用本仓库的内容即表示您同意本免责声明的所有条款和条件。
>
> 点击查看更为详细的免责声明。[点击跳转](#disclaimer)




## 📖 项目简介

一个功能强大的**多平台自媒体数据采集工具**，支持小红书、抖音、快手、B站、微博、贴吧、知乎等主流平台的公开信息抓取。

### 🔧 技术原理

- **核心技术**：基于 [Playwright](https://playwright.dev/) 浏览器自动化框架登录保存登录态
- **无需JS逆向**：利用保留登录态的浏览器上下文环境，通过 JS 表达式获取签名参数
- **优势特点**：无需逆向复杂的加密算法，大幅降低技术门槛

## ✨ 功能特性
| 平台   | 关键词搜索 | 指定帖子ID爬取 | 二级评论 | 指定创作者主页 | 登录态缓存 | IP代理池 | 生成评论词云图 |
| ------ | ---------- | -------------- | -------- | -------------- | ---------- | -------- | -------------- |
| 小红书 | ✅          | ✅              | ✅        | ✅              | ✅          | ✅        | ✅              |
| 抖音   | ✅          | ✅              | ✅        | ✅              | ✅          | ✅        | ✅              |
| 快手   | ✅          | ✅              | ✅        | ✅              | ✅          | ✅        | ✅              |
| B 站   | ✅          | ✅              | ✅        | ✅              | ✅          | ✅        | ✅              |
| 微博   | ✅          | ✅              | ✅        | ✅              | ✅          | ✅        | ✅              |
| 贴吧   | ✅          | ✅              | ✅        | ✅              | ✅          | ✅        | ✅              |
| 知乎   | ✅          | ✅              | ✅        | ✅              | ✅          | ✅        | ✅              |

### 🎯 知乎增强功能

**第二阶段：问题详情爬取** ✨
- 🔍 **自动问题详情获取**：回答类型内容自动获取对应问题的详细信息
- 💾 **智能缓存机制**：避免重复请求，提高爬取效率
- 📊 **丰富数据结构**：包含问题标题、描述、标签、统计信息等

**第三阶段：热门评论爬取** 🔥
- 🏆 **智能评论筛选**：按点赞数自动筛选热门评论
- ⚙️ **灵活配置选项**：支持自定义热门评论数量和点赞阈值
- 📈 **高效排序算法**：自动按点赞数降序排列

**第四阶段：全面图片爬取** 🖼️ ✅
- 🎯 **多类型图片支持**：支持问题、答案、评论中的图片爬取
- 🚀 **性能优化模式**：新增 `--skip-comments-pic` 参数，跳过评论图片处理以提升速度
- 🔍 **智能图片检测**：分别检测问题、答案、评论中的图片，精确控制浏览器打开时机
- 📁 **统一图片管理**：同一内容的所有图片保存在同一文件夹，支持去重处理
- 🏷️ **完美图片占位符替换**：自动将 `[图片]` 和 `查看图片` 占位符替换为实际图片文件名（`[pic:filename]`格式）
- 🔧 **浏览器解析评论**：使用浏览器直接解析评论内容，确保评论和图片顺序完全匹配
- 🛡️ **安全按钮操作**：精确识别评论按钮，避免误点其他操作按钮

> 📖 详细使用说明请参考：[知乎增强功能使用指南](docs/zhihu_enhancement_guide.md)

<details id="pro-version">
<summary>🔗 <strong>🚀 MediaCrawlerPro 重磅发布！更多的功能，更好的架构设计！</strong></summary>

### 🚀 MediaCrawlerPro 重磅发布！

> 专注于学习成熟项目的架构设计，不仅仅是爬虫技术，Pro 版本的代码设计思路同样值得深入学习！

[MediaCrawlerPro](https://github.com/MediaCrawlerPro) 相较于开源版本的核心优势：

#### 🎯 核心功能升级
- ✅ **断点续爬功能**（重点特性）
- ✅ **多账号 + IP代理池支持**（重点特性）
- ✅ **去除 Playwright 依赖**，使用更简单
- ✅ **完整 Linux 环境支持**

#### 🏗️ 架构设计优化
- ✅ **代码重构优化**，更易读易维护（解耦 JS 签名逻辑）
- ✅ **企业级代码质量**，适合构建大型爬虫项目
- ✅ **完美架构设计**，高扩展性，源码学习价值更大

#### 🎁 额外功能
- ✅ **自媒体视频下载器桌面端**（适合学习全栈开发）
- ✅ **多平台首页信息流推荐**（HomeFeed）
- [ ] **基于自媒体平台的AI Agent正在开发中 🚀🚀**

点击查看：[MediaCrawlerPro 项目主页](https://github.com/MediaCrawlerPro) 更多介绍
</details>

## 🚀 快速开始

> 💡 **开源不易，如果这个项目对您有帮助，请给个 ⭐ Star 支持一下！**

## 📋 前置依赖

### 🚀 uv 安装（推荐）

在进行下一步操作之前，请确保电脑上已经安装了 uv：

- **安装地址**：[uv 官方安装指南](https://docs.astral.sh/uv/getting-started/installation)
- **验证安装**：终端输入命令 `uv --version`，如果正常显示版本号，证明已经安装成功
- **推荐理由**：uv 是目前最强的 Python 包管理工具，速度快、依赖解析准确

### 🟢 Node.js 安装

项目依赖 Node.js，请前往官网下载安装：

- **下载地址**：https://nodejs.org/en/download/
- **版本要求**：>= 16.0.0

### 📦 Python 包安装

```shell
# 进入项目目录
cd MediaCrawler

# 使用 uv sync 命令来保证 python 版本和相关依赖包的一致性
uv sync
```

### 🌐 浏览器驱动安装

```shell
# 安装浏览器驱动
uv run playwright install
```

> **💡 提示**：MediaCrawler 目前已经支持使用 playwright 连接你本地的 Chrome 浏览器了，一些因为 Webdriver 导致的问题迎刃而解了。
>
> 目前开放了 `xhs` 和 `dy` 这两个使用 CDP 的方式连接本地浏览器，如有需要，查看 `config/base_config.py` 中的配置项。

## 🚀 运行爬虫程序

```shell
# 项目默认是没有开启评论爬取模式，如需评论请在 config/base_config.py 中的 ENABLE_GET_COMMENTS 变量修改
# 一些其他支持项，也可以在 config/base_config.py 查看功能，写的有中文注释

# 从配置文件中读取关键词搜索相关的帖子并爬取帖子信息与评论
uv run main.py --platform xhs --lt qrcode --type search

# 从配置文件中读取指定的帖子ID列表获取指定帖子的信息与评论信息
uv run main.py --platform xhs --lt qrcode --type detail

# 打开对应APP扫二维码登录

# 其他平台爬虫使用示例，执行下面的命令查看
uv run main.py --help
```

<details>
<summary>🔗 <strong>使用 Python 原生 venv 管理环境（不推荐）</strong></summary>

#### 创建并激活 Python 虚拟环境

> 如果是爬取抖音和知乎，需要提前安装 nodejs 环境，版本大于等于：`16` 即可

```shell
# 进入项目根目录
cd MediaCrawler

# 创建虚拟环境
# 我的 python 版本是：3.9.6，requirements.txt 中的库是基于这个版本的
# 如果是其他 python 版本，可能 requirements.txt 中的库不兼容，需自行解决
python -m venv venv

# macOS & Linux 激活虚拟环境
source venv/bin/activate

# Windows 激活虚拟环境
venv\Scripts\activate
```

#### 安装依赖库

```shell
pip install -r requirements.txt
```

#### 安装 playwright 浏览器驱动

```shell
playwright install
```

#### 运行爬虫程序（原生环境）

```shell
# 项目默认是没有开启评论爬取模式，如需评论请在 config/base_config.py 中的 ENABLE_GET_COMMENTS 变量修改
# 一些其他支持项，也可以在 config/base_config.py 查看功能，写的有中文注释

# 从配置文件中读取关键词搜索相关的帖子并爬取帖子信息与评论
python main.py --platform xhs --lt qrcode --type search

# 从配置文件中读取指定的帖子ID列表获取指定帖子的信息与评论信息
python main.py --platform xhs --lt qrcode --type detail

# 打开对应APP扫二维码登录

# 知乎收藏夹爬取示例（包含图片处理）
python main.py --platform zhihu --lt qrcode --type collection --max_count 5

# 知乎收藏夹爬取（跳过评论图片，提升速度）
python main.py --platform zhihu --lt qrcode --type collection --max_count 5 --skip-comments-pic

# 其他平台爬虫使用示例，执行下面的命令查看
python main.py --help
```

</details>


## 💾 数据保存

支持多种数据存储方式：

- **MySQL 数据库**：支持关系型数据库 MySQL 中保存（需要提前创建数据库）
  - 执行 `python db.py` 初始化数据库表结构（只在首次执行）
- **CSV 文件**：支持保存到 CSV 中（`data/` 目录下）
- **JSON 文件**：支持保存到 JSON 中（`data/` 目录下）

---

[🚀 MediaCrawlerPro 重磅发布 🚀！更多的功能，更好的架构设计！](https://github.com/MediaCrawlerPro)

## 🤝 社区与支持

### 💬 交流群组
- **微信交流群**：[点击加入](https://nanmicoder.github.io/MediaCrawler/%E5%BE%AE%E4%BF%A1%E4%BA%A4%E6%B5%81%E7%BE%A4.html)

### 📚 文档与教程
- **在线文档**：[MediaCrawler 完整文档](https://nanmicoder.github.io/MediaCrawler/)
- **爬虫教程**：[CrawlerTutorial 免费教程](https://github.com/NanmiCoder/CrawlerTutorial)
  

# 其他常见问题可以查看在线文档
> 
> 在线文档包含使用方法、常见问题、加入项目交流群等。
> [MediaCrawler在线文档](https://nanmicoder.github.io/MediaCrawler/)
> 

# 作者提供的知识服务
> 如果想快速入门和学习该项目的使用、源码架构设计等、学习编程技术、亦或者想了解MediaCrawlerPro的源代码设计可以看下我的知识付费栏目。

[作者的知识付费栏目介绍](https://nanmicoder.github.io/MediaCrawler/%E7%9F%A5%E8%AF%86%E4%BB%98%E8%B4%B9%E4%BB%8B%E7%BB%8D.html)


---

## ⭐ Star 趋势图

如果这个项目对您有帮助，请给个 ⭐ Star 支持一下，让更多的人看到 MediaCrawler！

[![Star History Chart](https://api.star-history.com/svg?repos=NanmiCoder/MediaCrawler&type=Date)](https://star-history.com/#NanmiCoder/MediaCrawler&Date)

### 💰 赞助商展示

<a href="https://www.swiftproxy.net/?ref=nanmi">
<img src="docs/static/images/img_5.png">
<br>
**Swiftproxy** - 90M+ 全球高质量纯净住宅IP，注册可领免费 500MB 测试流量，动态流量不过期！
> 专属折扣码：**GHB5** 立享九折优惠！
</a>

<br><br>

<a href="https://sider.ai/ad-land-redirect?source=github&p1=mi&p2=kk">**Sider** - 全网最火的 ChatGPT 插件，体验拉满！</a>

### 🤝 成为赞助者

成为赞助者，可以将您的产品展示在这里，每天获得大量曝光！

**联系方式**：
- 微信：`yzglan`
- 邮箱：`relakkes@gmail.com`


## 📚 参考

- **小红书客户端**：[ReaJason 的 xhs 仓库](https://github.com/ReaJason/xhs)
- **短信转发**：[SmsForwarder 参考仓库](https://github.com/pppscn/SmsForwarder)
- **内网穿透工具**：[ngrok 官方文档](https://ngrok.com/docs/)


# 免责声明
<div id="disclaimer"> 

## 1. 项目目的与性质
本项目（以下简称“本项目”）是作为一个技术研究与学习工具而创建的，旨在探索和学习网络数据采集技术。本项目专注于自媒体平台的数据爬取技术研究，旨在提供给学习者和研究者作为技术交流之用。

## 2. 法律合规性声明
本项目开发者（以下简称“开发者”）郑重提醒用户在下载、安装和使用本项目时，严格遵守中华人民共和国相关法律法规，包括但不限于《中华人民共和国网络安全法》、《中华人民共和国反间谍法》等所有适用的国家法律和政策。用户应自行承担一切因使用本项目而可能引起的法律责任。

## 3. 使用目的限制
本项目严禁用于任何非法目的或非学习、非研究的商业行为。本项目不得用于任何形式的非法侵入他人计算机系统，不得用于任何侵犯他人知识产权或其他合法权益的行为。用户应保证其使用本项目的目的纯属个人学习和技术研究，不得用于任何形式的非法活动。

## 4. 免责声明
开发者已尽最大努力确保本项目的正当性及安全性，但不对用户使用本项目可能引起的任何形式的直接或间接损失承担责任。包括但不限于由于使用本项目而导致的任何数据丢失、设备损坏、法律诉讼等。

## 5. 知识产权声明
本项目的知识产权归开发者所有。本项目受到著作权法和国际著作权条约以及其他知识产权法律和条约的保护。用户在遵守本声明及相关法律法规的前提下，可以下载和使用本项目。

## 6. 最终解释权
关于本项目的最终解释权归开发者所有。开发者保留随时更改或更新本免责声明的权利，恕不另行通知。
</div>


## 📝 更新历史

### 2025-07-16
- 🎉 **知乎爬虫热门评论数量限制修复**
  - ✅ **完全解决HOT_COMMENTS_COUNT配置不生效问题**：两种模式都严格遵循评论数量限制
  - 🔧 **浏览器解析模式修复**：在收藏夹爬取中正确应用热门评论筛选
  - 📊 **API模式验证**：确认API模式热门评论功能正常工作
  - 🎨 **图片占位符格式优化**：`[pic:filename]` → `[content_id/filename]`，提升可读性和实用性
- 🔧 **知乎爬虫评论图片处理重大修复**
  - 🎯 **完全解决评论图片占位符替换问题**：修复方案三，实现完美的 `[图片]` → `[pic:filename]` 替换
  - 🔒 **修复评论按钮识别错误**：解决误点"取消喜欢"按钮的严重bug，确保只点击评论按钮
  - 🎯 **优化评论区处理逻辑**：只处理第一个评论区，避免多余的评论抓取
  - 🧹 **数据结构优化**：移除浏览器解析评论中的无效字段（sub_comment_count、dislike_count等）
  - ⚙️ **完善skip-comments-pic模式**：确保该模式下has_comment_images永远为False
  - ✅ **全面测试验证**：所有功能完美工作，评论图片处理功能完全正常

### 2025-07-15
- ✅ **知乎爬虫第四阶段：全面图片爬取功能**
  - 🖼️ 新增问题图片爬取功能，支持问题详情中的图片下载
  - 🖼️ 新增评论图片爬取功能，支持评论区用户上传图片的识别和下载
  - 🚀 新增 `--skip-comments-pic` 性能优化参数，跳过评论图片处理以提升速度
  - 🔍 优化图片检测逻辑，分别检测问题、答案、评论中的图片类型
  - 📁 统一图片管理，同一内容的所有图片保存在同一文件夹并支持去重
  - 🏷️ 完善图片占位符替换，自动将 `[图片]` 和 `查看图片` 替换为实际文件名

### 2025-07-10
- ✅ **知乎收藏夹爬虫增强**
  - 修复question_id字段缺失问题，现可正确获取问题ID构建完整URL
  - 修复created_time和updated_time字段为0的问题，现可获取真实时间
  - 新增时间格式自动转换功能，输出人类可读的日期格式（YYYY-MM-DD HH:MM:SS）
  - 修复httpx兼容性问题和字段名不匹配问题
  - 提升数据完整性和可用性
- 🎯 **知乎增强功能重大更新**
  - **第二阶段：问题详情爬取功能**
    - 扩展ZhihuContent数据模型，新增6个问题详情字段
    - 实现问题详情API接口和HTML解析逻辑
    - 集成智能缓存机制，避免重复请求提高效率
    - 自动为回答类型内容获取对应问题的完整信息
  - **第三阶段：热门评论爬取功能**
    - 新增热门评论配置选项（ENABLE_HOT_COMMENTS等）
    - 实现按点赞数智能筛选和排序算法
    - 支持自定义热门评论数量和点赞阈值
    - 提供传统模式和热门评论模式双重选择
  - **技术优化**
    - 更新数据库表结构，支持问题详情字段存储
    - 完善错误处理和日志记录机制
    - 保持向下兼容，不影响现有功能
    - 提供完整的测试脚本和使用文档

## 🙏 致谢

### JetBrains 开源许可证支持

感谢 JetBrains 为本项目提供免费的开源许可证支持！

<a href="https://www.jetbrains.com/?from=MediaCrawler">
    <img src="https://www.jetbrains.com/company/brand/img/jetbrains_logo.png" width="100" alt="JetBrains" />
</a>
