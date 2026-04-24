# PDF OCR Toolkit

一个功能强大的 PDF 文档解析工具，支持 OCR 文字识别、公式识别，并可与 MongoDB 集成管理论文解析状态。

## ✨ 功能特性

- **多后端支持**：支持 PaddleOCR 本地处理和远程 API 调用
- **MongoDB 集成**：三种工作模式，灵活管理论文解析状态
- **批量处理**：高效处理大量 PDF 文件
- **多种输出格式**：支持 Markdown、JSON、图片等多种输出格式
- **智能状态管理**：自动记录解析状态，避免重复处理
- **错误处理**：完善的错误记录和重试机制
- **灵活配置**：通过环境变量或命令行参数灵活配置

## 📦 安装

### 前置要求

- Python 3.8+
- MongoDB（可选，用于 MongoDB 模式）

### 安装步骤

```bash
# 克隆项目
git clone <your-repo-url>
cd pdf_ocr_toolkit

# 安装依赖
pip install -r requirements.txt
```

### requirements.txt

```
paddleocr>=2.7.0
pymongo>=4.0.0
python-dotenv>=1.0.0
tqdm>=4.65.0
pillow>=10.0.0
```

## 🚀 快速开始

### 1. 配置环境变量

复制 `.env.example` 为 `.env` 并修改相应配置：

```bash
cp .env.example .env
```

### 2. 基本使用

```bash
# Local 模式：扫描本地文件
python -m pdf_ocr_toolkit.main --source=local --input=./papers --output=./output

# MongoDB 模式：从 MongoDB 获取待解析文件
python -m pdf_ocr_toolkit.main --source=mongo

# Mixed 模式：扫描本地 + 智能更新 MongoDB
python -m pdf_ocr_toolkit.main --source=mixed --input=./papers
```

## 📖 使用模式

### Local 模式

**适用场景**：独立的本地文件处理，不需要 MongoDB

```bash
python -m pdf_ocr_toolkit.main \
    --source=local \
    --input=./papers \
    --output=./output \
    --backend=api
```

**特点**：
- 扫描指定目录下的所有 PDF 文件
- 不访问 MongoDB
- 适合小型项目或临时任务

### MongoDB 模式

**适用场景**：集中式管理论文解析状态

```bash
python -m pdf_ocr_toolkit.main \
    --source=mongo \
    --output=./output \
    --backend=api
```

**特点**：
- 从 MongoDB 读取未解析文件列表
- 处理完成后自动更新 MongoDB 状态
- 支持断点续传和错误重试
- 适合生产环境和大规模处理

### Mixed 模式

**适用场景**：灵活的本地处理 + 状态管理

```bash
python -m pdf_ocr_toolkit.main \
    --source=mixed \
    --input=./papers \
    --output=./output \
    --backend=api
```

**特点**：
- 扫描本地文件
- 智能匹配 MongoDB 记录
- 匹配到的文件会更新状态
- 未匹配的文件正常处理
- 适合渐进式迁移和混合场景

## ⚙️ 配置说明

### 环境变量配置

```bash
# OCR 后端选择
OCR_BACKEND=api  # 可选: paddle, api

# MongoDB 配置（mongo/mixed 模式需要）
MONGO_URI=mongodb://localhost:27017
MONGO_DB=acl_anthology
MONGO_COLLECTION=papers
MONGO_PATH_FIELD=pdf_file
PDF_BASE_PATH=F:/papers/arxiv

# 输入输出路径
OCR_INPUT=F:/papers/arxiv
OCR_OUTPUT=./output

# PaddleOCR 配置（backend=paddle 时需要）
VL_REC_BACKEND=vllm-server
VL_REC_SERVER_URL=http://localhost:8118/v1
VL_REC_API_MODEL_NAME=PaddleOCR-VL-1.5-0.9B

# API 配置（backend=api 时需要）
OCR_API_URL=https://your-api-endpoint.com/layout-parsing
OCR_API_TOKEN=your-api-token
```

### 命令行参数

```bash
python -m pdf_ocr_toolkit.main [OPTIONS]

选项:
  --source {local,mongo,mixed}  输入来源模式
  --input, -i PATH              输入文件或目录
  --output, -o PATH             输出目录
  --backend {paddle,api}        OCR 后端选择
  --force                       强制重新处理已存在文件
  --no-images                   不保存图片
  --no-json                     不保存 JSON
  --no-markdown                 不保存 Markdown
  --vl-rec-backend TEXT         公式识别后端
  --vl-rec-server-url TEXT      VLLM 服务器地址
  --vl-rec-api-model-name TEXT  VLLM 模型名称
```

## 📝 MongoDB 数据结构

### 集合结构

