# 24. 文档解析 Worker 设计

> 版本：v0.6 · 2026-05-06

---

## 一句话职责

**把用户上传的文件安全、准确地提取成纯文本**，供模型和下游工具消费。

**类比**：保密文件拆封室——文件进来，在受控环境下拆开、扫描成文字，原文件不落地、不留痕。

---

## 安全前提（P0 硬约束）

| 约束 | 说明 | 违反后果 |
|------|------|---------|
| **敏感文件不写磁盘** | 合同/公文/附件直接流入内存缓冲区或直传解析服务 | 写磁盘 = 合规风险 |
| **解析后即焚** | 提取的文本存入临时对象存储（`temp/` 桶），session 过期自动清理 | 长期留档需经审批流程 |
| **沙箱执行** | 解析过程在隔离容器/进程内运行，禁止网络访问 | 防恶意文件攻击 |
| **格式白名单** | 仅允许 `agent.yaml` 中 `ui_config.attachments.accept` 声明的格式 | 防恶意文件上传 |

### 对象存储 temp 桶安全约束（MinIO）

解析后的文本临时存入对象存储 `temp/` 桶，必须满足：

| 约束 | 要求 |
|------|------|
| **服务端加密（SSE）** | temp 桶必须启用 SSE-S3 或 SSE-KMS，静态数据加密存储 |
| **生命周期策略** | 24 小时自动删除（Object Lifecycle Rule），禁止长期保留 |
| **桶访问策略** | 仅 core 服务与 doc-worker 有读写权限，其他服务只读或无权 |
| **网络隔离** | temp 桶不暴露公网 URL，仅限内网 VPC 访问 |
| **审计日志** | MinIO 审计日志记录所有 temp 桶写操作，保留 90 天 |
| **禁止本地落盘** | 处理链路：内存缓冲区 → 直传 MinIO temp/ → doc-worker 流式读取 → 解析后删除 temp 对象。禁止写入 `/tmp` 或本地文件系统 |

---

## 支持的文档格式矩阵

| 格式 | 扩展名 | MIME 类型 | 解析方式 | 同步/异步 | 最大文件大小 | 说明 |
|------|--------|-----------|---------|-----------|-------------|------|
| PDF | .pdf | `application/pdf` | pdfplumber / PyMuPDF / PyPDF2 | ≤10MB 同步，>10MB 异步 | 100MB | 优先 pdfplumber（表格保留更好），无文本层则 OCR |
| Word | .docx | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | python-docx | ≤10MB 同步，>10MB 异步 | 100MB | 保留段落结构 |
| Word (legacy) | .doc | `application/msword` | antiword / LibreOffice headless | ≤10MB 同步，>10MB 异步 | 100MB | legacy 格式，兼容性处理 |
| Excel | .xlsx | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` | openpyxl | ≤10MB 同步，>10MB 异步 | 50MB | 多个 sheet 按 sheet 名分隔输出 |
| PPT | .pptx | `application/vnd.openxmlformats-officedocument.presentationml.presentation` | python-pptx | ≤10MB 同步，>10MB 异步 | 100MB | 每页按 "--- Slide N ---" 分隔 |
| 纯文本 | .txt | `text/plain` | 直接读取 | 同步 | 50MB | 编码自动检测（utf-8 / gbk / gb2312），BOM 自动去除 |
| Markdown | .md | `text/markdown` | 直接读取 | 同步 | 50MB | 保留 markdown 语法 |
| 图片 | .png, .jpg, .jpeg | `image/png`, `image/jpeg` | OCR（PaddleOCR / Tesseract） | 异步 | 50MB | 单张图片 OCR；中文场景优先 PaddleOCR |

**不支持的格式**：`.exe`, `.zip`, `.rar`, `.7z`, `.js`, `.html`, `.htm`, `.rtf` 等可执行或脚本类文件——即使伪装扩展名，后端按 MIME 魔数二次校验，直接拒绝。

---

## 解析流程

```
用户上传文件
  ↓
1. 格式预检（widget 层）
   ├─→ 扩展名是否在 ui_config.attachments.accept
   └─→ 大小是否超过 ui_config.attachments.max_size_mb
  ↓
2. 后端二次校验
   ├─→ MIME 魔数校验（防改扩展名绕过）
   ├─→ 文件大小二次校验
   └─→ 病毒扫描（如有集成杀毒服务）
  ↓
3. 内存缓冲 / 直传解析服务
   ├─→ 小文件（<10MB）：直接读入内存 byte[]
   └─→ 大文件（≥10MB）：流式直传 Doc Worker，不经过应用内存
  ↓
4. Doc Worker 沙箱解析
   ├─→ 按格式选择解析器
   ├─→ 提取纯文本 + 结构信息（页码 / 段落 / 表格位置）
   └─→ 超时控制（默认 30 秒，大文件 60 秒）
  ↓
5. 结果处理
   ├─→ 文本存入对象存储 temp/ 桶（TTL = session 过期时间）
   ├─→ file_uploads 表更新状态 → extracted
   └─→ 返回 file_id + extracted_text（前 500 字摘要）给 widget
  ↓
