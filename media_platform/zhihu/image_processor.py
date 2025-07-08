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

            # 方法1：查找所有img标签
            img_tags = soup.find_all('img')

            for idx, img in enumerate(img_tags):
                src = img.get('src') or img.get('data-src') or img.get('data-original')
                if not src:
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
                    'filename': f"image_{idx:03d}.{extension}"
                })

            # 方法2：从知乎的JavaScript数据中提取图片（针对知乎特殊处理）
            zhihu_images = self._extract_zhihu_images_from_js(html_content)
            images.extend(zhihu_images)

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
                utils.logger.info(f"[ZhihuImageProcessor.download_image] Downloading: {url}")
                
                response = await self.session.get(url)
                response.raise_for_status()
                
                # 检查内容类型
                content_type = response.headers.get('content-type', '')
                if not content_type.startswith('image/'):
                    utils.logger.warning(f"[ZhihuImageProcessor.download_image] Not an image: {url}, content-type: {content_type}")
                    return None
                
                return response.content
                
            except Exception as e:
                utils.logger.error(f"[ZhihuImageProcessor.download_image] Error downloading {url}: {e}")
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
