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
import csv
import json
import os
import pathlib
from typing import Dict

import aiofiles

import config
from base.base_crawler import AbstractStore
from tools import utils, words
from var import crawler_type_var


def calculate_number_of_files(file_store_path: str) -> int:
    """计算数据保存文件的前部分排序数字，支持每次运行代码不写到同一个文件中
    Args:
        file_store_path;
    Returns:
        file nums
    """
    if not os.path.exists(file_store_path):
        return 1
    try:
        return max([int(file_name.split("_")[0]) for file_name in os.listdir(file_store_path)]) + 1
    except ValueError:
        return 1


class ZhihuCsvStoreImplement(AbstractStore):
    csv_store_path: str = "data/zhihu"
    file_count: int = calculate_number_of_files(csv_store_path)

    def make_save_file_name(self, store_type: str) -> str:
        """
        make save file name by store type
        Args:
            store_type: contents or comments

        Returns: eg: data/zhihu/search_comments_20240114.csv ...

        """
        return f"{self.csv_store_path}/{self.file_count}_{crawler_type_var.get()}_{store_type}_{utils.get_current_date()}.csv"

    async def save_data_to_csv(self, save_item: Dict, store_type: str):
        """
        Below is a simple way to save it in CSV format.
        Args:
            save_item:  save content dict info
            store_type: Save type contains content and comments（contents | comments）

        Returns: no returns

        """
        pathlib.Path(self.csv_store_path).mkdir(parents=True, exist_ok=True)
        save_file_name = self.make_save_file_name(store_type=store_type)
        async with aiofiles.open(save_file_name, mode='a+', encoding="utf-8-sig", newline="") as f:
            f.fileno()
            writer = csv.writer(f)
            if await f.tell() == 0:
                await writer.writerow(save_item.keys())
            await writer.writerow(save_item.values())

    async def store_content(self, content_item: Dict):
        """
        Zhihu content CSV storage implementation
        Args:
            content_item: note item dict

        Returns:

        """
        await self.save_data_to_csv(save_item=content_item, store_type="contents")

    async def store_comment(self, comment_item: Dict):
        """
        Zhihu comment CSV storage implementation
        Args:
            comment_item: comment item dict

        Returns:

        """
        await self.save_data_to_csv(save_item=comment_item, store_type="comments")

    async def store_creator(self, creator: Dict):
        """
        Zhihu content CSV storage implementation
        Args:
            creator: creator dict

        Returns:

        """
        await self.save_data_to_csv(save_item=creator, store_type="creator")


class ZhihuDbStoreImplement(AbstractStore):
    async def store_content(self, content_item: Dict):
        """
        Zhihu content DB storage implementation
        Args:
            content_item: content item dict

        Returns:

        """
        from .zhihu_store_sql import (add_new_content,
                                      query_content_by_content_id,
                                      update_content_by_content_id)
        note_id = content_item.get("note_id")
        note_detail: Dict = await query_content_by_content_id(content_id=note_id)
        if not note_detail:
            content_item["add_ts"] = utils.get_current_timestamp()
            await add_new_content(content_item)
        else:
            await update_content_by_content_id(note_id, content_item=content_item)

    async def store_comment(self, comment_item: Dict):
        """
        Zhihu content DB storage implementation
        Args:
            comment_item: comment item dict

        Returns:

        """
        from .zhihu_store_sql import (add_new_comment,
                                      query_comment_by_comment_id,
                                      update_comment_by_comment_id)
        comment_id = comment_item.get("comment_id")
        comment_detail: Dict = await query_comment_by_comment_id(comment_id=comment_id)
        if not comment_detail:
            comment_item["add_ts"] = utils.get_current_timestamp()
            await add_new_comment(comment_item)
        else:
            await update_comment_by_comment_id(comment_id, comment_item=comment_item)

    async def store_creator(self, creator: Dict):
        """
        Zhihu content DB storage implementation
        Args:
            creator: creator dict

        Returns:

        """
        from .zhihu_store_sql import (add_new_creator,
                                      query_creator_by_user_id,
                                      update_creator_by_user_id)
        user_id = creator.get("user_id")
        user_detail: Dict = await query_creator_by_user_id(user_id)
        if not user_detail:
            creator["add_ts"] = utils.get_current_timestamp()
            await add_new_creator(creator)
        else:
            await update_creator_by_user_id(user_id, creator)


