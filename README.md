# PDF OCR Toolkit

批量把 PDF 交给 PaddleOCR-VL 解析：递归扫描一个根目录下的所有 `*.pdf`，每篇论文在**它所在目录的上一级**生成一个结果目录，里面只有 `imgs/` 和一个 JSON。

## 代码组织

```
pdf-ocr-toolkit/
├── ocr_pdfs.py            # 全部逻辑，约 180 行，无类、无框架、无数据库
├── .env                   # 本地配置（含 token，已被 .gitignore 忽略）
├── .env.example           # 配置模板
├── requirements.txt       # requests / python-dotenv / tqdm / pypdf
├── scripts/
│   ├── run_official.sh    # 用官方 API 全量跑
│   ├── run_local.sh       # 用私有化部署全量跑
│   └── test.sh            # 只跑 1 篇，验证配置是否通
├── README.md
└── LICENSE
```

`ocr_pdfs.py` 内部就五块，从上往下读即可：

| 位置 | 内容 |
| --- | --- |
| 顶部 | argparse 参数 + 从 `.env` 读配置常量 |
| 小工具 | `log`（tqdm 打印）、`win_long`（Windows 长路径）、`count_pages`（本地数页数）、`valid_json`（判断旧结果是否可续用）、`save_image`（存图） |
| `ocr_official` | 官方 API：提交任务 → 轮询 → 拉 jsonl，返回每页结果 |
| `ocr_local` | 私有化部署：POST base64 到 `/layout-parsing`，同步返回 |
| `process` | 一个 PDF：断点续传判断 → 取结果 → 存图 → 写 JSON |
| `main` | 扫描 PDF → tqdm 循环 → 汇总成功/跳过/失败 |

## 安装

```bash
pip install -r requirements.txt
```

## 获取官方 API token

`OCR_MODE=official` 需要 `PADDLEOCR_API_TOKEN`，获取步骤：

1. 打开 <https://aistudio.baidu.com/paddleocr>（需登录百度账号）。
2. 点页面上方的 **「API」** 按钮，弹出「API调用」对话框。
3. 勾选 **「使用我的 AI Studio 访问令牌」**，再点代码块右上角的 **「复制代码」**——代码里的 `TOKEN = "..."` 那串就是你的 token，粘到 `.env` 的 `PADDLEOCR_API_TOKEN` 即可。
   - 代码里的 `MODEL = "PaddleOCR-VL-1.6"` 对应对话框上方的模型标签页（另有 PP-OCRv6、PP-StructureV3），换了标签页就同步改 `.env` 的 `PADDLEOCR_MODEL`。
   - 令牌属于个人账户隐私，别提交到仓库（`.env` 已被 `.gitignore` 忽略）。令牌丢了可以在对话框里点「点击获取令牌」重新取。

## 配置

复制 `.env.example` 为 `.env` 后改：

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `PDF_INPUT_DIR` | 递归扫描的根目录，找所有 `*.pdf` | `/path/to/papers` |
| `OCR_MODE` | `official` = 官方 API；`local` = 私有化部署 | `official` |
| `PDF_ORDER` | `path` = 按扫描到的原始顺序；`pages` = 页数少的先解析 | `path` |
| `OUTPUT_DIR_NAME` | 结果文件夹名（建在 PDF 所在文件夹的上一级） | `paddle_ocr_vl_1_6` |
| `OUTPUT_JSON_NAME` | 结果 JSON 的固定文件名（不带 PDF 名 / 论文名） | `paddle_ocr_vl.json` |
| `PADDLEOCR_API_TOKEN` | 官方 API token（`OCR_MODE=official` 必填，获取方法见上一节） | - |
| `PADDLEOCR_MODEL` | 官方模型名，与 AI Studio 对话框里的模型标签页对应 | `PaddleOCR-VL-1.6` |
| `LOCAL_API_URL` | 私有化部署地址（`OCR_MODE=local`） | `http://127.0.0.1:8080/layout-parsing` |
| `LOCAL_API_TOKEN` | 私有化部署 token，可空 | 空 |
| `POLL_INTERVAL` / `POLL_TIMEOUT` | 官方 API 轮询间隔 / 超时（秒） | `5` / `3600` |

## 用法

必须在仓库根目录执行（脚本里是相对路径）：

```bash
python ocr_pdfs.py                     # 全部按 .env
python ocr_pdfs.py --mode local        # 临时切私有化部署
python ocr_pdfs.py --order pages       # 先解析页数少的
python ocr_pdfs.py --limit 2           # 只跑前 2 篇，先验证效果
python ocr_pdfs.py --input /data/papers --dir-name paddle_ocr_vl_1_6
```

命令行参数会覆盖 `.env`：`--input`、`--mode`、`--order`、`--dir-name`、`--limit`。

`scripts/` 下三个一行脚本：

```bash
bash scripts/run_official.sh    # python ocr_pdfs.py --mode official
bash scripts/run_local.sh       # python ocr_pdfs.py --mode local
bash scripts/test.sh            # python ocr_pdfs.py --mode official --limit 1
```

## 解析顺序

`PDF_ORDER` 决定先解析哪一篇，取两个值：

| 值 | 行为 |
| --- | --- |
| `path`（默认） | 按路径扫描出来的原始顺序，稳定可预期，不额外读文件 |
| `pages` | 先解析**页数少**的，再解析页数多的（升序） |

