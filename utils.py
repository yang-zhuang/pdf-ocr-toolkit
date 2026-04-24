"""工具函数 - 路径处理、文件收集、结果保存"""

import os
import sys
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from PIL import Image

MAX_PATH_LENGTH = 240
SUPPORTED_FORMATS = [".jpg", ".jpeg", ".png", ".pdf"]


def get_safe_path(path: Path) -> Path:
    """Windows 长路径处理"""
    if sys.platform != "win32":
        return path
    abs_path = path.resolve()
    path_str = str(abs_path)
    if path_str.startswith("\\\\?\\"):
        return path
    if len(path_str) > MAX_PATH_LENGTH:
        converted = path_str.replace('/', '\\')
        return Path("\\\\?\\" + converted)
    return abs_path


def collect_input_files(input_path: str) -> List[str]:
    """收集输入路径下所有支持格式的文件"""
    path = Path(input_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"输入路径不存在: {input_path}")

    if path.is_file():
        if path.suffix.lower() not in SUPPORTED_FORMATS:
            raise ValueError(f"不支持的格式: {path.suffix}")
        return [str(path)]

    files = [
        str(get_safe_path(f)) for f in path.rglob("*")
        if f.is_file() and f.suffix.lower() in SUPPORTED_FORMATS
    ]
    if not files:
        raise ValueError(f"未找到支持的文件: {input_path}")
    return files


def save_images(processing_result: Dict[str, Any], output_dir: str) -> None:
    """保存提取的图片"""
    output_dir = Path(output_dir)
    for page_elements in processing_result.get('per_page_elements', []):
        for element in page_elements:
            if element.get('label') != 'fig':
                continue
            try:
                pil_crop = element.get('crop')
                figure_path = element.get('figure_path')
                if not pil_crop or not figure_path:
                    continue

                safe_rel = figure_path.lstrip("/\\").lstrip(":/\\").replace("../", "")
                full_path = (output_dir / safe_rel).resolve()
                if not str(full_path).startswith(str(output_dir)):
                    continue  # 跳过路径遍历攻击

                full_path.parent.mkdir(parents=True, exist_ok=True)
                pil_crop.save(get_safe_path(full_path), format="PNG", optimize=True)
            except Exception as e:
                print(f"  图片保存失败: {e}")


def save_json(processing_result: Dict[str, Any], source_file: str, output_path: str) -> None:
    """保存JSON结果"""
    cleaned = []
    for page_elements in processing_result['per_page_elements']:
        for elem in page_elements:
            elem.pop('crop', None)
        cleaned.append(page_elements)

    output_data = {
        "source_file": source_file,
        "total_pages": len(cleaned),
        "pages": cleaned,
    }
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(get_safe_path(output_path), "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)


def save_markdown(processing_result: Dict[str, Any], output_path: str) -> None:
    """保存Markdown结果"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = processing_result['full_markdown'].strip()
    with open(get_safe_path(output_path), "w", encoding="utf-8") as f:
        f.write(content)


def save_all(
    processing_result: Dict[str, Any],
    source_file: str,
    output_dir: str,
    base_filename: Optional[str] = None,
    save_images: bool = True,
    save_json: bool = True,
    save_markdown: bool = True,
) -> None:
    """保存所有结果"""
    if not base_filename:
        base_filename = Path(source_file).stem

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if save_images:
        save_images(processing_result, str(output_dir))
    if save_json:
        save_json(processing_result, source_file, str(output_dir / f"{base_filename}.json"))
    if save_markdown:
        save_markdown(processing_result, str(output_dir / f"{base_filename}.md"))


def file_exists(output_dir: str, base_filename: str) -> bool:
    """检查文件是否已存在"""
    output_dir = Path(output_dir)
    return (output_dir / f"{base_filename}.json").exists() or \
           (output_dir / f"{base_filename}.md").exists()