class ZhihuJsonStoreImplement(AbstractStore):
    json_store_path: str = "data/zhihu/json"
    words_store_path: str = "data/zhihu/words"
    lock = asyncio.Lock()
    file_count: int = calculate_number_of_files(json_store_path)
    WordCloud = words.AsyncWordCloudGenerator()




    def make_save_file_name(self, store_type: str) -> (str, str):
        """
        make save file name by store type
        Args:
            store_type: Save type contains content and comments（contents | comments）

        Returns:

        """

        return (
            f"{self.json_store_path}/{crawler_type_var.get()}_{store_type}_{utils.get_current_date()}.json",
            f"{self.words_store_path}/{crawler_type_var.get()}_{store_type}_{utils.get_current_date()}"
        )

    async def save_data_to_json(self, save_item: Dict, store_type: str):
        """
        Below is a simple way to save it in json format.
        Args:
            save_item: save content dict info
            store_type: Save type contains content and comments（contents | comments）

        Returns:

        """
        pathlib.Path(self.json_store_path).mkdir(parents=True, exist_ok=True)
        pathlib.Path(self.words_store_path).mkdir(parents=True, exist_ok=True)
        save_file_name, words_file_name_prefix = self.make_save_file_name(store_type=store_type)
        save_data = []

        async with self.lock:
            if os.path.exists(save_file_name):
                async with aiofiles.open(save_file_name, 'r', encoding='utf-8') as file:
                    save_data = json.loads(await file.read())

            save_data.append(save_item)
            async with aiofiles.open(save_file_name, 'w', encoding='utf-8') as file:
                await file.write(json.dumps(save_data, ensure_ascii=False, indent=4))

            if config.ENABLE_GET_COMMENTS and config.ENABLE_GET_WORDCLOUD:
                try:
                    await self.WordCloud.generate_word_frequency_and_cloud(save_data, words_file_name_prefix)
                except:
                    pass

    async def store_content(self, content_item: Dict):
        """
        content JSON storage implementation
        Args:
            content_item:

        Returns:

        """
        await self.save_data_to_json(content_item, "contents")

    async def store_comment(self, comment_item: Dict):
        """
        comment JSON storage implementation
        Args:
            comment_item:

        Returns:

        """
        await self.save_data_to_json(comment_item, "comments")

    async def store_creator(self, creator: Dict):
        """
        Zhihu content JSON storage implementation
        Args:
            creator: creator dict

        Returns:

        """
        await self.save_data_to_json(creator, "creator")


class ZhihuCollectionJsonStoreImplement:
    """
    知乎收藏夹专用JSON存储实现
    特点：内容和评论整合存储，每个文件最多20条数据
    """
    def __init__(self):
        self.json_store_path: str = "data/zhihu/json"
        self.lock = asyncio.Lock()
        self.max_items_per_file: int = 20

        # 内存中的数据缓存
        self._content_cache: Dict[str, Dict] = {}
        self._current_file_index: int = 1
        self._current_file_count: int = 0

    def make_save_file_name(self, file_index: int) -> str:
        """
        生成分片文件名
        Args:
            file_index: 文件索引
        Returns:
            文件路径
        """
        return f"{self.json_store_path}/{crawler_type_var.get()}_contents_{utils.get_current_date()}_{file_index:03d}.json"

    def get_next_available_file_index(self) -> int:
        """
        获取下一个可用的文件索引，避免覆盖现有文件
        Returns:
            下一个可用的文件索引
        """
        import glob
        import os

        # 确保目录存在
        pathlib.Path(self.json_store_path).mkdir(parents=True, exist_ok=True)

        # 查找当前日期的所有文件
        pattern = f"{self.json_store_path}/{crawler_type_var.get()}_contents_{utils.get_current_date()}_*.json"
        existing_files = glob.glob(pattern)

        if not existing_files:
            return 1

        # 提取现有文件的索引号
        max_index = 0
        for file_path in existing_files:
            filename = os.path.basename(file_path)
            # 文件名格式: collection_contents_2025-07-11_001.json
            try:
                # 提取最后一个下划线后、.json前的数字
                index_str = filename.split('_')[-1].split('.')[0]
                index = int(index_str)
                max_index = max(max_index, index)
            except (ValueError, IndexError):
                continue

        return max_index + 1

    async def store_content(self, content_item: Dict):
        """
        存储内容数据到缓存
        Args:
            content_item: 内容数据
        """
        async with self.lock:
            content_id = content_item.get("content_id")
            if content_id:
                # 初始化评论列表
                content_item["comments"] = []
                self._content_cache[content_id] = content_item
                utils.logger.info(f"[ZhihuCollectionJsonStore] Cached content: {content_id}")

    async def store_comment(self, comment_item: Dict):
        """
        将评论添加到对应内容的评论列表中
        Args:
            comment_item: 评论数据
        """
        async with self.lock:
            content_id = comment_item.get("content_id")
            if content_id and content_id in self._content_cache:
                # 移除不需要的字段
                comment_data = {k: v for k, v in comment_item.items()
                              if k not in ["content_id", "content_type"]}
                self._content_cache[content_id]["comments"].append(comment_data)
                utils.logger.info(f"[ZhihuCollectionJsonStore] Added comment to content: {content_id}")

    async def flush_to_files(self):
        """
        将缓存的数据写入文件
        """
        async with self.lock:
            if not self._content_cache:
                return

            contents = list(self._content_cache.values())
            total_contents = len(contents)

            utils.logger.info(f"[ZhihuCollectionJsonStore] Flushing {total_contents} contents to files")

            # 获取起始文件索引，避免覆盖现有文件
            start_file_index = self.get_next_available_file_index()

            # 按每个文件最多20条数据进行分片
            for i in range(0, total_contents, self.max_items_per_file):
                chunk = contents[i:i + self.max_items_per_file]
                file_index = start_file_index + (i // self.max_items_per_file)
                file_path = self.make_save_file_name(file_index)

                # 确保目录存在
                pathlib.Path(self.json_store_path).mkdir(parents=True, exist_ok=True)

                try:
                    async with aiofiles.open(file_path, 'w', encoding='utf-8') as file:
                        await file.write(json.dumps(chunk, ensure_ascii=False, indent=4))

                    utils.logger.info(f"[ZhihuCollectionJsonStore] Saved {len(chunk)} contents to {file_path}")
                except Exception as e:
                    utils.logger.error(f"[ZhihuCollectionJsonStore] Error saving to {file_path}: {e}")

            # 清空缓存
            self._content_cache.clear()
            utils.logger.info(f"[ZhihuCollectionJsonStore] Flush completed, cache cleared")

    async def store_creator(self, creator: Dict):
        """
        存储创作者信息（收藏夹模式下不需要）
        """
        pass
