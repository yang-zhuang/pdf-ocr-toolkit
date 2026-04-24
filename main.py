"""命令行入口 + 作为库调用的API"""

import argparse
import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Union
from tqdm import tqdm
from ocr import get_backend, list_backends
from utils import collect_input_files, save_all, file_exists
from dotenv import load_dotenv

load_dotenv()

# ========== 作为库调用的API ==========

def process_pdf(file_path: str, backend: str = "paddle", **backend_config) -> Dict[str, Any]:
    """
    处理单个PDF文件（可作为库调用）

    Args:
        file_path: PDF文件路径
        backend: OCR后端（paddle, api等）
        **backend_config: 后端配置参数

    Returns:
        处理结果字典

    Example:
        >>> from pdf_ocr_toolkit import process_pdf
        >>> result = process_pdf("paper.pdf", backend="paddle")
        >>> print(result['full_markdown'])
    """
    ocr_func = get_backend(backend)
    return ocr_func(file_path, **backend_config)


def process_batch(
    file_paths: Union[List[str], str],
    backend: str = "paddle",
    output_dir: str = "./output",
    **backend_config
) -> List[Dict[str, Any]]:
    """
    批量处理PDF文件（可作为库调用）

    Args:
        file_paths: 文件列表或目录路径
        backend: OCR后端
        output_dir: 输出目录
        **backend_config: 后端配置

    Returns:
        处理结果列表

    Example:
        >>> results = process_batch("./papers", backend="paddle")
        >>> success_count = sum(1 for r in results if r['success'])
    """
    if isinstance(file_paths, str):
        file_paths = collect_input_files(file_paths)

    results = []
    for file_path in file_paths:
        base_name = Path(file_path).stem
        try:
            result = process_pdf(file_path, backend, **backend_config)

            save_all(
                result, file_path, output_dir, base_name,
                save_images=True, save_json=True, save_markdown=True
            )

            results.append({
                "file_path": file_path,
                "success": True,
                "error": None,
            })
        except Exception as e:
            results.append({
                "file_path": file_path,
                "success": False,
                "error": str(e),
            })

    return results


# ========== CLI入口 ==========


def _check_paddleocr_available():
    """检查 paddleocr 是否已安装"""
    try:
        import importlib
        importlib.import_module("paddleocr")
        return True
    except ImportError:
        return False


def create_ocr_processor(backend: str, args):
    """创建OCR处理函数"""
    # PaddleOCR后端
    if backend == "paddle":
        if not _check_paddleocr_available():
            # 尝试切换到API
            if os.environ.get("OCR_API_URL"):
                print("[提示] PaddleOCR未安装，切换到API模式")
                backend = "api"
            else:
                print("[错误] PaddleOCR未安装，请安装: pip install paddleocr")
                sys.exit(1)

    # API后端
    if backend == "api":
        api_url = os.environ.get("OCR_API_URL")
        api_token = os.environ.get("OCR_API_TOKEN")
        if not api_url or not api_token:
            print("[错误] API模式需要环境变量: OCR_API_URL 和 OCR_API_TOKEN")
            sys.exit(1)
        return lambda f: get_backend("api")(f, api_url=api_url, api_token=api_token)

    # 默认后端
    return lambda f: get_backend(backend)(f)


