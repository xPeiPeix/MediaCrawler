#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
知乎收藏评论获取脚本
为收藏内容获取评论信息
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from typing import List, Dict

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from media_platform.zhihu.core import ZhihuCrawler
from media_platform.zhihu.client import ZhiHuClient
from media_platform.zhihu.login import ZhiHuLogin
from model.m_zhihu import ZhihuContent
from tools import utils
import config


class ZhihuCollectionCommentsProcessor:
    """知乎收藏评论处理器"""
    
    def __init__(self):
        self.zhihu_client = None
        self.processed_count = 0
        self.total_count = 0
        
    async def __aenter__(self):
        """异步上下文管理器入口"""
        # 创建知乎客户端
        self.zhihu_client = ZhiHuClient()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        pass
    
    async def load_collection_data(self, json_file: str) -> List[Dict]:
        """
        加载收藏数据
        Args:
            json_file: JSON文件路径
            
        Returns:
            收藏数据列表
        """
        if not os.path.exists(json_file):
            utils.logger.error(f"[ZhihuCollectionCommentsProcessor] JSON file not found: {json_file}")
            return []
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            utils.logger.info(f"[ZhihuCollectionCommentsProcessor] Loaded {len(data)} items from {json_file}")
            return data
            
        except Exception as e:
            utils.logger.error(f"[ZhihuCollectionCommentsProcessor] Error loading JSON file: {e}")
            return []
    
    def filter_items_need_comments(self, data: List[Dict]) -> List[Dict]:
        """
        筛选需要获取评论的项目
        Args:
            data: 收藏数据列表
            
        Returns:
            需要获取评论的项目列表
        """
        filtered_items = []
        
        for item in data:
            # 检查是否已有评论数据
            has_comments_data = 'comments' in item and item['comments']
            # 检查评论数量
            comment_count = item.get('comment_count', 0)
            
            # 如果有评论但没有评论数据，则需要获取
            if comment_count > 0 and not has_comments_data:
                filtered_items.append(item)
        
        utils.logger.info(f"[ZhihuCollectionCommentsProcessor] Found {len(filtered_items)} items need comments")
        return filtered_items
    
    async def get_content_comments(self, item: Dict) -> List[Dict]:
        """
        获取内容的评论
        Args:
            item: 收藏项数据
            
        Returns:
            评论列表
        """
        content_id = item.get('content_id', '')
        content_type = item.get('content_type', '')
        title = item.get('title', '无标题')
        
        utils.logger.info(f"[ZhihuCollectionCommentsProcessor] Getting comments for: {title[:50]}...")
        
        try:
            # 创建ZhihuContent对象
            zhihu_content = ZhihuContent()
            zhihu_content.content_id = content_id
            zhihu_content.content_type = content_type
            zhihu_content.title = title
            
            # 获取评论
            comments = await self.zhihu_client.get_note_all_comments(
                content=zhihu_content,
                crawl_interval=1.0  # 1秒间隔
            )
            
            # 转换为字典格式
            comments_data = []
            for comment in comments:
                comment_dict = comment.model_dump()
                comments_data.append(comment_dict)
            
            utils.logger.info(f"[ZhihuCollectionCommentsProcessor] Got {len(comments_data)} comments for {content_id}")
            return comments_data
            
        except Exception as e:
            utils.logger.error(f"[ZhihuCollectionCommentsProcessor] Error getting comments for {content_id}: {e}")
            return []
    
    async def process_single_item(self, item: Dict) -> Dict:
        """
        处理单个收藏项的评论
        Args:
            item: 收藏项数据
            
        Returns:
            更新后的收藏项数据
        """
        try:
            # 获取评论
            comments = await self.get_content_comments(item)
            
            # 更新项目数据
            item['comments'] = comments
            item['comments_fetched'] = True
            item['comments_fetch_time'] = utils.get_current_date()
            
            # 添加延迟避免请求过快
            await asyncio.sleep(2)
            
        except Exception as e:
            utils.logger.error(f"[ZhihuCollectionCommentsProcessor] Error processing item: {e}")
        
        return item
    
    async def save_updated_data(self, data: List[Dict], json_file: str):
        """
        保存更新后的数据
        Args:
            data: 更新后的数据
            json_file: JSON文件路径
        """
        try:
            # 备份原文件
            backup_file = json_file.replace('.json', f'_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
            if os.path.exists(json_file):
                os.rename(json_file, backup_file)
                utils.logger.info(f"[ZhihuCollectionCommentsProcessor] Backup created: {backup_file}")
            
            # 保存新数据
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            utils.logger.info(f"[ZhihuCollectionCommentsProcessor] Updated data saved to: {json_file}")
            
        except Exception as e:
            utils.logger.error(f"[ZhihuCollectionCommentsProcessor] Error saving data: {e}")
    
    async def process_all_items(self, json_file: str):
        """
        处理所有需要评论的项目
        Args:
            json_file: JSON文件路径
        """
        # 加载数据
        data = await self.load_collection_data(json_file)
        if not data:
            return
        
        # 筛选需要处理的项目
        items_to_process = self.filter_items_need_comments(data)
        if not items_to_process:
            utils.logger.info("[ZhihuCollectionCommentsProcessor] No items need comments")
            return
        
        self.total_count = len(items_to_process)
        utils.logger.info(f"[ZhihuCollectionCommentsProcessor] Starting to process {self.total_count} items")
        
        # 处理每个项目
        for i, item in enumerate(items_to_process):
            utils.logger.info(f"[ZhihuCollectionCommentsProcessor] Processing {i+1}/{self.total_count}")
            
            # 在原数据中找到对应项目并更新
            content_id = item.get('content_id', '')
            for j, original_item in enumerate(data):
                if original_item.get('content_id') == content_id:
                    data[j] = await self.process_single_item(item)
                    break
            
            self.processed_count += 1
        
        # 保存更新后的数据
        await self.save_updated_data(data, json_file)
        
        utils.logger.info(f"[ZhihuCollectionCommentsProcessor] Completed! Processed {self.processed_count}/{self.total_count} items")


async def main():
    """主函数"""
    # 查找最新的收藏JSON文件
    json_dir = 'data/zhihu/json'
    if not os.path.exists(json_dir):
        print(f"❌ JSON目录不存在: {json_dir}")
        return
    
    # 查找collection_contents文件
    json_files = [f for f in os.listdir(json_dir) if f.startswith('collection_contents_') and f.endswith('.json')]
    if not json_files:
        print(f"❌ 没有找到收藏JSON文件")
        return
    
    # 使用最新的文件
    latest_file = sorted(json_files)[-1]
    json_file = os.path.join(json_dir, latest_file)
    
    print(f"🔍 找到收藏文件: {json_file}")
    
    # 开始处理
    async with ZhihuCollectionCommentsProcessor() as processor:
        await processor.process_all_items(json_file)


if __name__ == "__main__":
    asyncio.run(main())
