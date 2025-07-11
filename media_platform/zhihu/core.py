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

            # 获取收藏夹内容
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

        # 创建收藏夹专用存储实例
        from store.zhihu import ZhihuStoreFactory
        collection_store = ZhihuStoreFactory.create_collection_store()

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
                    content_title = content.get("title", "无标题")
                    content_url = content.get("url", "")

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

                        # 检测是否包含图片
                        zhihu_content.has_images = self._detect_images_in_content(zhihu_content)

                        # 处理图片并获取图片信息（一步到位）
                        images_info = []
                        if config.ENABLE_GET_IMAGES and zhihu_content.has_images:
                            images_info = await self._process_images_with_browser(zhihu_content)
                            zhihu_content.images_processed = True

                            # 将content_text中的[图片]占位符替换为真实的图片文件名
                            if images_info and zhihu_content.content_text:
                                zhihu_content.content_text = replace_image_placeholders_with_filenames(
                                    zhihu_content.content_text, images_info
                                )
                                utils.logger.info(f"[ZhihuCrawler.get_collection_contents] Replaced {len(images_info)} image placeholders in content {content_id}")

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

        # 将缓存的数据写入文件
        if hasattr(collection_store, 'flush_to_files'):
            await collection_store.flush_to_files()

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
                            await collection_store.store_comment(comment_data)

                    utils.logger.info(f"[ZhihuCrawler._batch_get_collection_comments] Got {len(content_item.comments)} comments for content: {content_item.content_id}")

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

            return ZhihuContent(
                content_id=str(content.get("id", "")),
                content_type="answer",
                content_url=content.get("url", ""),
                title=question.get("title", ""),
                desc=content.get("excerpt", ""),
                note_id=str(content.get("id", "")),
                created_time=content.get("created_time", 0),
                updated_time=content.get("updated_time", 0),
                liked_count=content.get("voteup_count", 0),
                comments_count=content.get("comment_count", 0),
                shared_count=0,
                topics=question.get("topics", []),
                content_url_token=content.get("url", "").split("/")[-1] if content.get("url") else "",
                author=ZhihuCreator(
                    user_id=str(author.get("id", "")),
                    user_nickname=author.get("name", ""),
                    url_token=author.get("url_token", ""),
                    user_avatar=author.get("avatar_url", ""),
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

            return ZhihuContent(
                content_id=str(content.get("id", "")),
                content_type="article",
                content_url=content.get("url", ""),
                title=content.get("title", ""),
                desc=content.get("excerpt", ""),
                note_id=str(content.get("id", "")),
                created_time=content.get("created", 0),
                updated_time=content.get("updated", 0),
                liked_count=content.get("voteup_count", 0),
                comments_count=content.get("comment_count", 0),
                shared_count=0,
                topics=[],
                content_url_token=content.get("url", "").split("/")[-1] if content.get("url") else "",
                author=ZhihuCreator(
                    user_id=str(author.get("id", "")),
                    user_nickname=author.get("name", ""),
                    url_token=author.get("url_token", ""),
                    user_avatar=author.get("avatar_url", ""),
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

    def _detect_images_in_content(self, zhihu_content: ZhihuContent) -> bool:
        """
        检测内容中是否包含图片
        Args:
            zhihu_content: 知乎内容对象

        Returns:
            bool: 是否包含图片
        """
        # 检查描述和内容中是否有图片占位符
        desc = zhihu_content.desc or ""
        content = zhihu_content.content_text or ""

        # 检测图片占位符
        has_image_placeholder = "[图片]" in desc or "[图片]" in content

        # 主要通过占位符检测图片，HTML检测在浏览器阶段进行

        result = has_image_placeholder

        if result:
            utils.logger.info(f"[ZhihuCrawler._detect_images_in_content] Detected images in content {zhihu_content.content_id}")

        return result

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
