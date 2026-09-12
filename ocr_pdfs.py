"""批量 OCR PDF（PaddleOCR-VL）。

- 递归扫描 PDF_INPUT_DIR 下所有 *.pdf
- 每个 PDF 在「它所在文件夹的上一级」新建 OUTPUT_DIR_NAME 目录，里面放 imgs/ + paddle_ocr_vl.json
- 已生成 JSON 的 PDF 直接跳过（断点续传）；失败的只打印不写 JSON，下次重跑会重试

用法：
    python ocr_pdfs.py                          # 全部按 .env
    python ocr_pdfs.py --mode local             # 临时切私有化部署
    python ocr_pdfs.py --order pages            # 先解析页数少的 PDF
    python ocr_pdfs.py --input /data/papers --limit 2
"""

import argparse
import base64
import glob
import json
import os
import shutil
import time

import requests
from dotenv import load_dotenv
from pypdf import PdfReader
from tqdm import tqdm

load_dotenv()

_parser = argparse.ArgumentParser()
_parser.add_argument("--input", help="覆盖 .env 的 PDF_INPUT_DIR")
_parser.add_argument("--mode", choices=["official", "local"], help="覆盖 .env 的 OCR_MODE")
_parser.add_argument("--order", choices=["path", "pages"], help="覆盖 .env 的 PDF_ORDER")
_parser.add_argument("--dir-name", help="覆盖 .env 的 OUTPUT_DIR_NAME")
_parser.add_argument("--limit", type=int, default=0, help="只处理前 N 个 PDF（测试用）")
args = _parser.parse_args()

INPUT_DIR = args.input or os.getenv("PDF_INPUT_DIR", "")
MODE = (args.mode or os.getenv("OCR_MODE", "official")).strip().lower()   # official | local
ORDER = (args.order or os.getenv("PDF_ORDER", "path")).strip().lower()    # path | pages
OUT_DIR_NAME = args.dir_name or os.getenv("OUTPUT_DIR_NAME", "paddle_ocr_vl_1_6")
JSON_NAME = os.getenv("OUTPUT_JSON_NAME", "paddle_ocr_vl.json")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "5"))
POLL_TIMEOUT = int(os.getenv("POLL_TIMEOUT", "3600"))

OFFICIAL_JOB_URL = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
OFFICIAL_TOKEN = os.getenv("PADDLEOCR_API_TOKEN", "")
OFFICIAL_MODEL = os.getenv("PADDLEOCR_MODEL", "PaddleOCR-VL-1.6")

LOCAL_API_URL = os.getenv("LOCAL_API_URL", "http://127.0.0.1:8080/layout-parsing")
LOCAL_API_TOKEN = os.getenv("LOCAL_API_TOKEN", "")

OPTIONAL_PAYLOAD = {
    "useDocOrientationClassify": False,
    "useDocUnwarping": False,
    "useChartRecognition": False,
}


def log(msg):
    """用 tqdm.write 打印，避免把进度条冲乱"""
    tqdm.write(str(msg))


def win_long(p):
    """Windows 长路径（>240 字符）加 \\\\?\\ 前缀"""
    p = os.path.abspath(p)
    return "\\\\?\\" + p if len(p) > 240 else p


def count_pages(pdf_path):
    """本地读 PDF 页数（pypdf）；读不了返回 None"""
    try:
        return len(PdfReader(win_long(pdf_path)).pages)
    except Exception:
        return None


def valid_json(p):
    """文件存在且能解析（上次写到一半崩掉的会被判为无效）"""
    try:
        with open(win_long(p), encoding="utf-8") as f:
            json.load(f)
        return True
    except Exception:
        return False


def save_image(value, dest):
    """value 是图片 URL（官方 API）或 base64 字符串（私有化部署）"""
    os.makedirs(os.path.dirname(win_long(dest)), exist_ok=True)
    data = requests.get(value, timeout=120).content if value.startswith("http") else base64.b64decode(value)
    with open(win_long(dest), "wb") as f:
        f.write(data)


def ocr_official(pdf_path):
    """官方 API：提交任务 -> 轮询 -> 拉 jsonl，返回每页 layoutParsingResults"""
    headers = {"Authorization": f"bearer {OFFICIAL_TOKEN}"}
    with open(win_long(pdf_path), "rb") as f:
        resp = requests.post(
            OFFICIAL_JOB_URL,
            headers=headers,
            data={"model": OFFICIAL_MODEL, "optionalPayload": json.dumps(OPTIONAL_PAYLOAD)},
            files={"file": f},
        )
    if resp.status_code != 200:
        raise RuntimeError(f"提交失败 {resp.status_code}: {resp.text[:300]}")
    job_id = resp.json()["data"]["jobId"]
    log(f"    jobId={job_id}")

    deadline = time.time() + POLL_TIMEOUT
    while True:
        data = requests.get(f"{OFFICIAL_JOB_URL}/{job_id}", headers=headers, timeout=60).json()["data"]
        state = data["state"]
        if state == "done":
            jsonl = requests.get(data["resultUrl"]["jsonUrl"], timeout=300).text
            results = []
            for line in jsonl.strip().split("\n"):
                if line.strip():
                    results.extend(json.loads(line)["result"]["layoutParsingResults"])
            return results
        if state == "failed":
            raise RuntimeError(f"任务失败: {data.get('errorMsg')}")
        if time.time() > deadline:
            raise RuntimeError(f"轮询超时（{POLL_TIMEOUT}s）")
        prog = data.get("extractProgress") or {}
        log(f"    {state} {prog.get('extractedPages', '?')}/{prog.get('totalPages', '?')}")
        time.sleep(POLL_INTERVAL)


