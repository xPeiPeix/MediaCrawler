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
import re
import asyncio
import httpx
from typing import List, Dict, Optional
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from tools import utils
import config


class ZhihuImageProcessor:
    """知乎图片处理器"""
    
    def __init__(self):
        self.session = None
        self.semaphore = asyncio.Semaphore(3)  # 限制并发数
        
    async def __aenter__(self):
        self.session = httpx.AsyncClient(
            timeout=30,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.aclose()
    
    def extract_images_from_html(self, html_content: str, base_url: str = "") -> List[Dict]:
        """
        从HTML内容中提取图片URL
        Args:
            html_content: HTML内容
            base_url: 基础URL，用于处理相对路径

        Returns:
            图片信息列表
        """
        if not html_content:
            return []

        images = []

        try:
            # 使用BeautifulSoup解析HTML
            soup = BeautifulSoup(html_content, 'html.parser')

            # 首先尝试定位正文区域
            content_container = self._find_content_container(soup)
            if not content_container:
                utils.logger.warning("[ZhihuImageProcessor.extract_images_from_html] Could not find content container, using full page")
                content_container = soup

            # 方法1：只从正文区域的figure标签中查找img标签
            # 基于用户提供的信息，只提取figure标签内的图片
            figure_tags = content_container.find_all('figure')
            utils.logger.info(f"[ZhihuImageProcessor.extract_images_from_html] Found {len(figure_tags)} figure tags in content area")

            for figure_idx, figure in enumerate(figure_tags):
                utils.logger.info(f"[ZhihuImageProcessor.extract_images_from_html] Processing figure {figure_idx + 1}")
                img_tags_in_figure = figure.find_all('img')
                utils.logger.info(f"[ZhihuImageProcessor.extract_images_from_html] Found {len(img_tags_in_figure)} img tags in figure {figure_idx + 1}")

                for img_idx, img in enumerate(img_tags_in_figure):
                    # 尝试多种属性获取图片URL
                    src_candidates = [
                        img.get('src'),
                        img.get('data-src'),
                        img.get('data-original'),
                        img.get('data-actualsrc')
                    ]
                    src = None
                    for candidate in src_candidates:
                        if candidate:
                            src = candidate
                            break

                    utils.logger.info(f"[ZhihuImageProcessor.extract_images_from_html] Figure {figure_idx + 1}, img {img_idx + 1}: src={src}")

                    if not src:
                        utils.logger.warning(f"[ZhihuImageProcessor.extract_images_from_html] No valid src found for img {img_idx + 1} in figure {figure_idx + 1}")
                        continue

                    # 跳过头像和无关图片（额外保险）
                    if self._is_avatar_or_irrelevant_image(img):
                        utils.logger.info(f"[ZhihuImageProcessor.extract_images_from_html] Skipping img {img_idx + 1} in figure {figure_idx + 1}: detected as avatar/irrelevant")
                        continue

                # 处理相对路径
                if src.startswith('//'):
                    src = 'https:' + src
                elif src.startswith('/'):
                    src = urljoin(base_url, src)
                elif not src.startswith(('http://', 'https://')):
                    src = urljoin(base_url, src)

                # 过滤掉一些不需要的图片
                if self._should_skip_image(src):
                    # 对于data:协议的URL，只显示前50个字符避免日志过长
                    display_url = src[:50] + "..." if src.startswith('data:') and len(src) > 50 else src
                    utils.logger.info(f"[ZhihuImageProcessor.extract_images_from_html] Skipping img {img_idx + 1} in figure {figure_idx + 1}: {display_url} (filtered by skip rules)")
                    continue

                # 获取图片信息
                alt_text = img.get('alt', '')
                title = img.get('title', '')

                # 推断文件扩展名
                extension = self._get_image_extension(src)

                images.append({
                    'url': src,
                    'alt': alt_text,
                    'title': title,
                    'extension': extension,
                    'filename': f"image_{len(images):03d}.{extension}"
                })
                utils.logger.info(f"[ZhihuImageProcessor.extract_images_from_html] Successfully added img {img_idx + 1} from figure {figure_idx + 1}: {src}")

            # 方法2：从知乎的JavaScript数据中提取图片（针对知乎特殊处理）
            # 注意：暂时禁用JS提取，因为它可能包含页面上所有图片，包括头像
            # zhihu_images = self._extract_zhihu_images_from_js(html_content)
            # images.extend(zhihu_images)
            utils.logger.info("[ZhihuImageProcessor.extract_images_from_html] Skipping JS image extraction to avoid non-content images")

        except Exception as e:
            utils.logger.error(f"[ZhihuImageProcessor.extract_images_from_html] Error parsing HTML: {e}")

        return images

    def _extract_zhihu_images_from_js(self, html_content: str) -> List[Dict]:
        """
        从知乎页面的JavaScript数据中提取图片
        Args:
            html_content: HTML内容

        Returns:
            图片信息列表
        """
        images = []

        try:
            # 使用正则表达式查找JavaScript中的图片URL
            # 知乎图片通常在pic1.zhimg.com, pic2.zhimg.com等域名下
            import re

            # 查找所有知乎图片URL
            zhihu_img_pattern = r'https?://pic[0-9]\.zhimg\.com/[^"\'>\s]+'
            img_urls = re.findall(zhihu_img_pattern, html_content)

            # 去重
            unique_urls = list(set(img_urls))

            for idx, url in enumerate(unique_urls):
                # 过滤掉一些不需要的图片
                if self._should_skip_image(url):
                    continue

                # 推断文件扩展名
                extension = self._get_image_extension(url)

                images.append({
                    'url': url,
                    'alt': f'知乎图片{idx+1}',
                    'title': '',
                    'extension': extension,
                    'filename': f"zhihu_image_{idx:03d}.{extension}"
                })

            utils.logger.info(f"[ZhihuImageProcessor._extract_zhihu_images_from_js] Found {len(images)} zhihu images")

        except Exception as e:
            utils.logger.error(f"[ZhihuImageProcessor._extract_zhihu_images_from_js] Error extracting zhihu images: {e}")

        return images

    def _should_skip_image(self, url: str) -> bool:
        """
        判断是否应该跳过某个图片
        Args:
            url: 图片URL

        Returns:
            是否跳过
        """
        # 跳过data:协议的内联图片（如SVG占位符）
        if url.startswith('data:'):
            return True

        # 跳过非HTTP/HTTPS协议的URL
        if not url.startswith(('http://', 'https://')):
            return True

        skip_patterns = [
            r'avatar',  # 头像
            r'icon',    # 图标
            r'logo',    # Logo
            r'emoji',   # 表情
            r'1x1',     # 1x1像素图片
            r'placeholder',  # 占位图
        ]

        for pattern in skip_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return True

        return False
    
    def _get_image_extension(self, url: str) -> str:
        """
        从URL中获取图片扩展名
        Args:
            url: 图片URL
            
        Returns:
            文件扩展名
        """
        # 从URL路径中提取扩展名
        parsed = urlparse(url)
        path = parsed.path.lower()
        
        if path.endswith('.jpg') or path.endswith('.jpeg'):
            return 'jpg'
        elif path.endswith('.png'):
            return 'png'
        elif path.endswith('.gif'):
            return 'gif'
        elif path.endswith('.webp'):
            return 'webp'
        elif path.endswith('.svg'):
            return 'svg'
        else:
            # 默认使用jpg
            return 'jpg'
    
    async def download_image(self, image_info: Dict) -> Optional[bytes]:
        """
        下载单个图片
        Args:
            image_info: 图片信息
            
        Returns:
            图片内容字节
        """
        if not self.session:
            return None
            
        url = image_info['url']
        
        async with self.semaphore:
            try:
                # 对于data:协议的URL，只显示前50个字符避免日志过长
                display_url = url[:50] + "..." if url.startswith('data:') and len(url) > 50 else url
                utils.logger.info(f"[ZhihuImageProcessor.download_image] Downloading: {display_url}")

                response = await self.session.get(url)
                response.raise_for_status()
                
                # 检查内容类型
                content_type = response.headers.get('content-type', '')
                if not content_type.startswith('image/'):
                    utils.logger.warning(f"[ZhihuImageProcessor.download_image] Not an image: {url}, content-type: {content_type}")
                    return None
                
                return response.content
                
            except Exception as e:
                # 对于data:协议的URL，只显示前50个字符避免日志过长
                display_url = url[:50] + "..." if url.startswith('data:') and len(url) > 50 else url
                utils.logger.error(f"[ZhihuImageProcessor.download_image] Error downloading {display_url}: {e}")
                return None
    
    async def process_content_images(self, content_item: Dict) -> List[Dict]:
        """
        处理内容中的所有图片
        Args:
            content_item: 内容项
            
        Returns:
            下载成功的图片信息列表
        """
        if not config.ENABLE_GET_IMAGES:
            return []
            
        content_text = content_item.get('content_text', '')
        content_url = content_item.get('content_url', '')
        content_id = content_item.get('content_id', '')
        
        if not content_text or not content_id:
            return []
        
        # 提取图片URL
        images = self.extract_images_from_html(content_text, content_url)
        
        if not images:
            utils.logger.info(f"[ZhihuImageProcessor.process_content_images] No images found in content {content_id}")
            return []
        
        utils.logger.info(f"[ZhihuImageProcessor.process_content_images] Found {len(images)} images in content {content_id}")
        
        # 下载图片
        downloaded_images = []
        
        for image_info in images:
            try:
                # 添加延迟避免请求过快
                await asyncio.sleep(0.5)
                
                image_content = await self.download_image(image_info)
                
                if image_content:
                    downloaded_images.append({
                        'content_id': content_id,
                        'pic_content': image_content,
                        'extension_file_name': image_info['filename'],
                        'url': image_info['url'],
                        'alt': image_info['alt'],
                        'title': image_info['title']
                    })
                    
            except Exception as e:
                utils.logger.error(f"[ZhihuImageProcessor.process_content_images] Error processing image: {e}")
                continue
        
        utils.logger.info(f"[ZhihuImageProcessor.process_content_images] Successfully downloaded {len(downloaded_images)} images for content {content_id}")
        
        return downloaded_images

    def _find_content_container(self, soup):
        """
        定位知乎页面的正文内容容器

        Args:
            soup: BeautifulSoup对象

        Returns:
            正文容器元素，如果找不到则返回None
        """
        # 基于用户提供的信息，精确定位知乎正文容器
        content_selectors = [
            # 最精确的正文容器（基于用户提供的HTML结构）
            'span.RichText.ztext.CopyrightRichText-richText',
            '.RichText.ztext',
            '.CopyrightRichText-richText',
            # 备用选择器
            '.RichContent-inner',
            '.RichText',
            '.AnswerItem .RichContent',
            '.QuestionAnswer-content .RichContent',
            # 文章内容
            '.Post-RichTextContainer',
            '.ArticleItem .RichContent',
            # 通用内容容器
            '[data-za-detail-view-element_name="AnswerItem"]',
            '.ContentItem-main'
        ]

        for selector in content_selectors:
            container = soup.select_one(selector)
            if container:
                utils.logger.info(f"[ZhihuImageProcessor._find_content_container] Found content container using selector: {selector}")
                return container

        # 如果都找不到，尝试通过ID定位
        content_by_id = soup.find(id='content')
        if content_by_id:
            # 在content内查找RichText容器
            rich_text = content_by_id.find('span', class_='RichText')
            if rich_text:
                utils.logger.info("[ZhihuImageProcessor._find_content_container] Found content container by ID and RichText class")
                return rich_text

        return None

    def _is_avatar_or_irrelevant_image(self, img_tag):
        """
        判断图片是否为头像或其他无关图片

        Args:
            img_tag: BeautifulSoup的img标签对象

        Returns:
            True表示应该跳过，False表示保留
        """
        # 检查图片的src属性
        src = img_tag.get('src', '') or img_tag.get('data-src', '') or img_tag.get('data-original', '')

        # 头像相关的URL特征
        avatar_patterns = [
            'avatar',
            'profile',
            'user',
            'author',
            '/people/',
            'userinfo',
            'portrait',
            'headimg'
        ]

        # 检查URL是否包含头像特征
        src_lower = src.lower()
        for pattern in avatar_patterns:
            if pattern in src_lower:
                return True

        # 检查图片的class属性
        img_classes = img_tag.get('class', [])
        if isinstance(img_classes, list):
            class_str = ' '.join(img_classes).lower()
        else:
            class_str = str(img_classes).lower()

        avatar_class_patterns = [
            'avatar',
            'profile',
            'author',
            'user',
            'portrait'
        ]

        for pattern in avatar_class_patterns:
            if pattern in class_str:
                return True

        # 检查父元素的class
        parent = img_tag.parent
        if parent:
            parent_classes = parent.get('class', [])
            if isinstance(parent_classes, list):
                parent_class_str = ' '.join(parent_classes).lower()
            else:
                parent_class_str = str(parent_classes).lower()

            for pattern in avatar_class_patterns:
                if pattern in parent_class_str:
                    return True

        # 检查图片尺寸（如果有的话）
        width = img_tag.get('width')
        height = img_tag.get('height')

        if width and height:
            try:
                w = int(width)
                h = int(height)
                # 头像通常是小尺寸的正方形或接近正方形
                if w <= 100 and h <= 100 and abs(w - h) <= 20:
                    return True
            except (ValueError, TypeError):
                pass

        return False