6. 模型消费
   ├─→ 用户后续对话中引用该文件
   └─→ Tool Gateway 的 doc.extract 工具按 file_id 拉取全文
```

---

## Doc Worker 架构

### 部署形态

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│  API Gateway    │─────>│  Doc Worker     │─────>│  Object Storage │
│  (文件上传接口)  │      │  Pool (K8s Pod) │      │  (temp/ 桶)     │
└─────────────────┘      └─────────────────┘      └─────────────────┘
                                │
                                ↓
                         ┌─────────────────┐
                         │  Anti-Virus     │
                         │  (可选集成)      │
                         └─────────────────┘
```

- **Doc Worker 以独立 Pod / 进程池部署**，与主应用解耦
- 每个 Worker 进程单线程处理一个文件，处理完即释放
- Worker 池大小按并发量自动扩缩容（HPA：CPU >70% 或队列长度 >1000 时扩容）

### 沙箱约束

```yaml
sandbox:
  network: false                    # 禁止网络访问
  filesystem: temp_only             # 仅允许写临时目录
  temp_dir_max_size: 100MB          # 临时目录大小上限
  max_memory_mb: 512                # 单文件解析内存上限（常规文件）
  max_memory_mb_ocr: 2048           # OCR 任务内存上限
  timeout_seconds: 30               # 默认超时
  timeout_seconds_large_file: 60    # 大文件超时
  allowed_libraries:                # 仅允许加载白名单内的解析库
    - pdfplumber
    - python-docx
    - openpyxl
    - PyMuPDF
    - paddleocr
```

---

## Worker 内部流程

```python
async def process_extraction_task(task):
    file_path = download_from_minio(task.storage_path)

    try:
        # 1. 文件类型校验（魔数 + 扩展名双重校验）
        detected_mime = detect_mime(file_path)
        if not is_allowed_mime(detected_mime):
            raise UnsupportedFormat(f"Detected mime {detected_mime} not allowed")

        # 2. 按格式选择解析器
        extractor = get_extractor(detected_mime)

        # 3. 提取文本
        result = await asyncio.wait_for(
            extractor.extract(file_path),
            timeout=task.timeout_seconds
        )

        # 4. 后处理
        result.text = sanitize_text(result.text)  # 去除控制字符、统一换行符

        # 5. 上传结果
        extracted_path = upload_to_minio(result.text, prefix="extracted/")

        # 6. 更新状态
        await db.execute(
            "UPDATE file_uploads SET status='extracted', extracted_text_path=? WHERE id=?",
            extracted_path, task.file_id
        )

    except Exception as e:
        await db.execute(
            "UPDATE file_uploads SET status='failed', error_message=? WHERE id=?",
            str(e), task.file_id
        )
        raise
    finally:
        # 7. 清理本地临时文件
        os.unlink(file_path)
```

---

## 解析器实现要点

### PDF 解析

```python
def extract_pdf(file_path: str) -> ExtractResult:
    """优先 pdfplumber，fallback 到 PyMuPDF / PyPDF2"""
    try:
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            pages = []
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                pages.append(f"--- Page {i+1} ---\n{text}")
            return ExtractResult(text="\n\n".join(pages), pages=len(pdf.pages))
    except Exception:
        try:
            import PyMuPDF
            doc = PyMuPDF.open(file_path)
            pages = []
            for i, page in enumerate(doc):
                text = page.get_text() or ""
                pages.append(f"--- Page {i+1} ---\n{text}")
            return ExtractResult(text="\n\n".join(pages), pages=len(doc))
        except Exception:
            import PyPDF2
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                pages = []
                for i, page in enumerate(reader.pages):
                    text = page.extract_text() or ""
                    pages.append(f"--- Page {i+1} ---\n{text}")
                return ExtractResult(text="\n\n".join(pages), pages=len(reader.pages))
```

### OCR（图片）

```python
async def extract_image_ocr(file_path: str) -> ExtractResult:
    """PaddleOCR，中文场景优于 Tesseract"""
    from paddleocr import PaddleOCR
    ocr = PaddleOCR(use_angle_cls=True, lang='ch', show_log=False)
    result = ocr.ocr(file_path, cls=True)

    lines = []
    for line in result[0]:
        text = line[1][0]  # PaddleOCR 返回格式
        confidence = line[1][1]
        if confidence > 0.5:  # 过滤低置信度
            lines.append(text)

    return ExtractResult(text="\n".join(lines), pages=1)
```

---

## 任务队列设计

```python
# Redis Stream 作为任务队列
stream_key = "doc:extract:pending"
consumer_group = "doc_workers"

# 生产者（Core 服务）
async def enqueue(file_id: str):
    await redis.xadd(stream_key, {"file_id": file_id})

# 消费者（Doc Worker）
async def consume():
    while True:
        messages = await redis.xreadgroup(
            consumer_group, worker_id,
            {stream_key: ">"},
            count=1, block=5000
        )
        for stream, msgs in messages:
            for msg_id, fields in msgs:
                file_id = fields["file_id"]
                try:
                    await process_extraction_task(file_id)
                    await redis.xack(stream_key, consumer_group, msg_id)
                except Exception:
                    # 失败次数 +1，超过 3 次转入死信队列
                    retry_count = await redis.hincrby(f"doc:retry:{file_id}", "count", 1)
                    if retry_count >= 3:
                        await redis.xadd("doc:extract:dead", {"file_id": file_id, "error": traceback.format_exc()})
                        await redis.xack(stream_key, consumer_group, msg_id)
```