def ocr_local(pdf_path):
    """私有化部署：POST base64 到 /layout-parsing，同步返回"""
    with open(win_long(pdf_path), "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    headers = {"Content-Type": "application/json"}
    if LOCAL_API_TOKEN:
        headers["Authorization"] = f"token {LOCAL_API_TOKEN}"
    resp = requests.post(LOCAL_API_URL, json={"file": b64, "fileType": 0, **OPTIONAL_PAYLOAD},
                         headers=headers, timeout=POLL_TIMEOUT)
    if resp.status_code != 200:
        raise RuntimeError(f"请求失败 {resp.status_code}: {resp.text[:300]}")
    return resp.json()["result"]["layoutParsingResults"]


def process(pdf_path):
    """OCR 一个 PDF，结果写进 上一级目录/OUT_DIR_NAME/"""
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(pdf_path))), OUT_DIR_NAME)
    json_path = os.path.join(out_dir, JSON_NAME)

    if os.path.exists(win_long(json_path)):
        if valid_json(json_path):
            log(f"  已存在，跳过：{json_path}")
            return "skip"
        log(f"  上次结果损坏，重新解析：{json_path}")
        os.remove(win_long(json_path))

    imgs_dir = os.path.join(out_dir, "imgs")
    shutil.rmtree(win_long(imgs_dir), ignore_errors=True)   # 清掉上次失败留下的半成品
    os.makedirs(win_long(imgs_dir), exist_ok=True)

    try:
        results = ocr_official(pdf_path) if MODE == "official" else ocr_local(pdf_path)
        if not results:
            raise RuntimeError("接口没有返回任何页面")

        pages = []
        for idx, res in enumerate(results):
            markdown = res["markdown"]
            items = []
            for rel_path, img in (markdown.get("images") or {}).items():
                rel_path = "imgs/" + os.path.basename(rel_path.replace("\\", "/"))
                save_image(img, os.path.join(out_dir, rel_path))
                items.append({"label": "fig", "figure_path": rel_path})
            items.append({"page_index": idx, "page_content": markdown["text"]})
            pages.append(items)

        with open(win_long(json_path), "w", encoding="utf-8") as f:
            json.dump({"total_pages": len(pages), "pages": pages}, f, ensure_ascii=False, indent=2)
    except Exception:
        shutil.rmtree(win_long(imgs_dir), ignore_errors=True)   # 失败不留半成品，下次完整重试
        if os.path.exists(win_long(json_path)):
            os.remove(win_long(json_path))                      # 连同写了一半的 JSON 一起清掉
        raise

    log(f"  完成 {len(pages)} 页 -> {out_dir}")
    return "ok"


def main():
    if not INPUT_DIR:
        raise SystemExit("请在 .env 里设置 PDF_INPUT_DIR，或用 --input 指定")
    if MODE == "official" and not OFFICIAL_TOKEN:
        raise SystemExit("请在 .env 里设置 PADDLEOCR_API_TOKEN")

    pdfs = sorted(set(glob.glob(os.path.join(INPUT_DIR, "**", "*.pdf"), recursive=True))
                  | set(glob.glob(os.path.join(INPUT_DIR, "**", "*.PDF"), recursive=True)))
    if not pdfs:
        raise SystemExit(f"没找到 PDF：{INPUT_DIR}")

    counts = {}
    if ORDER == "pages":        # 先本地数页数，页数少的先解析
        for pdf in tqdm(pdfs, desc="统计页数", unit="篇"):
            counts[pdf] = count_pages(pdf)
        pdfs.sort(key=lambda p: (counts[p] is None, counts[p] or 0))   # 页数读不出来的排最后

    if args.limit:
        pdfs = pdfs[:args.limit]
    print(f"扫描到 {len(pdfs)} 个 PDF（{INPUT_DIR}），模式={MODE}，顺序={ORDER}")

    ok, skipped, failed = 0, 0, []
    start = time.time()
    for pdf in tqdm(pdfs, desc="OCR", unit="篇"):
        pages_info = f"（{counts[pdf]} 页）" if counts.get(pdf) else ""
        log(f"  {pdf}{pages_info}")
        t0 = time.time()
        try:
            r = process(pdf)
            ok += r == "ok"
            skipped += r == "skip"
        except Exception as e:
            log(f"  失败，跳过下次重试：{e}")
            failed.append(pdf)
            continue
        log(f"  耗时 {time.time() - t0:.0f}s")

    print(f"\n完成：成功 {ok}，跳过 {skipped}，失败 {len(failed)}，总耗时 {(time.time() - start) / 60:.1f} 分钟")
    for pdf in failed:
        print(f"  失败：{pdf}")


if __name__ == "__main__":
    main()
