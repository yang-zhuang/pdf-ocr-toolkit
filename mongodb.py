"""MongoDB 连接与论文解析状态管理。"""

import os
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from pymongo import MongoClient
from pymongo.collection import Collection

# MongoDB 文档中 PDF 解析状态的嵌套字段名
# 示例: { "pdf_parse": { "parsed": true, "parsed_at": "...", ... } }
PARSE_STATUS_KEY = "pdf_parse"


class MongoPaperStore:
    """MongoDB 论文数据存储：读取待解析文件、查询解析状态、更新解析结果。"""

    def __init__(self, uri: str, db_name: str, collection_name: str):
        self.client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        # 触发一次实际连接，尽早暴露连接失败
        self.client.admin.command("ping")
        self.db = self.client[db_name]
        self.collection: Collection = self.db[collection_name]

    def get_unparsed_papers(
        self,
        base_path: str,
        path_field: str = "pdf_file",
    ) -> List[Dict[str, Any]]:
        """
        查询所有未解析的论文，返回包含完整本地路径的任务列表。

        将 path_field（相对路径）与 base_path 拼接为绝对路径，
        过滤掉本地文件不存在的记录。
        """
        from pathlib import Path

        query = {
            "$or": [
                {f"{PARSE_STATUS_KEY}.parsed": {"$ne": True}},
                {PARSE_STATUS_KEY: {"$exists": False}},
            ]
        }
        cursor = self.collection.find(query, {path_field: 1})

        results = []
        for doc in cursor:
            relative = doc.get(path_field)
            if not relative:
                continue
            full_path = Path(base_path) / relative
            if not full_path.exists():
                print(f"  警告: 文件不存在，跳过: {full_path}")
                continue
            results.append({
                "_id": doc["_id"],
                "file_path": str(full_path),
                "base_name": full_path.stem,
                "relative_dir": str(Path(relative).with_suffix("")),
            })
        return results

    def is_parsed(self, paper_id) -> bool:
        """检查论文是否已成功解析。"""
        doc = self.collection.find_one(
            {"_id": paper_id},
            {f"{PARSE_STATUS_KEY}.parsed": 1},
        )
        if doc is None:
            return False
        return doc.get(PARSE_STATUS_KEY, {}).get("parsed") is True

    def mark_parsed(
        self,
        paper_id,
        ocr_model: str,
        parse_result_dir: str,
    ) -> None:
        """标记论文已成功解析。"""
        self.collection.update_one(
            {"_id": paper_id},
            {"$set": {
                f"{PARSE_STATUS_KEY}.parsed": True,
                f"{PARSE_STATUS_KEY}.parsed_at": datetime.now(timezone.utc),
                f"{PARSE_STATUS_KEY}.ocr_model": ocr_model,
                f"{PARSE_STATUS_KEY}.parse_error": None,
                f"{PARSE_STATUS_KEY}.parse_result_dir": parse_result_dir,
            }},
        )

    def mark_error(
        self,
        paper_id,
        error_message: str,
        ocr_model: Optional[str] = None,
    ) -> None:
        """记录论文解析失败。parsed 保持 false，下次运行会重试。"""
        update: Dict[str, Any] = {
            f"{PARSE_STATUS_KEY}.parse_error": error_message,
        }
        if ocr_model:
            update[f"{PARSE_STATUS_KEY}.ocr_model"] = ocr_model
        self.collection.update_one({"_id": paper_id}, {"$set": update})

    def find_paper_by_path(self, file_path: str, path_field: str = "pdf_file") -> Optional[str]:
        """
        通过文件路径反查 MongoDB 中的 paper_id

        Args:
            file_path: 完整本地文件路径
            path_field: MongoDB 中的路径字段名

        Returns:
            paper_id 如果找到，否则返回 None
        """
        from pathlib import Path

        # 尝试匹配相对路径（用于 mongo 模式）
        base_path = os.environ.get("PDF_BASE_PATH", "F:/papers/arxiv")
        try:
            relative_path = str(Path(file_path).relative_to(base_path))
            doc = self.collection.find_one({path_field: relative_path}, {"_id": 1})
            if doc:
                return doc["_id"]
        except ValueError:
            # file_path 不在 base_path 下，继续尝试绝对路径匹配
            pass

        # 尝试直接匹配绝对路径
        doc = self.collection.find_one({path_field: file_path}, {"_id": 1})
        return doc["_id"] if doc else None

    def find_papers_by_paths(self, file_paths: List[str], path_field: str = "pdf_file") -> Dict[str, str]:
        """
        批量查询文件路径对应的 paper_id

        Args:
            file_paths: 完整本地文件路径列表
            path_field: MongoDB 中的路径字段名

        Returns:
            字典 {file_path: paper_id}
        """
        from pathlib import Path

        base_path = os.environ.get("PDF_BASE_PATH", "F:/papers/arxiv")
        path_to_id = {}

        # 构建所有可能的路径变体
        possible_queries = []
        for fp in file_paths:
            # 原始路径
            possible_queries.append({path_field: fp})

            # 相对路径
            try:
                relative_path = str(Path(fp).relative_to(base_path))
                possible_queries.append({path_field: relative_path})
            except ValueError:
                pass

        # 批量查询（使用 $or）
        if possible_queries:
            cursor = self.collection.find(
                {"$or": possible_queries},
                {path_field: 1, "_id": 1}
            )
            for doc in cursor:
                stored_path = doc.get(path_field)
                if stored_path:
                    # 构建完整路径作为键
                    full_path = str(Path(base_path) / stored_path) if not Path(stored_path).is_absolute() else stored_path
                    path_to_id[full_path] = doc["_id"]

        return path_to_id

    def close(self) -> None:
        """关闭 MongoDB 连接。"""
        self.client.close()
