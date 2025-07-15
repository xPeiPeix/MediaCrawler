# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：  
# 1. 不得用于任何商业用途。  
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。  
# 3. 不得进行大规模爬取或对平台造成运营干扰。  
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。   
# 5. 不得用于任何非法或不当的用途。
#   
# 详细许可条款请参阅项目根目录下的LICENSE文件。  
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。  


# -*- coding: utf-8 -*-
import asyncio
import os
import random
from asyncio import Task
from typing import Dict, List, Optional, Tuple, cast

from playwright.async_api import (BrowserContext, BrowserType, Page, Playwright,
                                  async_playwright)
from bs4 import BeautifulSoup

import config
from constant import zhihu as constant
from base.base_crawler import AbstractCrawler
from model.m_zhihu import ZhihuContent, ZhihuCreator, ZhihuComment
from proxy.proxy_ip_pool import IpInfoModel, create_ip_pool
from store import zhihu as zhihu_store
from tools import utils
from tools.cdp_browser import CDPBrowserManager
from tools.content_checker import get_content_checker
from tools.crawler_util import replace_image_placeholders_with_filenames
from var import crawler_type_var, source_keyword_var

from .client import ZhiHuClient
from .exception import DataFetchError
from .help import ZhihuExtractor, judge_zhihu_url
from .login import ZhiHuLogin
from .image_processor import ZhihuImageProcessor