---

## 结果格式

Doc Worker 输出的结构化文本：

```json
{
  "file_id": "file_uuid",
  "status": "success",
  "pages": 12,
  "total_chars": 8500,
  "content": "\n--- Page 1 ---\n合同编号：HT-2026-001\n...\n--- Page 2 ---\n第一条 合同标的\n...",
  "structure": [
    {"type": "paragraph", "page": 1, "text": "合同编号：HT-2026-001"},
    {"type": "table", "page": 3, "rows": 5, "cols": 4},
    {"type": "heading", "page": 2, "level": 1, "text": "第一条 合同标的"}
  ],
  "warnings": [
    "page_5: 包含扫描图片，已尝试 OCR 但识别率可能较低"
  ]
}
```

**超长文件处理**：

- 超过 `max_tokens`（如 8000 tokens ≈ 24000 中文字）的文件，触发分块策略
- 分块方式：按自然段落切分，每块保留前后 200 字重叠上下文
- 模型通过 `doc.extract` 工具可按页码/章节按需拉取特定块

---

## 错误处理

| 错误场景 | 错误码 | 响应 | 用户提示 |
|---------|--------|------|---------|
| 格式不支持 | `INVALID_FILE_TYPE` | 400 | "暂不支持该文件格式，请上传 PDF/Word/TXT" |
| 文件过大 | `FILE_TOO_LARGE` | 413 | "文件超过大小限制，请拆分后上传" |
| 解析超时 | `EXTRACTION_TIMEOUT` | 504 | "文件解析超时，请检查文件是否损坏或过大" |
| 加密 PDF | `ENCRYPTED_DOCUMENT` | 422 | "无法解析加密文档，请先解除密码保护" |
| 扫描件无 OCR | `NO_TEXT_LAYER` | 422 | "该文档为扫描件，文字识别失败，请提供可搜索 PDF" |
| 病毒检测阳性 | `MALWARE_DETECTED` | 403 | "文件未通过安全检测，禁止上传" |

---

## 与 Tool Gateway 的集成

Doc Worker 的解析结果作为 `doc.extract` 工具的输出：

```
Agent Runner ──→ Tool Gateway ──→ Doc Worker
  调 doc.extract    路由到 doc     按 file_id 拉取对象存储
  (file_id=xxx)     执行解析      返回结构化文本
```

- `doc.extract` 是 Tool Gateway 注册的标准工具之一
- 权限校验：`file_id` 必须属于当前 `session_id`，防横向越权
- 结果缓存：同一 `file_id` 的解析结果在 Redis 缓存 5 分钟，避免重复解析

---

## 资源隔离

| 资源 | 限制 | 说明 |
|------|------|------|
| CPU | 单任务最多 2 核 | OCR 密集型任务独占 |
| 内存 | 单任务最多 2GB | 超大 PDF 可能导致内存峰值 |
| 磁盘 | 本地临时文件 10GB | 下载文件 + 中间产物 |
| 网络 | 禁止外网访问 | 仅允许访问 MinIO 内网 endpoint |
| 超时 | 默认 60s，最大 300s | 超大文件可配置 |

---

## 性能指标

| 指标 | 目标 | 说明 |
|------|------|------|
| 解析延迟 P99 | <5s（<10MB） | 常规合同/公文 |
| 解析延迟 P99 | <30s（10-50MB） | 大型文档 |
| 并发解析数 | 按 Worker 池大小 | 默认 10 并发，可扩容 |
| 内存占用 | <512MB/文件（常规）<2GB/文件（OCR） | 沙箱限制 |
| 文本提取准确率 | >98%（可搜索 PDF） | 不含扫描件 OCR |

---

## 监控指标

| 指标 | 类型 | 说明 |
|------|------|------|
| `af_doc_extraction_total{mime_type, status}` | counter | 解析总量 |
| `af_doc_extraction_duration_seconds{mime_type}` | histogram | 解析耗时 |
| `af_doc_extraction_pages_total{mime_type}` | counter | 解析页数 |
| `af_doc_queue_length` | gauge | 待处理队列长度 |
| `af_doc_retry_total{mime_type}` | counter | 重试次数 |

---

## 与现有文档的衔接

- **文件上传端到端一致性** → [02-architecture.md](02-architecture.md) §文件上传端到端一致性
- **文件处理流水线** → [39-file-pipeline-design.md](39-file-pipeline-design.md)
- **Temp 桶安全策略** → [12-security-audit.md](12-security-audit.md) §敏感文件临时存储安全
- **数据归档策略** → [22-data-archiving.md](22-data-archiving.md)
- **P0 裁剪** → [34-p0-delivery-spec.md](34-p0-delivery-spec.md) §文档解析 Worker