选 `pages` 时，脚本会先用 `pypdf` 在本地把每个 PDF 的页数数一遍（会多一个 `统计页数` 进度条），然后按页数升序排。

- 好处：先用小文件把整条链路跑通、拿到结果，大文件排后面，中断了也不影响已出的结果。
- 页数读不出来的 PDF（损坏、加密）会被排到最后，但**不会被跳过**，照样会尝试解析。
- 数页数是纯本地 IO，不消耗 API 额度。
- 注意 `--limit` 是在排序**之后**才截断的，所以 `--order pages --limit 3` 会取最短的 3 篇。

## 输出结构

结果目录建在 **PDF 所在目录的上一级**：

```
<论文目录>/
├── pdf/                          # PDF 所在的目录，名字随意、可有多层
│   └── xxx.pdf
└── paddle_ocr_vl_1_6/            # <- 结果目录（名字由 OUTPUT_DIR_NAME 决定）
    ├── imgs/                     # 该 PDF 的全部图片，扁平存放
    │   └── img_in_image_box_612_1040_1046_1201.jpg
    └── paddle_ocr_vl.json        # 固定文件名，由 OUTPUT_JSON_NAME 决定
```

## JSON 结构

```json
{
  "total_pages": 20,
  "pages": [
    [
      { "label": "fig", "figure_path": "imgs/img_in_image_box_612_1040_1046_1201.jpg" },
      { "page_index": 0, "page_content": "# 标题\n\n正文 markdown ..." }
    ],
    [
      { "page_index": 1, "page_content": "## 1 Introduction\n\n..." }
    ]
  ]
}
```

顶层两个字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `total_pages` | int | 实际解析出的页数，等于 `pages` 的长度 |
| `pages` | array | 每一页一个元素，顺序与 PDF 页序一致 |

`pages` 的每个元素是一个**数组**，里面是若干条目。条目只有两种形状：

| 条目 | 字段 | 类型 | 说明 |
| --- | --- | --- | --- |
| 图片条目 | `label` | string | 条目类型，目前恒为 `"fig"`（插图） |
| | `figure_path` | string | 图片相对结果目录的路径，固定为 `imgs/<文件名>`；文件一定已落盘 |
| 正文条目 | `page_index` | int | 页序号，从 `0` 开始，等于该页在 `pages` 里的下标 |
| | `page_content` | string | 该页的 Markdown 正文（含公式、表格） |

排列顺序：**图片条目在前**（按 PaddleOCR 返回顺序），**正文条目永远是最后一个元素**。

> **注意：不是每页都有 `label` / `figure_path`。**
> 页面上没有插图时，那一页只有一个元素——正文条目。上面第 2 页就是这种页。
> 实测 400 篇论文共 7666 页，其中 **68.6% 的页面没有图片条目**。
> 想安全地取一页的图片，用 `[x for x in page if "label" in x]`，不要假设 `page[0]` 是图片。

## 断点续传与失败重试

- **断点续传**：结果目录里 `paddle_ocr_vl.json` 存在**且能正常解析** → 直接跳过，重复跑不会重复花钱。若该文件存在但已损坏（上次写了一半崩掉），判定为无效，自动删掉重新解析。
- **失败重试**：解析失败只打印错误、**不写 JSON**，并清掉半成品 `imgs/` 和写了一半的 JSON，下一篇继续；下次重跑该篇会完整重来。结尾打印失败清单。
- **单篇异常不中断整批**：每篇都包在 try/except 里，任何异常（HTTP 非 200、任务 `failed`、轮询超时、网络中断、JSON 缺字段、写盘失败等）都只影响当前这一篇，记录到失败清单后继续下一篇。唯一例外是 `Ctrl-C`——它是 `KeyboardInterrupt`，不被吞掉，会整体中断（想停就停）。
- **空结果也算失败**：接口返回 200 但一页都没有（`layoutParsingResults` 为空）时按失败处理，不会写出一个 0 页的 JSON 然后被当成"已完成"永远跳过。
- 进度条用 tqdm，形如 `OCR: 100%|██████████| 1/1 [01:32<00:00, 92.27s/篇]`；每篇结束打印耗时，最后打印总耗时。

## 两种模式

- `official`：走 PaddleOCR 官方 job API（提交 → 轮询 → 拉 jsonl），需要 token，异步。额度与限制（AI Studio 对话框里的「API调用须知」）：
  - 每个模型有**当日解析页数上限**（默认 20000 页/天，对话框里显示为「今日调用解析页数 0 / 20,000」），超上限返回 **429**，可在对话框里「申请更多页数」。
  - 单个文件大小无限制，但建议控制在 **100 页内**，**超出部分将被忽略不解析**。
- `local`：POST base64 到你自己的 `/layout-parsing` 服务，同步返回。页数上限由你的产线配置决定（`Serving.extra.max_num_input_imgs`，为 `null` 则不限）。图片字段两种模式都兼容（`http` 开头当 URL 下载，否则按 base64 解码）。

## 注意

- Windows 长路径（>240 字符）会自动加 `\\?\` 前缀，论文名过长也不怕写不进文件。
- 官方 API 解析出的页数少于 PDF 实际页数，通常是撞了上面那条 100 页限制；`local` 模式则要看产线配置 `max_num_input_imgs`，脚本侧改不了。