def create_argument_parser():
    parser = argparse.ArgumentParser(
        description="PDF 文档解析器",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # 从环境变量读取默认值
    default_backend = os.environ.get("OCR_BACKEND", "api")
    default_input = os.environ.get("OCR_INPUT", "F:/papers/arxiv")
    default_output = os.environ.get("OCR_OUTPUT", "./output")

    parser.add_argument("--source", type=str, default="local",
                        choices=["local", "mongo", "mixed"],
                        help="输入来源: local(仅本地), mongo(MongoDB驱动), mixed(本地扫描+智能更新MongoDB)")
    parser.add_argument("--input", "-i", type=str, default=default_input,
                        help="输入文件或目录")
    parser.add_argument("--output", "-o", type=str, default=default_output,
                        help="输出目录")
    parser.add_argument("--backend", type=str, default=default_backend,
                        help=f"OCR后端 ({', '.join(list_backends())})")
    parser.add_argument("--force", action="store_true",
                        help="强制重新处理")
    parser.add_argument("--no-images", action="store_true",
                        help="不保存图片")
    parser.add_argument("--no-json", action="store_true",
                        help="不保存JSON")
    parser.add_argument("--no-markdown", action="store_true",
                        help="不保存Markdown")

    # PaddleOCR参数
    parser.add_argument("--vl-rec-backend", type=str,
                        default=os.environ.get("VL_REC_BACKEND", "vllm-server"))
    parser.add_argument("--vl-rec-server-url", type=str,
                        default=os.environ.get("VL_REC_SERVER_URL", "http://localhost:8118/v1"))
    parser.add_argument("--vl-rec-api-model-name", type=str,
                        default=os.environ.get("VL_REC_API_MODEL_NAME", "PaddleOCR-VL-1.5-0.9B"))

    return parser


def main():
    args = create_argument_parser().parse_args()

    # MongoDB 相关变量
    mongo_store = None
    file_to_paper_id = {}
    papers = []  # 用于存储完整的论文信息（mongo 模式）

    # 根据 source 模式收集文件并初始化 MongoDB
    if args.source == "local":
        files = collect_input_files(args.input)
    elif args.source == "mongo":
        # 从 MongoDB 获取未解析文件
        try:
            from pdf_ocr_toolkit.mongodb import MongoPaperStore
            mongo_store = MongoPaperStore(
                os.environ.get("MONGO_URI", "mongodb://localhost:27017"),
                os.environ.get("MONGO_DB", "acl_anthology"),
                os.environ.get("MONGO_COLLECTION", "papers"),
            )
            papers = mongo_store.get_unparsed_papers(
                os.environ.get("PDF_BASE_PATH", "F:/papers/arxiv"),
                os.environ.get("MONGO_PATH_FIELD", "pdf_file"),
            )
            files = [p["file_path"] for p in papers]
            # 从 papers 数据中提取映射
            file_to_paper_id = {p["file_path"]: p["_id"] for p in papers}
        except ImportError:
            print("[错误] MongoDB 模式需要安装 pymongo: pip install pymongo")
            sys.exit(1)
        except Exception as e:
            print(f"[警告] MongoDB 连接失败: {e}")
            sys.exit(1)
    else:  # mixed
        # 扫描本地文件 + 智能匹配 MongoDB 记录
        files = collect_input_files(args.input)
        try:
            from pdf_ocr_toolkit.mongodb import MongoPaperStore
            mongo_store = MongoPaperStore(
                os.environ.get("MONGO_URI", "mongodb://localhost:27017"),
                os.environ.get("MONGO_DB", "acl_anthology"),
                os.environ.get("MONGO_COLLECTION", "papers"),
            )
            # 批量查询所有本地文件对应的 paper_id
            file_to_paper_id = mongo_store.find_papers_by_paths(
                files,
                os.environ.get("MONGO_PATH_FIELD", "pdf_file"),
            )
            matched_count = len(file_to_paper_id)
            print(f"  提示: {matched_count}/{len(files)} 个文件在 MongoDB 中有记录")
        except ImportError:
            print("[警告] MongoDB 模式需要安装 pymongo: pip install pymongo")
            print("  将以纯本地模式继续处理")
        except Exception as e:
            print(f"[警告] MongoDB 连接失败: {e}")
            print("  将以纯本地模式继续处理")
            mongo_store = None

    print(f"共 {len(files)} 个待处理文件")

    # 创建处理器
    ocr_processor = create_ocr_processor(args.backend, args)

    # 处理文件
    try:
        for file_path in tqdm(files, desc="正在处理"):
            base_name = Path(file_path).stem
            output_dir = Path(args.output) / base_name

            # 检查是否需要跳过
            if not args.force and file_exists(str(output_dir), base_name):
                # 如果在 MongoDB 中有记录，也标记为已解析
                if mongo_store and file_path in file_to_paper_id:
                    paper_id = file_to_paper_id[file_path]
                    if not mongo_store.is_parsed(paper_id):
                        result_dir = str(output_dir)
                        mongo_store.mark_parsed(paper_id, args.backend, result_dir)
                        print(f"  [MongoDB] 更新状态: {paper_id}")
                continue

            # 获取对应的 paper_id（如果有）
            paper_id = file_to_paper_id.get(file_path)

            try:
                # OCR 处理
                if args.backend == "paddle":
                    result = ocr_processor(file_path,
                        vl_rec_backend=args.vl_rec_backend,
                        vl_rec_server_url=args.vl_rec_server_url,
                        vl_rec_api_model_name=args.vl_rec_api_model_name,
                    )
                else:
                    result = ocr_processor(file_path)

                save_all(
                    result, file_path, str(output_dir), base_name,
                    save_images=not args.no_images,
                    save_json=not args.no_json,
                    save_markdown=not args.no_markdown,
                )

                # 更新 MongoDB 状态（如果有对应记录）
                if mongo_store and paper_id:
                    mongo_store.mark_parsed(paper_id, args.backend, str(output_dir))
                    print(f"处理完成: {output_dir} [MongoDB已更新]")
                else:
                    print(f"处理完成: {output_dir}")

            except Exception as e:
                print(f"处理失败 [{file_path}]: {e}")

                # 记录错误到 MongoDB（如果有对应记录）
                if mongo_store and paper_id:
                    mongo_store.mark_error(paper_id, str(e), args.backend)
                    print(f"  [MongoDB] 错误已记录")
    finally:
        # 关闭 MongoDB 连接
        if mongo_store:
            mongo_store.close()


if __name__ == "__main__":
    main()
