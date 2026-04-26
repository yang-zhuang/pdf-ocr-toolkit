"""API后端实现"""

import os
from typing import Dict, Any, Optional
import base64
import requests


def process_with_api(
    file_path: str,
    api_url: str,
    api_token: str,
    timeout: Optional[int] = None,
) -> Dict[str, Any]:
    """使用远程 API 处理文件"""
    if timeout is None:
        timeout_str = os.environ.get("OCR_API_TIMEOUT")
        if timeout_str:
            timeout = int(timeout_str)

    with open(file_path, 'rb') as file:
        file_bytes = file.read()
        file_data = base64.b64encode(file_bytes).decode("ascii")

    headers = {
        "Authorization": f"token {api_token}",
        "Content-Type": "application/json"
    }
    required_payload = {
        'file': file_data,
        "fileType": 0,  # For PDF documents, set `fileType` to 0; for images, set `fileType` to 1
    }

    optional_payload = {
        "useDocOrientationClassify": False,
        "useDocUnwarping": False,
        "useChartRecognition": False,
    }

    payload = {**required_payload, **optional_payload}

    kwargs = {}
    if timeout is not None:
        kwargs['timeout'] = timeout
    response = requests.post(api_url, json=payload, headers=headers, **kwargs)
    response.raise_for_status()
    api_result = response.json()

    # 获取实际结果
    result = api_result["result"]

    from PIL import Image
    import io

    per_page_elements = []
    all_markdown_pages = []

    for page_idx, res in enumerate(result["layoutParsingResults"]):
        page_elements = []

        # 处理 markdown 中的图片（保持原始相对路径）
        # markdown.images 包含: 相对路径 -> 图片URL
        for img_rel_path, img_url in res["markdown"]["images"].items():
            try:
                img_response = requests.get(img_url, timeout=30)
                img_response.raise_for_status()
                pil_image = Image.open(io.BytesIO(img_response.content))
                page_elements.append({
                    'label': 'fig',
                    'crop': pil_image,
                    'figure_path': img_rel_path,
                })
            except Exception as e:
                print(f"  下载图片失败 {img_rel_path}: {e}")

        # 添加页面内容
        md_text = res["markdown"]["text"]
        page_elements.append({
            'page_index': page_idx,
            'page_content': md_text,
        })

        per_page_elements.append(page_elements)
        all_markdown_pages.append(md_text)

    # 拼接所有页面的 markdown（用分隔符分隔）
    full_markdown = "\n\n---\n\n".join(all_markdown_pages)

    return {
        "per_page_elements": per_page_elements,
        "full_markdown": full_markdown,
    }