```javascript
{
  "_id": ObjectId("..."),
  "pdf_file": "arxiv/2023/1234.pdf",  // 相对路径
  "title": "论文标题",
  "authors": ["作者1", "作者2"],
  "pdf_parse": {
    "parsed": true,                    // 是否已解析
    "parsed_at": ISODate("2024-04-24"),  // 解析时间
    "ocr_model": "api",                // 使用的 OCR 模型
    "parse_result_dir": "./output/1234",  // 结果目录
    "parse_error": null                // 错误信息（如有）
  }
}
```

## 🔄 工作流程

### Local 模式流程

```
扫描本地文件 → OCR 处理 → 保存结果
```

### MongoDB 模式流程

```
查询未解析文件 → OCR 处理 → 更新 MongoDB 状态
     ↓                           ↓
  获取 paper_id            mark_parsed()
     ↓                           ↓
  文件路径映射              或 mark_error()
```

### Mixed 模式流程

```
扫描本地文件 → 批量查询 MongoDB → 匹配 paper_id
     ↓                              ↓
  OCR 处理                     如果匹配则：
     ↓                       - 处理成功：mark_parsed()
  保存结果                   - 处理失败：mark_error()
```

## 📊 输出格式

处理完成后，每个 PDF 会生成一个独立的输出目录：

```
output/
├── paper_1/
│   ├── full_markdown.md    # 完整 Markdown（推荐）
│   ├── structured.json     # 结构化 JSON 数据
│   ├── pages/              # 逐页图片
│   │   ├── page_001.jpg
│   │   ├── page_002.jpg
│   │   └── ...
```

### Markdown 输出示例

```markdown
# 论文标题

## 第 1 页

[页面文字内容...]

## 第 2 页

[更多内容...]
```

### JSON 输出结构

```json
{
  "file_path": "path/to/paper.pdf",
  "total_pages": 10,
  "pages": [
    {
      "page_number": 1,
      "text": "页面文字内容",
      "images": ["path/to/image.jpg"]
    }
  ]
}
```

## 🛠️ 作为库使用

### 处理单个文件

```python
from pdf_ocr_toolkit import process_pdf

result = process_pdf("paper.pdf", backend="api")
print(result['full_markdown'])
```

### 批量处理

```python
from pdf_ocr_toolkit import process_batch

results = process_batch("./papers", backend="api")
success_count = sum(1 for r in results if r['success'])
print(f"成功处理 {success_count}/{len(results)} 个文件")
```

## 🐛 常见问题

### 1. MongoDB 连接失败

**错误**：`MongoDB 连接失败`

**解决**：
- 检查 MongoDB 服务是否运行
- 确认 `MONGO_URI` 配置正确
- 验证网络连接和防火墙设置

### 2. 文件路径不匹配

**错误**：Mixed 模式下文件无法匹配 MongoDB 记录

**解决**：
- 确认 `PDF_BASE_PATH` 与 MongoDB 中的相对路径基准一致
- 检查 `MONGO_PATH_FIELD` 字段名是否正确
- 查看控制台输出的匹配数量

### 3. 已处理文件被重复处理

**原因**：输出目录不存在但 MongoDB 状态已更新

**解决**：
- 使用 `--force` 强制重新处理
- 或手动删除 MongoDB 中的解析状态

## 🔧 开发指南

### 项目结构

```
pdf_ocr_toolkit/
├── __init__.py           # 包初始化
├── main.py               # CLI 入口和 API
├── mongodb.py            # MongoDB 集成
├── utils.py              # 工具函数
├── ocr/                  # OCR 后端实现
│   ├── __init__.py
│   ├── paddle_backend.py
│   └── api_backend.py
├── .env                  # 环境变量配置
├── .gitignore           # Git 忽略文件
└── README.md            # 项目文档
```

### 添加新的 OCR 后端

1. 在 `ocr/` 目录下创建新的后端文件
2. 实现处理函数
3. 在 `ocr/__init__.py` 中注册后端
4. 更新文档和配置示例

## 📝 更新日志

### v1.1.0 (2024-04-24)

- ✨ 新增 `--source=mixed` 模式
- ✨ 优化 MongoDB 状态更新机制
- ✨ 添加批量查询优化
- ✨ 改进错误处理和日志记录
- ✨ 完善中文文档

### v1.0.0 (2024-04-20)

- 🎉 初始版本发布
- ✨ 支持 Local 和 MongoDB 模式
- ✨ 实现 PaddleOCR 和 API 双后端

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

1. Fork 本项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

## 👥 作者

- Your Name - Initial work

## 🙏 致谢

- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) - 优秀的 OCR 框架
- [pymongo](https://github.com/mongodb/mongo-python-driver) - MongoDB Python 驱动
- 所有贡献者

## 📮 联系方式

- 项目主页：[GitHub Repository]
- 问题反馈：[GitHub Issues]

---

⭐ 如果这个项目对你有帮助，请给个 Star！
