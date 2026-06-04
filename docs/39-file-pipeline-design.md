# 39. 文件处理流水线设计

> 版本：v0.6 · 2026-05-06

---

## 完整文件生命周期

> 本文档描述文件从用户上传到清理的**完整业务流**；Doc Worker 的解析实现细节（沙箱、解析器、错误码）见 [24-document-parser-worker.md](24-document-parser-worker.md)。

```
用户选择文件
  ↓
前端预检（类型 / 大小 / 并发）
  ↓
前端计算文件 hash（sha256，用于秒传）
  ↓
POST /api/v1/upload（multipart/form-data，带 session cookie）
  ↓
后端接收 → 校验 mime 类型（魔数 + 扩展名）
  ↓
秒传检查：hash 是否已存在于 MinIO？
  ├─ 是 → 复用已有文件，返回已有 file_id
  └─ 否 → 直传 MinIO temp/ 桶
  ↓
写入 PostgreSQL file_uploads（状态=pending）
  ↓
投递 doc_worker 队列（Redis Stream）
  ↓
Doc Worker 解析 → 提取文本 → 上传 extracted_text 到 MinIO
  ↓
更新 PostgreSQL file_uploads（状态=extracted）
  ↓
模型调用 doc.extract(file_id) → Tool Gateway 返回已提取的文本
  ↓
会话结束 / 24h 后 → MinIO temp/ 桶自动清理（Lifecycle Rule）
```

---

## 文件元数据表（file_uploads）

```sql
CREATE TABLE file_uploads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(64) NOT NULL,
    user_id_hash VARCHAR(64) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    file_size BIGINT NOT NULL,
    mime_type VARCHAR(64) NOT NULL,
    sha256 VARCHAR(64) NOT NULL,
    storage_path VARCHAR(512) NOT NULL,        -- MinIO temp/ 路径
    extracted_text_path VARCHAR(512),           -- MinIO extracted/ 路径
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
        -- enum: pending / extracting / extracted / failed / expired
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '24 hours'
);

CREATE INDEX idx_file_uploads_session ON file_uploads(session_id);
CREATE INDEX idx_file_uploads_sha256 ON file_uploads(sha256);
CREATE INDEX idx_file_uploads_status ON file_uploads(status) WHERE status = 'pending';
CREATE INDEX idx_file_uploads_expires ON file_uploads(expires_at) WHERE status != 'expired';
```

---

## 秒传机制

```python
async def handle_upload(file_stream, filename, session_id, user_id_hash):
    # 1. 计算 sha256
    file_hash = await compute_sha256(file_stream)

    # 2. 检查秒传
    existing = await db.fetch_one(
        "SELECT id, storage_path, extracted_text_path, status FROM file_uploads WHERE sha256 = ?",
        file_hash
    )
    if existing and existing["status"] == "extracted":
        # 已有完全相同的文件且已解析完成
        new_id = generate_file_id()
        await db.execute(
            """INSERT INTO file_uploads (id, session_id, user_id_hash, file_name, file_size, mime_type,
                sha256, storage_path, extracted_text_path, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'extracted')""",
            new_id, session_id, user_id_hash, filename, file_size, mime_type,
            file_hash, existing["storage_path"], existing["extracted_text_path"]
        )
        return {"file_id": new_id, "status": "extracted", "dedup": True}

    # 3. 秒传状态机处理（同一 hash 的不同状态）
    if existing:
        if existing["status"] == "pending":
            # 文件正在解析中，返回同一 file_id，前端轮询等待
            return {"file_id": existing["id"], "status": "pending", "dedup": True}
        elif existing["status"] == "failed":
            # 之前解析失败，重新投递 doc_worker 队列，不重复上传 MinIO
            new_id = generate_file_id()
            await db.execute(
                """INSERT INTO file_uploads (id, session_id, user_id_hash, file_name, file_size, mime_type,
                    sha256, storage_path, extracted_text_path, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
                new_id, session_id, user_id_hash, filename, file_size, mime_type,
                file_hash, existing["storage_path"], existing["extracted_text_path"]
            )
            await enqueue_doc_worker(new_id)
            return {"file_id": new_id, "status": "pending", "dedup": False}
        elif existing["status"] == "expired":
            # 过期文件走全新上传流程（原文件可能已被 MinIO 清理）
            pass  # 继续执行下面的正常上传流程

    # 4. 正常上传流程
    storage_path = await minio.upload_stream("temp", generate_path(), file_stream)
    ...
```

---

## 异常处理

| 异常场景 | 处理 |
|---------|------|
| MinIO 有文件但 PG 无记录 | cron 扫描 MinIO temp/，清理 24h 前 orphan 对象 |
| PG 有记录但 MinIO 文件丢失 | doc.extract 返回 `FILE_NOT_FOUND`，模型自行处理 |
| 解析超时 | Doc Worker 标记 failed，前端提示"文件解析失败，请重试" |
| 格式不支持 | 上传阶段即拦截，返回 400 |
| 解析结果为空 | 标记 extracted 但 content=""，模型收到空文本提示 |

---

## 与现有文档的衔接

- **文档解析 Worker** → [24-document-parser-worker.md](24-document-parser-worker.md)
- **Temp 桶安全策略** → [12-security-audit.md](12-security-audit.md) §敏感文件临时存储安全
- **数据一致性** → [02-architecture.md](02-architecture.md) §文件上传端到端一致性
