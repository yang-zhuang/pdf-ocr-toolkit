"""PaddleOCR后端实现"""

from typing import Dict, Any, List


def process_with_paddle(
    file_path: str,
    vl_rec_backend: str = "vllm-server",
    vl_rec_server_url: str = "http://localhost:8118/v1",
    vl_rec_api_model_name: str = "PaddleOCR-VL-1.5-0.9B",
) -> Dict[str, Any]:
    """使用本地 PaddleOCR 处理文件"""
    from paddleocr import PaddleOCRVL

    pipeline = PaddleOCRVL(
        vl_rec_backend=vl_rec_backend,
        vl_rec_server_url=vl_rec_server_url,
        vl_rec_api_model_name=vl_rec_api_model_name,
    )

    ocr_results = pipeline.predict(file_path)
    page_markdown_infos: List[Dict] = []
    per_page_elements: List[List[Dict]] = []

    for result in ocr_results:
        md_info = result.markdown
        page_markdown_infos.append(md_info)

        page_elements: List[Dict] = []
        for image_path, pil_image in md_info.get("markdown_images", {}).items():
            page_elements.append({
                'label': 'fig',
                'crop': pil_image,
                'figure_path': image_path,
            })
        page_elements.append({
            'page_index': md_info.get("page_index"),
            'page_content': md_info.get("markdown_texts", ""),
        })
        per_page_elements.append(page_elements)

    full_markdown = pipeline.concatenate_markdown_pages(page_markdown_infos)
    return {
        "per_page_elements": per_page_elements,
        "full_markdown": full_markdown,
    }
