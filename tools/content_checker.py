# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：  
# 1. 不得用于任何商业用途。  
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。  
# 3. 不得进行大规模爬取或对平台造成运营干扰。  
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。   
# 5. 不得用于任何非法或不当的用途。
#   
# 详细许可条款请参阅项目根目录下的LICENSE文件。  
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。  


import json
import os
import asyncio
from typing import Set, Dict, List
from pathlib import Path

import config
from tools import utils


class ContentExistenceChecker:
    """内容存在性检测器，支持JSON文件和数据库两种存储方式"""
    
    def __init__(self, platform: str = "zhihu"):
        self.platform = platform
        self.existing_content_ids: Set[str] = set()
        self._loaded = False
    
    async def load_existing_content_ids(self) -> None:
        """加载已存在的内容ID列表"""
        if self._loaded:
            return
            
        if config.SAVE_DATA_OPTION == "json":
            await self._load_from_json()
        elif config.SAVE_DATA_OPTION == "db":
            await self._load_from_database()
        else:
            utils.logger.warning(f"[ContentExistenceChecker] Unsupported save data option: {config.SAVE_DATA_OPTION}")
        
        self._loaded = True
        utils.logger.info(f"[ContentExistenceChecker] Loaded {len(self.existing_content_ids)} existing content IDs")
    
    async def _load_from_json(self) -> None:
        """从JSON文件加载已存在的内容ID"""
        json_dir = Path(f"data/{self.platform}/json")
        if not json_dir.exists():
            utils.logger.info(f"[ContentExistenceChecker] JSON directory not found: {json_dir}")
            return
        
        # 查找所有相关的JSON文件
        pattern_files = [
            "collection_contents_*.json",
            "contents_*.json"
        ]
        
        for pattern in pattern_files:
            for json_file in json_dir.glob(pattern):
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        
                    if isinstance(data, list):
                        for item in data:
                            content_id = item.get('content_id')
                            if content_id:
                                self.existing_content_ids.add(str(content_id))
                    
                    utils.logger.info(f"[ContentExistenceChecker] Loaded {len(data)} items from {json_file.name}")
                    
                except Exception as e:
                    utils.logger.error(f"[ContentExistenceChecker] Error loading {json_file}: {e}")
    
    async def _load_from_database(self) -> None:
        """从数据库加载已存在的内容ID"""
        try:
            if self.platform == "zhihu":
                from store.zhihu.zhihu_store_sql import query_all_content_ids
                content_ids = await query_all_content_ids()
                self.existing_content_ids.update(str(cid) for cid in content_ids)
            else:
                utils.logger.warning(f"[ContentExistenceChecker] Database loading not implemented for platform: {self.platform}")
        except Exception as e:
            utils.logger.error(f"[ContentExistenceChecker] Error loading from database: {e}")
    
    async def content_exists(self, content_id: str) -> bool:
        """检查内容是否已存在"""
        if not self._loaded:
            await self.load_existing_content_ids()
        
        return str(content_id) in self.existing_content_ids
    
    async def filter_new_content_ids(self, content_ids: List[str]) -> List[str]:
        """过滤出不存在的内容ID列表"""
        if not self._loaded:
            await self.load_existing_content_ids()
        
        new_ids = [cid for cid in content_ids if str(cid) not in self.existing_content_ids]
        
        skipped_count = len(content_ids) - len(new_ids)
        if skipped_count > 0:
            utils.logger.info(f"[ContentExistenceChecker] Skipping {skipped_count} existing content(s), processing {len(new_ids)} new content(s)")
        
        return new_ids
    
    def add_content_id(self, content_id: str) -> None:
        """添加新的内容ID到已存在列表（用于实时更新）"""
        self.existing_content_ids.add(str(content_id))
    
    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        return {
            "total_existing": len(self.existing_content_ids),
            "loaded": self._loaded
        }


# 全局实例，避免重复加载
_checker_instances = {}

def get_content_checker(platform: str = "zhihu") -> ContentExistenceChecker:
    """获取内容检测器实例（单例模式）"""
    if platform not in _checker_instances:
        _checker_instances[platform] = ContentExistenceChecker(platform)
    return _checker_instances[platform]