class ZhihuCrawler(AbstractCrawler):
    context_page: Page
    zhihu_client: ZhiHuClient
    browser_context: BrowserContext
    cdp_manager: Optional[CDPBrowserManager]

    def __init__(self) -> None:
        self.index_url = "https://www.zhihu.com"
        # self.user_agent = utils.get_user_agent()
        self.user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self._extractor = ZhihuExtractor()
        self.cdp_manager = None
        # 问题详情缓存（第二阶段新增）
        self.question_cache: Dict[str, Dict] = {}

    async def start(self) -> None:
        """
        Start the crawler
        Returns:

        """
        playwright_proxy_format, httpx_proxy_format = None, None
        if config.ENABLE_IP_PROXY:
            ip_proxy_pool = await create_ip_pool(config.IP_PROXY_POOL_COUNT, enable_validate_ip=True)
            ip_proxy_info: IpInfoModel = await ip_proxy_pool.get_proxy()
            playwright_proxy_format, httpx_proxy_format = self.format_proxy_info(ip_proxy_info)

        async with async_playwright() as playwright:
            # 根据配置选择启动模式
            if config.ENABLE_CDP_MODE:
                utils.logger.info("[ZhihuCrawler] 使用CDP模式启动浏览器")
                self.browser_context = await self.launch_browser_with_cdp(
                    playwright, playwright_proxy_format, self.user_agent,
                    headless=config.CDP_HEADLESS
                )
            else:
                utils.logger.info("[ZhihuCrawler] 使用标准模式启动浏览器")
                # Launch a browser context.
                chromium = playwright.chromium
                self.browser_context = await self.launch_browser(
                    chromium,
                    None,
                    self.user_agent,
                    headless=config.HEADLESS
                )
            # stealth.min.js is a js script to prevent the website from detecting the crawler.
            await self.browser_context.add_init_script(path="libs/stealth.min.js")

            self.context_page = await self.browser_context.new_page()
            await self.context_page.goto(self.index_url, wait_until="domcontentloaded")

            # Create a client to interact with the zhihu website.
            self.zhihu_client = await self.create_zhihu_client(httpx_proxy_format)
            if not await self.zhihu_client.pong():
                login_obj = ZhiHuLogin(
                    login_type=config.LOGIN_TYPE,
                    login_phone="",  # input your phone number
                    browser_context=self.browser_context,
                    context_page=self.context_page,
                    cookie_str=config.COOKIES
                )
                await login_obj.begin()
                await self.zhihu_client.update_cookies(browser_context=self.browser_context)

            # 知乎的搜索接口需要打开搜索页面之后cookies才能访问API，单独的首页不行
            utils.logger.info("[ZhihuCrawler.start] Zhihu跳转到搜索页面获取搜索页面的Cookies，该过程需要5秒左右")
            await self.context_page.goto(f"{self.index_url}/search?q=python&search_source=Guess&utm_content=search_hot&type=content")
            await asyncio.sleep(5)
            await self.zhihu_client.update_cookies(browser_context=self.browser_context)

            crawler_type_var.set(config.CRAWLER_TYPE)
            if config.CRAWLER_TYPE == "search":
                # Search for notes and retrieve their comment information.
                await self.search()
            elif config.CRAWLER_TYPE == "detail":
                # Get the information and comments of the specified post
                await self.get_specified_notes()
            elif config.CRAWLER_TYPE == "creator":
                # Get creator's information and their notes and comments
                await self.get_creators_and_notes()
            elif config.CRAWLER_TYPE == "collection":
                # Get user's collection information and their contents
                await self.get_user_collections()
            else:
                pass

            utils.logger.info("[ZhihuCrawler.start] Zhihu Crawler finished ...")

    async def search(self) -> None:
        """Search for notes and retrieve their comment information."""
        utils.logger.info("[ZhihuCrawler.search] Begin search zhihu keywords")
        zhihu_limit_count = 20  # zhihu limit page fixed value
        if config.CRAWLER_MAX_NOTES_COUNT < zhihu_limit_count:
            config.CRAWLER_MAX_NOTES_COUNT = zhihu_limit_count
        start_page = config.START_PAGE
        for keyword in config.KEYWORDS.split(","):
            source_keyword_var.set(keyword)
            utils.logger.info(f"[ZhihuCrawler.search] Current search keyword: {keyword}")
            page = 1
            while (page - start_page + 1) * zhihu_limit_count <= config.CRAWLER_MAX_NOTES_COUNT:
                if page < start_page:
                    utils.logger.info(f"[ZhihuCrawler.search] Skip page {page}")
                    page += 1
                    continue

                try:
                    utils.logger.info(f"[ZhihuCrawler.search] search zhihu keyword: {keyword}, page: {page}")
                    content_list: List[ZhihuContent]  = await self.zhihu_client.get_note_by_keyword(
                        keyword=keyword,
                        page=page,
                    )
                    utils.logger.info(f"[ZhihuCrawler.search] Search contents :{content_list}")
                    if not content_list:
                        utils.logger.info("No more content!")
                        break

                    page += 1
                    for content in content_list:
                        await zhihu_store.update_zhihu_content(content)

                    await self.batch_get_content_comments(content_list)
                except DataFetchError:
                    utils.logger.error("[ZhihuCrawler.search] Search content error")
                    return

    async def batch_get_content_comments(self, content_list: List[ZhihuContent]):
        """
        Batch get content comments
        Args:
            content_list:

        Returns:

        """
        if not config.ENABLE_GET_COMMENTS:
            utils.logger.info(f"[ZhihuCrawler.batch_get_content_comments] Crawling comment mode is not enabled")
            return

        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
        task_list: List[Task] = []
        for content_item in content_list:
            task = asyncio.create_task(self.get_comments(content_item, semaphore), name=content_item.content_id)
            task_list.append(task)
        await asyncio.gather(*task_list)

    async def get_comments(self, content_item: ZhihuContent, semaphore: asyncio.Semaphore):
        """
        Get note comments with keyword filtering and quantity limitation
        Args:
            content_item:
            semaphore:

        Returns:

        """
        async with semaphore:
            utils.logger.info(f"[ZhihuCrawler.get_comments] Begin get note id comments {content_item.content_id}")

            # 检查是否启用热门评论模式（第三阶段新增功能）
            if config.ENABLE_HOT_COMMENTS:
                await self._get_hot_comments(content_item)
            else:
                await self.zhihu_client.get_note_all_comments(
                    content=content_item,
                    crawl_interval=random.random(),
                    callback=zhihu_store.batch_update_zhihu_note_comments
                )

    async def _get_hot_comments(self, content_item: ZhihuContent, is_collection_crawl: bool = False):
        """
        获取热门评论（第三阶段新增功能）
        Args:
            content_item: 内容对象

        Returns:

        """
        try:
            utils.logger.info(f"[ZhihuCrawler._get_hot_comments] Getting hot comments for {content_item.content_id}")

            # 获取所有评论（不使用回调函数，直接获取返回值）
            all_comments = await self.zhihu_client.get_note_all_comments(
                content=content_item,
                crawl_interval=random.random(),
                callback=None  # 不使用回调，直接获取返回值
            )

            if not all_comments:
                utils.logger.info(f"[ZhihuCrawler._get_hot_comments] No comments found for {content_item.content_id}")
                return

            utils.logger.info(f"[ZhihuCrawler._get_hot_comments] Retrieved {len(all_comments)} total comments for {content_item.content_id}")

            # 筛选热门评论
            hot_comments = self._filter_hot_comments(all_comments)

            if hot_comments:
                utils.logger.info(f"[ZhihuCrawler._get_hot_comments] Found {len(hot_comments)} hot comments for {content_item.content_id}")
                # 将热门评论添加到content_item.comments列表中（用于收藏夹整合存储）
                content_item.comments.extend(hot_comments)
                # 只在非收藏夹爬取模式下使用分离存储（避免重复存储）
                if not is_collection_crawl:
                    await zhihu_store.batch_update_zhihu_note_comments(hot_comments)
                else:
                    utils.logger.info(f"[ZhihuCrawler._get_hot_comments] Collection crawl mode: skipping separate comment storage")
            else:
                utils.logger.info(f"[ZhihuCrawler._get_hot_comments] No hot comments found for {content_item.content_id} (threshold: {config.MIN_COMMENT_LIKES})")

        except Exception as e:
            utils.logger.error(f"[ZhihuCrawler._get_hot_comments] Error getting hot comments for {content_item.content_id}: {e}")

    def _filter_hot_comments(self, comments: List[ZhihuComment]) -> List[ZhihuComment]:
        """
        筛选热门评论
        Args:
            comments: 所有评论列表

        Returns:
            热门评论列表

        """
        try:
            utils.logger.info(f"[ZhihuCrawler._filter_hot_comments] Starting to filter {len(comments)} comments with threshold {config.MIN_COMMENT_LIKES}")

            # 过滤掉点赞数小于阈值的评论
            filtered_comments = [
                comment for comment in comments
                if comment.like_count >= config.MIN_COMMENT_LIKES
            ]

            utils.logger.info(f"[ZhihuCrawler._filter_hot_comments] After threshold filtering: {len(filtered_comments)} comments remain")

            # 按点赞数降序排序
            filtered_comments.sort(key=lambda x: x.like_count, reverse=True)

            # 取前N条热门评论
            hot_comments = filtered_comments[:config.HOT_COMMENTS_COUNT]

            # 输出热门评论的点赞数信息
            if hot_comments:
                like_counts = [comment.like_count for comment in hot_comments]
                utils.logger.info(f"[ZhihuCrawler._filter_hot_comments] Hot comments like counts: {like_counts}")

            utils.logger.info(f"[ZhihuCrawler._filter_hot_comments] Final result: {len(hot_comments)} hot comments from {len(comments)} total comments")
            return hot_comments

        except Exception as e:
            utils.logger.error(f"[ZhihuCrawler._filter_hot_comments] Error filtering hot comments: {e}")
            return []

    async def get_creators_and_notes(self) -> None:
        """
        Get creator's information and their notes and comments
        Returns:

        """
        utils.logger.info("[ZhihuCrawler.get_creators_and_notes] Begin get xiaohongshu creators")
        for user_link in config.ZHIHU_CREATOR_URL_LIST:
            utils.logger.info(f"[ZhihuCrawler.get_creators_and_notes] Begin get creator {user_link}")
            user_url_token = user_link.split("/")[-1]
            # get creator detail info from web html content
            createor_info: ZhihuCreator = await self.zhihu_client.get_creator_info(url_token=user_url_token)
            if not createor_info:
                utils.logger.info(f"[ZhihuCrawler.get_creators_and_notes] Creator {user_url_token} not found")
                continue

            utils.logger.info(f"[ZhihuCrawler.get_creators_and_notes] Creator info: {createor_info}")
            await zhihu_store.save_creator(creator=createor_info)

            # 默认只提取回答信息，如果需要文章和视频，把下面的注释打开即可

            # Get all anwser information of the creator
            all_content_list = await self.zhihu_client.get_all_anwser_by_creator(
                creator=createor_info,
                crawl_interval=random.random(),
                callback=zhihu_store.batch_update_zhihu_contents
            )


            # Get all articles of the creator's contents
            # all_content_list = await self.zhihu_client.get_all_articles_by_creator(
            #     creator=createor_info,
            #     crawl_interval=random.random(),
            #     callback=zhihu_store.batch_update_zhihu_contents
            # )

            # Get all videos of the creator's contents
            # all_content_list = await self.zhihu_client.get_all_videos_by_creator(
            #     creator=createor_info,
            #     crawl_interval=random.random(),
            #     callback=zhihu_store.batch_update_zhihu_contents
            # )

            # Get all comments of the creator's contents
            await self.batch_get_content_comments(all_content_list)

    async def get_note_detail(
        self, full_note_url: str, semaphore: asyncio.Semaphore
    ) -> Optional[ZhihuContent]:
        """
        Get note detail
        Args:
            full_note_url: str
            semaphore:

        Returns:

        """
        async with semaphore:
            utils.logger.info(
                f"[ZhihuCrawler.get_specified_notes] Begin get specified note {full_note_url}"
            )
            # judge note type
            note_type: str = judge_zhihu_url(full_note_url)
            if note_type == constant.ANSWER_NAME:
                question_id = full_note_url.split("/")[-3]
                answer_id = full_note_url.split("/")[-1]
                utils.logger.info(
                    f"[ZhihuCrawler.get_specified_notes] Get answer info, question_id: {question_id}, answer_id: {answer_id}"
                )
                return await self.zhihu_client.get_answer_info(question_id, answer_id)

            elif note_type == constant.ARTICLE_NAME:
                article_id = full_note_url.split("/")[-1]
                utils.logger.info(
                    f"[ZhihuCrawler.get_specified_notes] Get article info, article_id: {article_id}"
                )
                return await self.zhihu_client.get_article_info(article_id)

            elif note_type == constant.VIDEO_NAME:
                video_id = full_note_url.split("/")[-1]
                utils.logger.info(
                    f"[ZhihuCrawler.get_specified_notes] Get video info, video_id: {video_id}"
                )
                return await self.zhihu_client.get_video_info(video_id)

    async def get_specified_notes(self):
        """
        Get the information and comments of the specified post
        Returns:

        """
        get_note_detail_task_list = []
        for full_note_url in config.ZHIHU_SPECIFIED_ID_LIST:
            # remove query params
            full_note_url = full_note_url.split("?")[0]
            crawler_task = self.get_note_detail(
                full_note_url=full_note_url,
                semaphore=asyncio.Semaphore(config.MAX_CONCURRENCY_NUM),
            )
            get_note_detail_task_list.append(crawler_task)

        need_get_comment_notes: List[ZhihuContent] = []
        note_details = await asyncio.gather(*get_note_detail_task_list)
        for index, note_detail in enumerate(note_details):
            if not note_detail:
                utils.logger.info(
                    f"[ZhihuCrawler.get_specified_notes] Note {config.ZHIHU_SPECIFIED_ID_LIST[index]} not found"
                )
                continue

            note_detail = cast(ZhihuContent, note_detail)  # only for type check
            need_get_comment_notes.append(note_detail)
            await zhihu_store.update_zhihu_content(note_detail)

        await self.batch_get_content_comments(need_get_comment_notes)

    @staticmethod
    def format_proxy_info(ip_proxy_info: IpInfoModel) -> Tuple[Optional[Dict], Optional[Dict]]:
        """format proxy info for playwright and httpx"""
        playwright_proxy = {
            "server": f"{ip_proxy_info.protocol}{ip_proxy_info.ip}:{ip_proxy_info.port}",
            "username": ip_proxy_info.user,
            "password": ip_proxy_info.password,
        }
        httpx_proxy = {
            f"{ip_proxy_info.protocol}": f"http://{ip_proxy_info.user}:{ip_proxy_info.password}@{ip_proxy_info.ip}:{ip_proxy_info.port}"
        }
        return playwright_proxy, httpx_proxy

    async def create_zhihu_client(self, httpx_proxy: Optional[str]) -> ZhiHuClient:
        """Create zhihu client"""
        utils.logger.info("[ZhihuCrawler.create_zhihu_client] Begin create zhihu API client ...")
        cookie_str, cookie_dict = utils.convert_cookies(await self.browser_context.cookies())
        zhihu_client_obj = ZhiHuClient(
            proxies=httpx_proxy,
            headers={
                'accept': '*/*',
                'accept-language': 'zh-CN,zh;q=0.9',
                'cookie': cookie_str,
                'priority': 'u=1, i',
                'referer': 'https://www.zhihu.com/search?q=python&time_interval=a_year&type=content',
                'user-agent': self.user_agent,
                'x-api-version': '3.0.91',
                'x-app-za': 'OS=Web',
                'x-requested-with': 'fetch',
                'x-zse-93': '101_3_3.0',
            },
            playwright_page=self.context_page,
            cookie_dict=cookie_dict,
        )
        return zhihu_client_obj

    async def launch_browser(
            self,
            chromium: BrowserType,
            playwright_proxy: Optional[Dict],
            user_agent: Optional[str],
            headless: bool = True
    ) -> BrowserContext:
        """Launch browser and create browser context"""
        utils.logger.info("[ZhihuCrawler.launch_browser] Begin create browser context ...")
        if config.SAVE_LOGIN_STATE:
            # feat issue #14
            # we will save login state to avoid login every time
            user_data_dir = os.path.join(os.getcwd(), "browser_data",
                                         config.USER_DATA_DIR % config.PLATFORM)  # type: ignore
            browser_context = await chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                accept_downloads=True,
                headless=headless,
                proxy=playwright_proxy,  # type: ignore
                viewport={"width": 1920, "height": 1080},
                user_agent=user_agent
            )
            return browser_context
        else:
            browser = await chromium.launch(headless=headless, proxy=playwright_proxy)  # type: ignore
            browser_context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=user_agent
            )
            return browser_context

    async def launch_browser_with_cdp(self, playwright: Playwright, playwright_proxy: Optional[Dict],
                                     user_agent: Optional[str], headless: bool = True) -> BrowserContext:
        """
        使用CDP模式启动浏览器
        """
        try:
            self.cdp_manager = CDPBrowserManager()
            browser_context = await self.cdp_manager.launch_and_connect(
                playwright=playwright,
                playwright_proxy=playwright_proxy,
                user_agent=user_agent,
                headless=headless
            )

            # 显示浏览器信息
            browser_info = await self.cdp_manager.get_browser_info()
            utils.logger.info(f"[ZhihuCrawler] CDP浏览器信息: {browser_info}")

            return browser_context

        except Exception as e:
            utils.logger.error(f"[ZhihuCrawler] CDP模式启动失败，回退到标准模式: {e}")
            # 回退到标准模式
            chromium = playwright.chromium
            return await self.launch_browser(chromium, playwright_proxy, user_agent, headless)

    async def get_user_collections(self):
        """
        获取用户收藏夹数据
        """
        utils.logger.info("[ZhihuCrawler.get_user_collections] Begin get user collections ...")

        # 初始化内容检测器（用于增量爬取）
        content_checker = get_content_checker("zhihu")
        if config.CRAWL_MODE == "incremental":
            utils.logger.info("[ZhihuCrawler.get_user_collections] Incremental mode enabled, loading existing content IDs...")
            await content_checker.load_existing_content_ids()
            stats = content_checker.get_stats()
            utils.logger.info(f"[ZhihuCrawler.get_user_collections] Found {stats['total_existing']} existing content(s)")

        # 获取当前用户信息
        current_user_info = await self.zhihu_client.get_current_user_info()
        user_id = current_user_info.get("id")
        if not user_id:
            utils.logger.error("[ZhihuCrawler.get_user_collections] Failed to get current user id")
            return

        utils.logger.info(f"[ZhihuCrawler.get_user_collections] Current user id: {user_id}")

        # 获取用户收藏夹列表
        collections_data = await self.zhihu_client.get_user_collections(user_id)
        collections = collections_data.get("data", [])

        if not collections:
            utils.logger.info("[ZhihuCrawler.get_user_collections] No collections found")
            return

        utils.logger.info(f"[ZhihuCrawler.get_user_collections] Found {len(collections)} collections")

        # 遍历每个收藏夹
        for collection in collections:
            collection_id = collection.get("id")
            collection_title = collection.get("title", "未知收藏夹")
            collection_count = collection.get("answer_count", 0)

            utils.logger.info(f"[ZhihuCrawler.get_user_collections] Processing collection: {collection_title} (ID: {collection_id}, Count: {collection_count})")

            if collection_count == 0:
                utils.logger.info(f"[ZhihuCrawler.get_user_collections] Collection {collection_title} is empty, skipping")
                continue

            # 获取收藏夹内容（每个收藏夹独立存储）
            await self.get_collection_contents(collection_id, collection_title)

        # 显示最终统计信息
        if config.CRAWL_MODE == "incremental":
            content_checker = get_content_checker("zhihu")
            stats = content_checker.get_stats()
            utils.logger.info(f"[ZhihuCrawler.get_user_collections] Incremental mode completed. Total existing content: {stats['total_existing']}")

        utils.logger.info(f"[ZhihuCrawler.get_user_collections] Finished processing all collections (Mode: {config.CRAWL_MODE})")

    async def get_collection_contents(self, collection_id: str, collection_title: str):
        """
        获取指定收藏夹的内容
        Args:
            collection_id: 收藏夹ID
            collection_title: 收藏夹标题
        """
        utils.logger.info(f"[ZhihuCrawler.get_collection_contents] Begin get collection contents for: {collection_title}")

        # 检查数量限制配置
        max_items = config.CRAWLER_MAX_COLLECTION_ITEMS_COUNT
        if max_items > 0:
            utils.logger.info(f"[ZhihuCrawler.get_collection_contents] Max items limit set to: {max_items}")
        else:
            utils.logger.info(f"[ZhihuCrawler.get_collection_contents] No limit set, will crawl all items")

        page = 0
        limit = 20
        all_contents = []

        # 为每个收藏夹创建独立的存储实例（支持实时分片）
        from store.zhihu import ZhihuStoreFactory
        collection_store = ZhihuStoreFactory.create_collection_store()

        # 设置收藏夹标题用于文件命名
        if hasattr(collection_store, 'set_collection_title'):
            collection_store.set_collection_title(collection_title)

        utils.logger.info(f"[ZhihuCrawler.get_collection_contents] Created independent collection store for: {collection_title}")

        # 创建信号量控制并发
        detail_semaphore = asyncio.Semaphore(3)  # 限制同时获取详情的数量

        while True:
            offset = page * limit
            utils.logger.info(f"[ZhihuCrawler.get_collection_contents] Getting page {page + 1} (offset: {offset})")

            try:
                collection_items = await self.zhihu_client.get_collection_items(
                    collection_id=collection_id,
                    offset=offset,
                    limit=limit
                )

                items = collection_items.get("data", [])
                if not items:
                    utils.logger.info(f"[ZhihuCrawler.get_collection_contents] No more items in collection: {collection_title}")
                    break

                utils.logger.info(f"[ZhihuCrawler.get_collection_contents] Found {len(items)} items in page {page + 1}")

                # 处理每个收藏项
                for item in items:
                    # 检查是否达到数量限制
                    if max_items > 0 and len(all_contents) >= max_items:
                        utils.logger.info(f"[ZhihuCrawler.get_collection_contents] Reached max items limit ({max_items}), stopping")
                        break

                    content = item.get("content")
                    if not content:
                        continue

                    # 提取内容信息
                    content_type = content.get("type", "unknown")
                    content_id = content.get("id")
                    content_url = content.get("url", "")

                    # 根据内容类型获取正确的标题
                    if content_type == "answer":
                        # 回答类型：使用问题标题
                        question = content.get("question", {})
                        content_title = question.get("title", "无标题")
                    elif content_type == "article":
                        # 文章类型：使用文章标题
                        content_title = content.get("title", "无标题")
                    else:
                        content_title = content.get("title", "无标题")

                    utils.logger.info(f"[ZhihuCrawler.get_collection_contents] Processing {content_type}: {content_title}")

                    # 增量模式：检查内容是否已存在
                    if config.CRAWL_MODE == "incremental":
                        content_checker = get_content_checker("zhihu")
                        if await content_checker.content_exists(content_id):
                            utils.logger.info(f"[ZhihuCrawler.get_collection_contents] Content {content_id} already exists, skipping...")
                            continue

                    # 根据内容类型处理
                    if content_type == "answer":
                        # 处理回答
                        zhihu_content = self._extract_answer_from_collection_item(content)
                    elif content_type == "article":
                        # 处理文章
                        zhihu_content = self._extract_article_from_collection_item(content)
                    else:
                        utils.logger.warning(f"[ZhihuCrawler.get_collection_contents] Unsupported content type: {content_type}")
                        continue

                    if zhihu_content:
                        # 设置来源关键词为收藏夹标题
                        zhihu_content.source_keyword = collection_title
                        utils.logger.debug(f"[ZhihuCrawler.get_collection_contents] Set source_keyword to '{collection_title}' for content {content_id}")

                        # 尝试获取完整内容详情
                        try:
                            full_content = await self._get_full_content_detail(
                                content_url, content_type, detail_semaphore
                            )

                            if full_content:
                                # 合并完整内容到收藏数据中，保留收藏的元数据
                                zhihu_content.content_text = full_content.content_text or zhihu_content.content_text
                                zhihu_content.desc = full_content.desc or zhihu_content.desc

                                # 更新时间字段（如果完整内容中有有效时间）
                                if full_content.created_time and full_content.created_time > 0:
                                    zhihu_content.created_time = full_content.created_time
                                if full_content.updated_time and full_content.updated_time > 0:
                                    zhihu_content.updated_time = full_content.updated_time

                                # 更新question_id（仅对回答类型）
                                if content_type == "answer" and full_content.question_id:
                                    zhihu_content.question_id = full_content.question_id

                                # 更新其他可能的字段
                                if full_content.voteup_count:
                                    zhihu_content.voteup_count = full_content.voteup_count
                                if full_content.comment_count:
                                    zhihu_content.comment_count = full_content.comment_count

                                # 更新作者信息（如果完整内容中有更详细的作者信息）
                                if hasattr(full_content, 'author') and full_content.author and hasattr(full_content.author, 'user_id'):
                                    if hasattr(zhihu_content, 'author'):
                                        zhihu_content.author = full_content.author

                                utils.logger.info(f"[ZhihuCrawler.get_collection_contents] Successfully got full content for: {content_title}")
                            else:
                                utils.logger.warning(f"[ZhihuCrawler.get_collection_contents] Failed to get full content for: {content_title}")

                        except Exception as e:
                            utils.logger.error(f"[ZhihuCrawler.get_collection_contents] Error getting full content for {content_title}: {e}")

                        # 获取问题详情（第二阶段新增功能）
                        if zhihu_content.content_type == "answer" and zhihu_content.question_id:
                            question_info = await self._get_question_info_with_cache(zhihu_content.question_id)
                            if question_info:
                                zhihu_content.question_title = question_info.get("question_title", "")
                                zhihu_content.question_detail = question_info.get("question_detail", "")
                                zhihu_content.question_tags = question_info.get("question_tags", [])
                                zhihu_content.question_follower_count = question_info.get("question_follower_count", 0)
                                zhihu_content.question_answer_count = question_info.get("question_answer_count", 0)
                                zhihu_content.question_view_count = question_info.get("question_view_count", 0)
                                utils.logger.info(f"[ZhihuCrawler.get_collection_contents] Added question info for answer {content_id}")

                        # 检测是否包含图片（在获取问题详情之后）
                        self._detect_images_in_content(zhihu_content)

                        # 处理图片并获取图片信息（一步到位）
                        images_info = []
                        # 根据跳过评论图片模式决定是否需要打开浏览器
                        needs_browser = False
                        if config.ENABLE_GET_IMAGES:
                            if config.SKIP_COMMENTS_PIC:
                                # 跳过评论图片模式：只有问题或答案有图片才打开浏览器
                                needs_browser = zhihu_content.has_question_images or zhihu_content.has_answer_images
                            else:
                                # 完整模式：有任何图片都打开浏览器
                                needs_browser = zhihu_content.has_question_images or zhihu_content.has_answer_images or zhihu_content.has_comment_images

                        if needs_browser:
                            images_info = await self._process_images_with_browser(zhihu_content)
                            zhihu_content.images_processed = True

                            # 分类图片信息
                            question_images = [img for img in images_info if img['filename'].startswith('question_')]
                            answer_images = [img for img in images_info if img['filename'].startswith('answer_')]
                            comment_images = [img for img in images_info if img['filename'].startswith('comment_')]

                            # 将content_text中的[图片]占位符替换为真实的图片文件名（仅答案图片）
                            if answer_images and zhihu_content.content_text:
                                from tools.crawler_util import replace_image_placeholders_with_filenames
                                zhihu_content.content_text = replace_image_placeholders_with_filenames(
                                    zhihu_content.content_text, answer_images
                                )
                                utils.logger.info(f"[ZhihuCrawler.get_collection_contents] Replaced {len(answer_images)} answer image placeholders in content {content_id}")

                            # 处理问题详情中的图片占位符
                            if question_images and zhihu_content.question_detail:
                                from tools.crawler_util import replace_image_placeholders_with_filenames_enhanced
                                zhihu_content.question_detail = replace_image_placeholders_with_filenames_enhanced(
                                    zhihu_content.question_detail, question_images, "[图片]"
                                )
                                utils.logger.info(f"[ZhihuCrawler.get_collection_contents] Replaced {len(question_images)} question image placeholders")

                            # 处理评论中的图片占位符
                            if comment_images and zhihu_content.comments:
                                self._process_comment_images(zhihu_content.comments, comment_images)
                                utils.logger.info(f"[ZhihuCrawler.get_collection_contents] Processed {len(comment_images)} comment images")

                        all_contents.append(zhihu_content)
                        # 保存内容到收藏夹专用存储
                        if hasattr(collection_store, 'store_content'):
                            await collection_store.store_content(zhihu_content.model_dump())
                        else:
                            # 兼容其他存储方式
                            await zhihu_store.update_zhihu_content(zhihu_content, images_info)

                        # 增量模式：更新已处理内容ID缓存
                        if config.CRAWL_MODE == "incremental":
                            content_checker = get_content_checker("zhihu")
                            content_checker.add_content_id(zhihu_content.content_id)

                        # 添加延迟避免请求过快
                        await asyncio.sleep(0.5)

                # 检查是否达到数量限制，如果达到则退出外层循环
                if max_items > 0 and len(all_contents) >= max_items:
                    utils.logger.info(f"[ZhihuCrawler.get_collection_contents] Reached max items limit ({max_items}), stopping collection processing")
                    break

                page += 1

                # 添加延迟避免请求过快
                await asyncio.sleep(1)

            except Exception as e:
                utils.logger.error(f"[ZhihuCrawler.get_collection_contents] Error getting collection items: {e}")
                break

        utils.logger.info(f"[ZhihuCrawler.get_collection_contents] Finished processing collection: {collection_title}, total items: {len(all_contents)}")

        # 批量获取评论
        if config.ENABLE_GET_COMMENTS and all_contents:
            await self._batch_get_collection_comments(all_contents, collection_store)

        # 收藏夹处理完成后，flush剩余的缓存数据（不足20条的部分）
        if hasattr(collection_store, 'flush_to_files'):
            utils.logger.info(f"[ZhihuCrawler.get_collection_contents] Flushing remaining cached data for collection: {collection_title}")
            await collection_store.flush_to_files()
            utils.logger.info(f"[ZhihuCrawler.get_collection_contents] Collection {collection_title} processing completed with final flush")
        else:
            utils.logger.warning(f"[ZhihuCrawler.get_collection_contents] Collection store does not support flush_to_files method")

    async def _batch_get_collection_comments(self, content_list: List[ZhihuContent], collection_store):
        """
        批量获取收藏夹内容的评论（专用于收藏夹存储）
        Args:
            content_list: 内容列表
            collection_store: 收藏夹存储实例
        """
        utils.logger.info(f"[ZhihuCrawler._batch_get_collection_comments] Begin batch get comments for {len(content_list)} contents")

        semaphore = asyncio.Semaphore(1)  # 控制并发数

        async def get_content_comments(content_item: ZhihuContent):
            async with semaphore:
                try:
                    # 如果不跳过评论图片处理且已经处理过图片，使用浏览器解析评论（方案三）
                    if not config.SKIP_COMMENTS_PIC and content_item.images_processed:
                        # 导航到内容页面
                        await self.context_page.goto(content_item.content_url)
                        await asyncio.sleep(2)

                        # 展开评论（只展开第一个评论区）
                        await self._expand_comments_single()

                        # 从浏览器解析评论
                        browser_comments = await self._parse_comments_from_browser(content_item.content_id)

                        # 在添加评论之前处理图片占位符
                        # 检测浏览器解析的评论中是否有图片占位符
                        has_comment_images = False
                        if browser_comments:
                            for comment in browser_comments:
                                if "[图片]" in comment.content:
                                    has_comment_images = True
                                    content_item.has_comment_images = True
                                    utils.logger.info(f"[ZhihuCrawler._batch_get_collection_comments] Detected comment images in browser comments for {content_item.content_id}")
                                    break

                        if browser_comments and has_comment_images:
                            # 查找该内容的评论图片
                            image_dir = f"data/zhihu/images/collection_contents/{content_item.content_id}"
                            comment_images = []

                            # 扫描图片目录，找出评论图片，按文件名排序确保顺序
                            import os
                            if os.path.exists(image_dir):
                                comment_files = []
                                for filename in os.listdir(image_dir):
                                    if filename.startswith('comment_') and filename.endswith(('.jpg', '.png', '.jpeg', '.webp')):
                                        comment_files.append(filename)

                                # 按文件名排序，确保comment_000.jpg在comment_001.jpg前面
                                comment_files.sort()
                                for filename in comment_files:
                                    comment_images.append({'filename': filename})

                            if comment_images:
                                # 使用增强版的占位符替换，按顺序替换
                                self._process_comment_images_enhanced(browser_comments, comment_images)
                                utils.logger.info(f"[ZhihuCrawler._batch_get_collection_comments] Processed {len(comment_images)} comment image placeholders for {content_item.content_id}")

                        content_item.comments.extend(browser_comments)
                        utils.logger.info(f"[ZhihuCrawler._batch_get_collection_comments] Parsed {len(browser_comments)} comments from browser for {content_item.content_id}")

                    else:
                        # 使用原有的API方式获取评论
                        if config.ENABLE_HOT_COMMENTS:
                            await self._get_hot_comments(content_item, is_collection_crawl=True)
                        else:
                            # 获取所有评论，不使用回调函数，直接返回评论数据
                            comments_data = await self.zhihu_client.get_note_all_comments(
                                content=content_item,
                                crawl_interval=random.random(),
                                callback=None
                            )
                            # 手动将评论数据添加到content_item.comments中
                            if comments_data and isinstance(comments_data, list):
                                content_item.comments.extend(comments_data)

                    # 将评论添加到收藏夹存储
                    if hasattr(collection_store, 'store_comment'):
                        for comment in content_item.comments:
                            comment_data = comment.model_dump()
                            comment_data["content_id"] = content_item.content_id
                            comment_data["content_type"] = content_item.content_type

                            # 如果是浏览器解析的评论，移除无效字段
                            if not config.SKIP_COMMENTS_PIC and content_item.images_processed:
                                # 移除浏览器解析评论中的无效字段
                                invalid_fields = ['sub_comment_count', 'dislike_count', 'user_id', 'user_avatar']
                                for field in invalid_fields:
                                    comment_data.pop(field, None)

                            # 调试日志：检查评论内容
                            if "[图片]" in comment_data["content"] or "[pic:" in comment_data["content"]:
                                utils.logger.info(f"[ZhihuCrawler._batch_get_collection_comments] Storing comment {comment.comment_id}: {comment_data['content'][:100]}")

                            await collection_store.store_comment(comment_data)

                    utils.logger.info(f"[ZhihuCrawler._batch_get_collection_comments] Got {len(content_item.comments)} comments for content: {content_item.content_id}")

                    # 检测评论中的图片（如果不跳过评论图片处理且使用API方式获取评论的话）
                    if not config.SKIP_COMMENTS_PIC and content_item.comments and not content_item.images_processed:
                        for comment in content_item.comments:
                            if "查看图片" in comment.content or "[图片]" in comment.content:
                                content_item.has_comment_images = True
                                utils.logger.info(f"[ZhihuCrawler._batch_get_collection_comments] Detected comment images in content: {content_item.content_id}")
                                break

                    # 确保在skip-comments-pic模式下，has_comment_images永远为False
                    if config.SKIP_COMMENTS_PIC:
                        content_item.has_comment_images = False

                except Exception as e:
                    utils.logger.error(f"[ZhihuCrawler._batch_get_collection_comments] Error getting comments for {content_item.content_id}: {e}")

        # 并发获取评论
        tasks = [get_content_comments(content) for content in content_list]
        await asyncio.gather(*tasks, return_exceptions=True)

        utils.logger.info(f"[ZhihuCrawler._batch_get_collection_comments] Finished batch get comments")

    def _format_gender_text(self, gender: int) -> str:
        """
        格式化性别文本
        Args:
            gender: 性别数字

        Returns:
            性别文本
        """
        if gender == 1:
            return "男"
        elif gender == 0:
            return "女"
        else:
            return "未知"

    def _parse_content_ids_from_url(self, content_url: str, content_type: str) -> Optional[Dict[str, str]]:
        """
        从URL中解析出内容ID
        Args:
            content_url: 内容URL
            content_type: 内容类型

        Returns:
            包含ID信息的字典
        """
        try:
            if content_type == "answer":
                # URL格式: https://www.zhihu.com/question/123456/answer/789012
                parts = content_url.split("/")
                if len(parts) >= 6:
                    question_id = parts[-3]
                    answer_id = parts[-1]
                    return {"question_id": question_id, "answer_id": answer_id}
            elif content_type == "article":
                # URL格式: https://zhuanlan.zhihu.com/p/123456
                parts = content_url.split("/")
                if len(parts) >= 2:
                    article_id = parts[-1]
                    return {"article_id": article_id}
            elif content_type == "zvideo":
                # URL格式: https://www.zhihu.com/zvideo/123456
                parts = content_url.split("/")
                if len(parts) >= 2:
                    video_id = parts[-1]
                    return {"video_id": video_id}
        except Exception as e:
            utils.logger.error(f"[ZhihuCrawler._parse_content_ids_from_url] Error parsing URL {content_url}: {e}")

        return None

    async def _get_full_content_detail(self, content_url: str, content_type: str, semaphore: asyncio.Semaphore) -> Optional[ZhihuContent]:
        """
        获取内容的完整详情
        Args:
            content_url: 内容URL
            content_type: 内容类型
            semaphore: 并发控制信号量

        Returns:
            完整的内容详情
        """
        async with semaphore:
            try:
                ids = self._parse_content_ids_from_url(content_url, content_type)
                if not ids:
                    utils.logger.warning(f"[ZhihuCrawler._get_full_content_detail] Cannot parse IDs from URL: {content_url}")
                    return None

                utils.logger.info(f"[ZhihuCrawler._get_full_content_detail] Getting full content for {content_type}: {content_url}")

                # 方法1：通过API获取结构化数据
                zhihu_content = None
                if content_type == "answer" and "question_id" in ids and "answer_id" in ids:
                    zhihu_content = await self.zhihu_client.get_answer_info(ids["question_id"], ids["answer_id"])
                elif content_type == "article" and "article_id" in ids:
                    zhihu_content = await self.zhihu_client.get_article_info(ids["article_id"])
                elif content_type == "zvideo" and "video_id" in ids:
                    zhihu_content = await self.zhihu_client.get_video_info(ids["video_id"])
                else:
                    utils.logger.warning(f"[ZhihuCrawler._get_full_content_detail] Unsupported content type: {content_type}")
                    return None

                return zhihu_content

            except Exception as e:
                utils.logger.error(f"[ZhihuCrawler._get_full_content_detail] Error getting full content for {content_url}: {e}")
                return None

    async def _get_question_info_with_cache(self, question_id: str) -> Optional[Dict]:
        """
        获取问题详情信息（带缓存）
        Args:
            question_id: 问题ID

        Returns:
            问题详情字典
        """
        if not question_id:
            return None

        # 检查缓存
        if question_id in self.question_cache:
            utils.logger.info(f"[ZhihuCrawler._get_question_info_with_cache] Using cached question info for {question_id}")
            return self.question_cache[question_id]

        try:
            # 获取问题详情
            utils.logger.info(f"[ZhihuCrawler._get_question_info_with_cache] Fetching question info for {question_id}")
            question_info = await self.zhihu_client.get_question_info(question_id)

            if question_info:
                # 缓存结果
                self.question_cache[question_id] = question_info
                utils.logger.info(f"[ZhihuCrawler._get_question_info_with_cache] Cached question info for {question_id}")
                return question_info
            else:
                utils.logger.warning(f"[ZhihuCrawler._get_question_info_with_cache] No question info found for {question_id}")
                return None

        except Exception as e:
            utils.logger.error(f"[ZhihuCrawler._get_question_info_with_cache] Error getting question info for {question_id}: {e}")
            return None

    def _extract_answer_from_collection_item(self, content: Dict) -> Optional[ZhihuContent]:
        """
        从收藏项中提取回答信息
        Args:
            content: 收藏项内容数据

        Returns:
            ZhihuContent对象
        """
        try:
            question = content.get("question", {})
            author = content.get("author", {})

            # 提取用户信息
            user_id = str(author.get("id", ""))
            user_nickname = author.get("name", "")
            user_avatar = author.get("avatar_url", "")
            user_url_token = author.get("url_token", "")
            # 构造用户链接
            from constant import zhihu as zhihu_constant
            user_link = f"{zhihu_constant.ZHIHU_URL}/people/{user_url_token}" if user_url_token else ""

            # 转换时间戳为可读格式
            def convert_timestamp_to_readable(timestamp):
                """将时间戳转换为可读格式"""
                if timestamp == 0:
                    return "0"
                try:
                    from tools.time_util import get_time_str_from_unix_time
                    return get_time_str_from_unix_time(timestamp)
                except Exception:
                    return str(timestamp)

            created_time_readable = convert_timestamp_to_readable(content.get("created_time", 0))
            updated_time_readable = convert_timestamp_to_readable(content.get("updated_time", 0))

            utils.logger.debug(f"[ZhihuCrawler._extract_answer_from_collection_item] Mapping fields for answer {content.get('id')}: voteup_count={content.get('voteup_count', 0)}, comment_count={content.get('comment_count', 0)}, created_time={created_time_readable}")

            return ZhihuContent(
                content_id=str(content.get("id", "")),
                content_type="answer",
                content_url=content.get("url", ""),
                title=question.get("title", ""),
                desc=content.get("excerpt", ""),
                note_id=str(content.get("id", "")),
                created_time=created_time_readable,
                updated_time=updated_time_readable,
                voteup_count=content.get("voteup_count", 0),  # 修复：使用正确的字段名
                comment_count=content.get("comment_count", 0),  # 修复：使用正确的字段名
                shared_count=0,
                topics=question.get("topics", []),
                content_url_token=content.get("url", "").split("/")[-1] if content.get("url") else "",
                # 添加用户信息到顶级字段
                user_id=user_id,
                user_link=user_link,
                user_nickname=user_nickname,
                user_avatar=user_avatar,
                user_url_token=user_url_token,
                author=ZhihuCreator(
                    user_id=user_id,
                    user_nickname=user_nickname,
                    url_token=user_url_token,
                    user_avatar=user_avatar,
                    gender=self._format_gender_text(author.get("gender", -1)),
                    follows=author.get("follower_count", 0),
                    fans=author.get("following_count", 0),
                    voteup_count=author.get("voteup_count", 0),
                    thanked_count=author.get("thanked_count", 0)
                )
            )
        except Exception as e:
            utils.logger.error(f"[ZhihuCrawler._extract_answer_from_collection_item] Error extracting answer: {e}")
            return None

    def _extract_article_from_collection_item(self, content: Dict) -> Optional[ZhihuContent]:
        """
        从收藏项中提取文章信息
        Args:
            content: 收藏项内容数据

        Returns:
            ZhihuContent对象
        """
        try:
            author = content.get("author", {})

            # 提取用户信息
            user_id = str(author.get("id", ""))
            user_nickname = author.get("name", "")
            user_avatar = author.get("avatar_url", "")
            user_url_token = author.get("url_token", "")
            # 构造用户链接
            from constant import zhihu as zhihu_constant
            user_link = f"{zhihu_constant.ZHIHU_URL}/people/{user_url_token}" if user_url_token else ""

            # 转换时间戳为可读格式
            def convert_timestamp_to_readable(timestamp):
                """将时间戳转换为可读格式"""
                if timestamp == 0:
                    return "0"
                try:
                    from tools.time_util import get_time_str_from_unix_time
                    return get_time_str_from_unix_time(timestamp)
                except Exception:
                    return str(timestamp)

            created_time_readable = convert_timestamp_to_readable(content.get("created", 0))
            updated_time_readable = convert_timestamp_to_readable(content.get("updated", 0))

            utils.logger.debug(f"[ZhihuCrawler._extract_article_from_collection_item] Mapping fields for article {content.get('id')}: voteup_count={content.get('voteup_count', 0)}, comment_count={content.get('comment_count', 0)}, created_time={created_time_readable}")

            return ZhihuContent(
                content_id=str(content.get("id", "")),
                content_type="article",
                content_url=content.get("url", ""),
                title=content.get("title", ""),
                desc=content.get("excerpt", ""),
                note_id=str(content.get("id", "")),
                created_time=created_time_readable,
                updated_time=updated_time_readable,
                voteup_count=content.get("voteup_count", 0),  # 修复：使用正确的字段名
                comment_count=content.get("comment_count", 0),  # 修复：使用正确的字段名
                shared_count=0,
                topics=[],
                content_url_token=content.get("url", "").split("/")[-1] if content.get("url") else "",
                # 添加用户信息到顶级字段
                user_id=user_id,
                user_link=user_link,
                user_nickname=user_nickname,
                user_avatar=user_avatar,
                user_url_token=user_url_token,
                author=ZhihuCreator(
                    user_id=user_id,
                    user_nickname=user_nickname,
                    url_token=user_url_token,
                    user_avatar=user_avatar,
                    gender=self._format_gender_text(author.get("gender", -1)),
                    follows=author.get("follower_count", 0),
                    fans=author.get("following_count", 0),
                    voteup_count=author.get("voteup_count", 0),
                    thanked_count=author.get("thanked_count", 0)
                )
            )
        except Exception as e:
            utils.logger.error(f"[ZhihuCrawler._extract_article_from_collection_item] Error extracting article: {e}")
            return None

    def _detect_images_in_content(self, zhihu_content: ZhihuContent) -> None:
        """
        检测内容中是否包含图片，分别设置三个标志
        Args:
            zhihu_content: 知乎内容对象
        """
        # 检查描述和内容中是否有图片占位符
        desc = zhihu_content.desc or ""
        content = zhihu_content.content_text or ""
        question_detail = zhihu_content.question_detail or ""

        # 检测问题图片
        zhihu_content.has_question_images = "[图片]" in question_detail

        # 检测答案图片
        zhihu_content.has_answer_images = "[图片]" in desc or "[图片]" in content

        # 评论图片检测将在评论获取后进行，这里先设为默认值
        zhihu_content.has_comment_images = False

        # 记录检测结果
        if zhihu_content.has_question_images or zhihu_content.has_answer_images or zhihu_content.has_comment_images:
            utils.logger.info(f"[ZhihuCrawler._detect_images_in_content] Detected images in content {zhihu_content.content_id}: question={zhihu_content.has_question_images}, answer={zhihu_content.has_answer_images}, comment={zhihu_content.has_comment_images}")

    async def _process_images_with_browser(self, zhihu_content: ZhihuContent) -> List[Dict]:
        """
        使用浏览器获取HTML并处理图片（一步到位）
        Args:
            zhihu_content: 知乎内容对象

        Returns:
            List[Dict]: 图片信息列表
        """
        if not config.ENABLE_GET_IMAGES:
            return []

        content_url = zhihu_content.content_url
        content_id = zhihu_content.content_id

        try:
            utils.logger.info(f"[ZhihuCrawler._process_images_with_browser] Processing images for {content_id}")

            # 使用现有浏览器会话获取HTML
            await self.context_page.goto(content_url, wait_until='networkidle')
            await asyncio.sleep(3)  # 等待页面完全加载

            # 尝试点击"显示全部"按钮展开问题内容
            await self._expand_question_content()

            # 尝试点击答案的展开按钮（如果有）
            await self._expand_answer_content()

            # 尝试点击评论展开按钮（如果不跳过评论图片处理的话）
            if not config.SKIP_COMMENTS_PIC:
                await self._expand_comments()

            # 等待内容完全展开
            await asyncio.sleep(3)

            # 获取页面HTML
            page_html = await self.context_page.content()

            utils.logger.info(f"[ZhihuCrawler._process_images_with_browser] Got HTML content, length: {len(page_html)}")

            # 使用图片处理器提取和下载图片
            async with ZhihuImageProcessor() as image_processor:
                # 提取图片URL
                images = image_processor.extract_images_from_html(page_html, content_url)

                if not images:
                    utils.logger.info(f"[ZhihuCrawler._process_images_with_browser] No images found in {content_id}")
                    return []

                utils.logger.info(f"[ZhihuCrawler._process_images_with_browser] Found {len(images)} images in {content_id}")

                # 下载图片并构建信息
                images_info = []
                for image_info in images:
                    try:
                        # 下载图片
                        image_content = await image_processor.download_image(image_info)

                        if image_content:
                            # 保存图片到本地
                            from store.zhihu.zhihu_store_image import ZhihuStoreImage
                            image_store = ZhihuStoreImage()
                            image_content_item = {
                                "content_id": content_id,
                                "pic_content": image_content,
                                "extension_file_name": image_info['filename']
                            }
                            await image_store.store_image(image_content_item)

                            # 构建图片信息
                            img_info = {
                                'url': image_info['url'],
                                'local_path': f"data/zhihu/images/collection_contents/{content_id}/{image_info['filename']}",
                                'filename': image_info['filename'],
                                'alt': image_info['alt'],
                                'title': image_info['title'],
                                'size': len(image_content),
                                'download_time': utils.get_current_date()
                            }
                            images_info.append(img_info)

                            utils.logger.info(f"[ZhihuCrawler._process_images_with_browser] Downloaded image: {image_info['filename']}")

                    except Exception as e:
                        utils.logger.error(f"[ZhihuCrawler._process_images_with_browser] Error downloading image: {e}")
                        continue

                # 添加延迟避免请求过快
                await asyncio.sleep(2)

                utils.logger.info(f"[ZhihuCrawler._process_images_with_browser] Successfully processed {len(images_info)} images for {content_id}")
                return images_info

        except Exception as e:
            utils.logger.error(f"[ZhihuCrawler._process_images_with_browser] Error processing images for {content_id}: {e}")
            return []

    async def _expand_question_content(self):
        """
        尝试展开问题详情内容
        """
        try:
            # 尝试查找并点击问题的"显示全部"按钮
            show_all_button_selector = 'button.QuestionRichText-more, button.Button.QuestionRichText-more'
            show_all_button = await self.context_page.query_selector(show_all_button_selector)

            if show_all_button:
                utils.logger.info("[ZhihuCrawler._expand_question_content] Found 'Show All' button for question, clicking...")
                await show_all_button.click()
                await asyncio.sleep(1)  # 等待内容展开
                utils.logger.info("[ZhihuCrawler._expand_question_content] Question content expanded")
            else:
                utils.logger.info("[ZhihuCrawler._expand_question_content] No 'Show All' button found for question")

        except Exception as e:
            utils.logger.warning(f"[ZhihuCrawler._expand_question_content] Error expanding question content: {e}")

    async def _expand_answer_content(self):
        """
        尝试展开答案内容
        """
        try:
            # 尝试查找并点击答案的"显示全部"按钮
            answer_show_all_selector = '.RichContent-inner button.Button.ContentItem-expandButton'
            answer_show_all_buttons = await self.context_page.query_selector_all(answer_show_all_selector)

            if answer_show_all_buttons:
                utils.logger.info(f"[ZhihuCrawler._expand_answer_content] Found {len(answer_show_all_buttons)} 'Show All' buttons for answers")
                for i, button in enumerate(answer_show_all_buttons):
                    try:
                        await button.click()
                        utils.logger.info(f"[ZhihuCrawler._expand_answer_content] Clicked 'Show All' button {i+1}")
                        await asyncio.sleep(0.5)  # 短暂等待，避免点击过快
                    except Exception as e:
                        utils.logger.warning(f"[ZhihuCrawler._expand_answer_content] Error clicking button {i+1}: {e}")

                # 等待所有内容展开
                await asyncio.sleep(1)
                utils.logger.info("[ZhihuCrawler._expand_answer_content] Answer content expanded")
            else:
                utils.logger.info("[ZhihuCrawler._expand_answer_content] No 'Show All' buttons found for answers")

        except Exception as e:
            utils.logger.warning(f"[ZhihuCrawler._expand_answer_content] Error expanding answer content: {e}")

    async def _expand_comments(self):
        """
        尝试展开评论区域
        """
        try:
            # 查找评论展开按钮
            comment_button_selectors = [
                'button.ContentItem-action[class*="Button--withLabel"]',  # 基于info.txt中的信息
                'button.ContentItem-action',
                '.ContentItem-actions button[class*="Comment"]',
                '.RichContent-actions button[class*="Comment"]'
            ]

            comment_buttons = []
            for selector in comment_button_selectors:
                buttons = await self.context_page.query_selector_all(selector)
                if buttons:
                    # 过滤出包含"条评论"文本的按钮
                    for button in buttons:
                        try:
                            button_text = await button.inner_text()
                            if "条评论" in button_text:
                                comment_buttons.append(button)
                                utils.logger.info(f"[ZhihuCrawler._expand_comments] Found comment button with text: {button_text}")
                        except Exception as e:
                            utils.logger.debug(f"[ZhihuCrawler._expand_comments] Error getting button text: {e}")

                    if comment_buttons:
                        utils.logger.info(f"[ZhihuCrawler._expand_comments] Found comment buttons using selector: {selector}")
                        break

            if comment_buttons:
                utils.logger.info(f"[ZhihuCrawler._expand_comments] Found {len(comment_buttons)} comment buttons to click")
                for i, button in enumerate(comment_buttons):
                    try:
                        await button.click()
                        utils.logger.info(f"[ZhihuCrawler._expand_comments] Clicked comment button {i+1}")
                        await asyncio.sleep(1)  # 等待评论加载
                    except Exception as e:
                        utils.logger.warning(f"[ZhihuCrawler._expand_comments] Error clicking comment button {i+1}: {e}")

                # 等待评论完全加载
                await asyncio.sleep(2)
                utils.logger.info("[ZhihuCrawler._expand_comments] Comments expanded")
            else:
                utils.logger.info("[ZhihuCrawler._expand_comments] No comment buttons found")

        except Exception as e:
            utils.logger.warning(f"[ZhihuCrawler._expand_comments] Error expanding comments: {e}")

    async def _expand_comments_single(self):
        """
        展开评论（只展开第一个评论区，用于方案三）
        """
        try:
            # 等待页面加载
            await asyncio.sleep(2)

            # 方法1：通过更精确的选择器查找评论按钮
            comment_buttons = await self.context_page.query_selector_all('.ContentItem-actions button[class*="Comment"]')

            if comment_buttons:
                # 找到评论按钮，验证文本内容
                for button in comment_buttons:
                    button_text = await button.inner_text()
                    # 检查是否为评论按钮（包含"评论"或数字+"条评论"）
                    if "评论" in button_text or "条评论" in button_text:
                        utils.logger.info(f"[ZhihuCrawler._expand_comments_single] Found comment button with text: {button_text}")

                        await button.click()
                        utils.logger.info(f"[ZhihuCrawler._expand_comments_single] Clicked comment button")

                        # 等待评论加载
                        await asyncio.sleep(3)
                        utils.logger.info(f"[ZhihuCrawler._expand_comments_single] Comment section expanded")
                        return

                utils.logger.warning(f"[ZhihuCrawler._expand_comments_single] Found buttons but none are comment buttons")

            # 方法2：备用选择器 - 通过按钮文本直接查找
            all_buttons = await self.context_page.query_selector_all('.ContentItem-actions button')
            if all_buttons:
                for button in all_buttons:
                    try:
                        button_text = await button.inner_text()
                        # 检查是否为评论按钮
                        if "评论" in button_text or "条评论" in button_text:
                            utils.logger.info(f"[ZhihuCrawler._expand_comments_single] Found comment button using backup method: {button_text}")

                            await button.click()
                            utils.logger.info(f"[ZhihuCrawler._expand_comments_single] Clicked comment button")

                            # 等待评论加载
                            await asyncio.sleep(3)
                            utils.logger.info(f"[ZhihuCrawler._expand_comments_single] Comment section expanded")
                            return
                    except Exception as e:
                        # 跳过无法获取文本的按钮
                        continue

                utils.logger.warning(f"[ZhihuCrawler._expand_comments_single] No comment buttons found in {len(all_buttons)} buttons")
            else:
                utils.logger.warning(f"[ZhihuCrawler._expand_comments_single] No buttons found at all")

        except Exception as e:
            utils.logger.warning(f"[ZhihuCrawler._expand_comments_single] Error expanding comment section: {e}")

    async def _parse_comments_from_browser(self, content_id: str) -> List[ZhihuComment]:
        """
        从浏览器页面直接解析评论内容和图片（方案三）
        只在非--skip-comments-pic模式下使用
        Args:
            content_id: 内容ID
        Returns:
            List[ZhihuComment]: 解析出的评论列表
        """
        comments = []
        try:
            # 获取页面HTML
            html_content = await self.context_page.content()
            soup = BeautifulSoup(html_content, 'html.parser')

            # 查找所有评论容器
            comment_containers = soup.select('div[data-id]')
            utils.logger.info(f"[ZhihuCrawler._parse_comments_from_browser] Found {len(comment_containers)} comment containers")

            for container in comment_containers:
                try:
                    # 获取评论ID
                    comment_id = container.get('data-id')
                    if not comment_id:
                        continue

                    # 获取评论内容
                    content_elem = container.select_one('.CommentContent.css-1jpzztt')
                    if not content_elem:
                        continue

                    # 提取评论文本内容（排除图片）
                    comment_text = ""
                    for elem in content_elem.children:
                        if hasattr(elem, 'name'):
                            if elem.name == 'div' and 'comment_img' in elem.get('class', []):
                                # 遇到图片容器，添加占位符
                                comment_text += "[图片]"
                            elif elem.name == 'img' and 'sticker' in elem.get('class', []):
                                # 跳过表情图片
                                continue
                            else:
                                comment_text += elem.get_text()
                        else:
                            comment_text += str(elem)

                    # 获取用户信息
                    user_link_elem = container.select_one('a.css-10u695f')
                    user_nickname = user_link_elem.get_text() if user_link_elem else "未知用户"
                    user_link = user_link_elem.get('href') if user_link_elem else ""

                    # 获取点赞数
                    like_buttons = container.select('button.css-1vd72tl')
                    like_count = 0
                    if like_buttons:
                        like_text = like_buttons[-1].get_text()
                        try:
                            like_count = int(''.join(filter(str.isdigit, like_text)))
                        except:
                            like_count = 0

                    # 获取时间信息
                    time_elem = container.select_one('.css-12cl38p')
                    publish_time = time_elem.get_text() if time_elem else ""

                    # 获取IP位置
                    ip_elem = container.select_one('.css-ntkn7q')
                    ip_location = ip_elem.get_text() if ip_elem else ""

                    # 创建评论对象（移除无效字段）
                    comment = ZhihuComment(
                        comment_id=comment_id,
                        parent_comment_id="0",  # 只获取第一层评论
                        content=comment_text.strip(),
                        publish_time=publish_time,
                        ip_location=ip_location,
                        like_count=like_count,
                        user_link=user_link,
                        user_nickname=user_nickname
                    )

                    comments.append(comment)
                    utils.logger.debug(f"[ZhihuCrawler._parse_comments_from_browser] Parsed comment {comment_id}: {comment_text[:50]}...")

                except Exception as e:
                    utils.logger.warning(f"[ZhihuCrawler._parse_comments_from_browser] Error parsing comment container: {e}")
                    continue

            utils.logger.info(f"[ZhihuCrawler._parse_comments_from_browser] Successfully parsed {len(comments)} comments for {content_id}")
            return comments

        except Exception as e:
            utils.logger.error(f"[ZhihuCrawler._parse_comments_from_browser] Error parsing comments from browser: {e}")
            return []

    def _process_comment_images(self, comments: List[ZhihuComment], comment_images: List[Dict]):
        """
        处理评论中的图片占位符

        Args:
            comments: 评论列表
            comment_images: 评论图片信息列表
        """
        if not comments or not comment_images:
            return

        from tools.crawler_util import replace_image_placeholders_with_filenames_enhanced

        # 为每个评论处理图片占位符
        for comment in comments:
            # 处理"查看图片"占位符
            if "查看图片" in comment.content:
                # 找出当前未使用的图片
                available_images = [img for img in comment_images if not img.get('used', False)]
                if available_images:
                    # 替换占位符
                    comment.content = replace_image_placeholders_with_filenames_enhanced(
                        comment.content, available_images, "查看图片"
                    )

                    # 标记已使用的图片
                    for img in available_images[:comment.content.count('[pic:')]:
                        img['used'] = True

            # 处理"[图片]"占位符
            if "[图片]" in comment.content:
                # 找出当前未使用的图片
                available_images = [img for img in comment_images if not img.get('used', False)]
                if available_images:
                    # 替换占位符
                    comment.content = replace_image_placeholders_with_filenames_enhanced(
                        comment.content, available_images, "[图片]"
                    )

                    # 标记已使用的图片
                    for img in available_images[:comment.content.count('[pic:')]:
                        img['used'] = True

    def _process_comment_images_enhanced(self, comments: List[ZhihuComment], comment_images: List[Dict]):
        """
        增强版评论图片占位符处理（方案三专用）
        按照评论和图片的顺序进行精确匹配
        Args:
            comments: 评论列表（按浏览器显示顺序）
            comment_images: 图片列表（按文件名排序）
        """
        utils.logger.info(f"[ZhihuCrawler._process_comment_images_enhanced] Processing {len(comments)} comments with {len(comment_images)} images")

        image_index = 0
        total_replaced = 0

        for comment in comments:
            # 统计当前评论中的图片占位符数量
            placeholder_count = comment.content.count("[图片]")

            if placeholder_count > 0:
                utils.logger.info(f"[ZhihuCrawler._process_comment_images_enhanced] Comment {comment.comment_id} has {placeholder_count} placeholders: {comment.content[:100]}")

                if image_index < len(comment_images):
                    # 获取当前评论需要的图片
                    needed_images = comment_images[image_index:image_index + placeholder_count]

                    # 逐个替换占位符
                    updated_content = comment.content
                    for img_info in needed_images:
                        filename = img_info['filename']
                        old_content = updated_content
                        updated_content = updated_content.replace("[图片]", f"[pic:{filename}]", 1)
                        utils.logger.info(f"[ZhihuCrawler._process_comment_images_enhanced] Replaced [图片] with [pic:{filename}] in comment {comment.comment_id}")

                    comment.content = updated_content
                    image_index += placeholder_count
                    total_replaced += placeholder_count

                    utils.logger.info(f"[ZhihuCrawler._process_comment_images_enhanced] Updated comment {comment.comment_id}: {comment.content[:100]}")
                else:
                    utils.logger.warning(f"[ZhihuCrawler._process_comment_images_enhanced] Not enough images for comment {comment.comment_id}, need {placeholder_count} but only {len(comment_images) - image_index} remaining")

        utils.logger.info(f"[ZhihuCrawler._process_comment_images_enhanced] Total replaced {total_replaced} placeholders")

    async def process_content_images_with_info(self, zhihu_content: ZhihuContent) -> List[Dict]:
        """
        处理内容中的图片并返回图片信息
        Args:
            zhihu_content: 知乎内容对象

        Returns:
            List[Dict]: 图片信息列表
        """
        if not config.ENABLE_GET_IMAGES:
            return []

        try:
            # 转换为字典格式进行图片处理
            content_dict = {
                'content_id': zhihu_content.content_id,
                'content_text': zhihu_content.content_text,
                'content_url': zhihu_content.content_url,
                'title': zhihu_content.title
            }

            # 使用图片处理器处理图片
            async with ZhihuImageProcessor() as image_processor:
                downloaded_images = await image_processor.process_content_images(content_dict)

                # 保存图片并构建图片信息
                images_info = []
                for image_info in downloaded_images:
                    # 保存图片到本地
                    await zhihu_store.update_zhihu_image(
                        content_id=image_info['content_id'],
                        pic_content=image_info['pic_content'],
                        extension_file_name=image_info['extension_file_name']
                    )

                    # 构建图片信息（用于JSON存储）
                    img_info = {
                        'url': image_info.get('url', ''),
                        'local_path': f"data/zhihu/images/collection_contents/{image_info['content_id']}/{image_info['extension_file_name']}",
                        'filename': image_info['extension_file_name'],
                        'alt': image_info.get('alt', ''),
                        'title': image_info.get('title', ''),
                        'size': len(image_info['pic_content']) if image_info.get('pic_content') else 0,
                        'download_time': utils.get_current_date()
                    }
                    images_info.append(img_info)

                utils.logger.info(f"[ZhihuCrawler.process_content_images_with_info] Successfully processed {len(images_info)} images for content {zhihu_content.note_id}")
                return images_info

        except Exception as e:
            utils.logger.error(f"[ZhihuCrawler.process_content_images_with_info] Error processing images for content {zhihu_content.note_id}: {e}")
            return []

    async def close(self):
        """Close browser context"""
        # 如果使用CDP模式，需要特殊处理
        if self.cdp_manager:
            await self.cdp_manager.cleanup()
            self.cdp_manager = None
        else:
            await self.browser_context.close()
        utils.logger.info("[ZhihuCrawler.close] Browser context closed ...")
