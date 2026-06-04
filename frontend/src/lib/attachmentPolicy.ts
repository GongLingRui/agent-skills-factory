import type { AgentUIConfig } from '@/types/agent'

export type AttachmentPolicy = NonNullable<AgentUIConfig['attachments']>

const DEFAULT_MAX_MB = 10

/** First chunk for magic-byte sniffing (aligned with backend ``MAGIC_SNIFF_BYTES``). */
export const MAGIC_SNIFF_BYTES = 512

const OOXML_DOCX =
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
const OOXML_XLSX =
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
const OOXML_PPTX =
  'application/vnd.openxmlformats-officedocument.presentationml.presentation'

const ZIP_FAMILY = new Set<string>([
  'application/zip',
  OOXML_DOCX,
  OOXML_XLSX,
  OOXML_PPTX,
])

function bytesEq(head: Uint8Array, start: number, seq: readonly number[]): boolean {
  if (head.length < start + seq.length) return false
  for (let i = 0; i < seq.length; i++) {
    if (head[start + i] !== seq[i]) return false
  }
  return true
}

/** Best-effort MIME from leading bytes; ``null`` if unknown or too short. */
export function sniffMimeMagic(head: Uint8Array): string | null {
  if (head.length < 4) return null
  if (bytesEq(head, 0, [0x25, 0x50, 0x44, 0x46])) return 'application/pdf'
  if (bytesEq(head, 0, [0xff, 0xd8, 0xff])) return 'image/jpeg'
  if (bytesEq(head, 0, [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))
    return 'image/png'
  if (
    bytesEq(head, 0, [0x47, 0x49, 0x46, 0x38, 0x37, 0x61]) ||
    bytesEq(head, 0, [0x47, 0x49, 0x46, 0x38, 0x39, 0x61])
  ) {
    return 'image/gif'
  }
  if (
    head.length >= 12 &&
    bytesEq(head, 0, [0x52, 0x49, 0x46, 0x46]) &&
    bytesEq(head, 8, [0x57, 0x45, 0x42, 0x50])
  ) {
    return 'image/webp'
  }
  if (bytesEq(head, 0, [0x50, 0x4b, 0x03, 0x04])) return 'application/zip'
  if (head[0] === 0x4d && head[1] === 0x5a) return 'application/x-msdownload'
  return null
}

function mimeCompatible(declared: string, sniffed: string): boolean {
  const d = declared.toLowerCase()
  const s = sniffed.toLowerCase()
  if (d === s) return true
  if (ZIP_FAMILY.has(d) && ZIP_FAMILY.has(s)) return true
  if (
    (d === 'image/jpg' || d === 'image/jpeg') &&
    (s === 'image/jpg' || s === 'image/jpeg')
  ) {
    return true
  }
  return false
}

function executableDisguise(filename: string, sniffed: string | null): boolean {
  if (sniffed !== 'application/x-msdownload') return false
  const low = filename.toLowerCase()
  const safe = ['.exe', '.msi', '.dll', '.bat', '.cmd', '.scr']
  return !safe.some((s) => low.endsWith(s))
}

function extensionMagicConsistent(filename: string, sniffed: string | null): boolean {
  if (!sniffed) return true
  const low = filename.toLowerCase()
  if (low.endsWith('.pdf')) return sniffed === 'application/pdf'
  if (low.endsWith('.png')) return sniffed === 'image/png'
  if (low.endsWith('.jpg') || low.endsWith('.jpeg')) return sniffed === 'image/jpeg'
  if (low.endsWith('.gif')) return sniffed === 'image/gif'
  if (low.endsWith('.webp')) return sniffed === 'image/webp'
  if (low.endsWith('.docx')) return ZIP_FAMILY.has(sniffed)
  if (low.endsWith('.xlsx')) return ZIP_FAMILY.has(sniffed)
  if (low.endsWith('.pptx')) return ZIP_FAMILY.has(sniffed)
  return true
}

function matchesPattern(filename: string, mime: string, pattern: string): boolean {
  const p = pattern.trim()
  if (!p) return false
  const low = p.toLowerCase()
  if (low.startsWith('.')) {
    return filename.toLowerCase().endsWith(low)
  }
  if (low.includes('*') || low.includes('?')) {
    const main = mime.toLowerCase().split(';')[0]?.trim() ?? ''
    const escaped = low
      .replace(/[.+^${}()|[\]\\]/g, '\\$&')
      .replace(/\*/g, '.*')
      .replace(/\?/g, '.')
    const rx = new RegExp(`^${escaped}$`)
    return rx.test(main)
  }
  return mime.toLowerCase() === low
}

/** Whether the attachment button should be shown (default: enabled). */
export function isAttachmentUploadAllowed(policy: AttachmentPolicy | undefined): boolean {
  return policy?.enabled !== false
}

/** HTML ``accept`` attribute string when patterns are declared. */
export function attachmentInputAccept(policy: AttachmentPolicy | undefined): string | undefined {
  if (!policy?.accept?.length) return undefined
  const parts = policy.accept.map((x) => String(x).trim()).filter(Boolean)
  return parts.length ? parts.join(',') : undefined
}

/**
 * Client-side validation (size, accept, MIME magic) aligned with backend
 * ``attachment_policy.validate_upload_for_ui_config``.
 */
export async function validateLocalAttachment(
  file: File,
  policy: AttachmentPolicy | undefined,
): Promise<{ ok: true } | { ok: false; message: string }> {
  if (policy?.enabled === false) {
    return { ok: false, message: '该 Agent 未开启附件上传' }
  }
  const maxMb =
    typeof policy?.max_size_mb === 'number' && policy.max_size_mb > 0
      ? policy.max_size_mb
      : DEFAULT_MAX_MB
  const maxBytes = maxMb * 1024 * 1024
  if (file.size > maxBytes) {
    return { ok: false, message: `文件需不超过 ${maxMb}MB` }
  }

  let sniffed: string | null = null
  if (file.size > 0) {
    const slice = file.slice(0, Math.min(file.size, MAGIC_SNIFF_BYTES))
    const buf = new Uint8Array(await slice.arrayBuffer())
    sniffed = sniffMimeMagic(buf)
  }

  const declaredRaw = (file.type || '').trim().toLowerCase()
  const declared = declaredRaw || 'application/octet-stream'
  let effectiveMime = declared

  if (sniffed) {
    if (executableDisguise(file.name, sniffed)) {
      return { ok: false, message: '文件内容与类型不一致' }
    }
    if (!extensionMagicConsistent(file.name, sniffed)) {
      return { ok: false, message: '文件内容与类型不一致' }
    }
    if (
      declared === 'application/octet-stream' ||
      declared === 'binary/octet-stream' ||
      declared === ''
    ) {
      effectiveMime = sniffed
    } else if (!mimeCompatible(declared, sniffed)) {
      return { ok: false, message: '文件内容与类型不一致' }
    }
  }

  const accept = policy?.accept
  if (Array.isArray(accept) && accept.length > 0) {
    const patterns = accept.map((x) => String(x).trim()).filter(Boolean)
    if (patterns.length > 0) {
      const hit = patterns.some((pat) =>
        matchesPattern(file.name, effectiveMime, pat),
      )
      if (!hit) {
        return { ok: false, message: '不允许的文件类型' }
      }
    }
  }
  return { ok: true }
}
