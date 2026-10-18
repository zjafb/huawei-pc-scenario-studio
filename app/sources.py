"""把 ima 真实目录映射成 {文件名: media_id}，供 LiveSourceReader 使用。

所有 ID 都来自接口实际返回，不自行拼接。目录读取只用 get_knowledge_list，不下载原文。
"""
from __future__ import annotations

from connectors import IMAClient

KB_NAME = "任德耀新建华为PC知识库"
D14_PATH = ["P1-产品参数库", "02-MateBook-Windows", "MateBook D 14"]


def build_media_map(ima: IMAClient) -> dict[str, str]:
    base = ima.find_base(KB_NAME)
    kb_id = base["kb_id"]
    entries = ima.list_path(kb_id, [base["kb_name"], *D14_PATH])
    by_title = {r["title"]: r for r in entries}

    ids: dict[str, str] = {}
    for local, title in (("A14.md", "产品事实.md"), ("B14.md", "卖点与限制.md"), ("I14.csv", "图片索引.csv")):
        if title in by_title:
            ids[local] = by_title[title]["media_id"]
    folder = by_title.get("images")
    if folder:
        for r in ima.list_all(kb_id, folder_id=folder["media_id"]):
            if r.get("media_type") == 9:
                ids[r["title"]] = r["media_id"]
    return ids
