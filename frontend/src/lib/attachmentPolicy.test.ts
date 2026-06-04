import { describe, expect, it } from 'vitest'
import {
  attachmentInputAccept,
  isAttachmentUploadAllowed,
  sniffMimeMagic,
  validateLocalAttachment,
} from './attachmentPolicy'

describe('isAttachmentUploadAllowed', () => {
  it('defaults to true when policy missing', () => {
    expect(isAttachmentUploadAllowed(undefined)).toBe(true)
  })
  it('is false when explicitly disabled', () => {
    expect(isAttachmentUploadAllowed({ enabled: false })).toBe(false)
  })
})

describe('attachmentInputAccept', () => {
  it('joins accept tokens', () => {
    expect(attachmentInputAccept({ accept: ['.pdf', 'image/*'] })).toBe('.pdf,image/*')
  })
})

describe('sniffMimeMagic', () => {
  it('detects pdf png mz', () => {
    const pdf = new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d])
    expect(sniffMimeMagic(pdf)).toBe('application/pdf')
    const png = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])
    expect(sniffMimeMagic(png)).toBe('image/png')
    const mz = new Uint8Array([0x4d, 0x5a, 0, 0])
    expect(sniffMimeMagic(mz)).toBe('application/x-msdownload')
    expect(sniffMimeMagic(new Uint8Array(0))).toBe(null)
  })
})

describe('validateLocalAttachment', () => {
  it('rejects when disabled', async () => {
    const f = new File([new Uint8Array([1])], 'a.pdf', { type: 'application/pdf' })
    const r = await validateLocalAttachment(f, { enabled: false })
    expect(r.ok).toBe(false)
  })

  it('respects max_size_mb', async () => {
    const f = new File([new Uint8Array(2 * 1024 * 1024)], 'big.bin', {
      type: 'application/octet-stream',
    })
    const r = await validateLocalAttachment(f, { max_size_mb: 1 })
    expect(r.ok).toBe(false)
  })

  it('allows by extension when octet-stream', async () => {
    const f = new File([new Uint8Array([1])], 'x.PDF', {
      type: 'application/octet-stream',
    })
    const r = await validateLocalAttachment(f, { accept: ['.pdf'] })
    expect(r.ok).toBe(true)
  })

  it('allows image/*', async () => {
    const f = new File([new Uint8Array([1])], 'p.png', { type: 'image/png' })
    const r = await validateLocalAttachment(f, { accept: ['image/*'] })
    expect(r.ok).toBe(true)
  })

  it('refines octet-stream to pdf via magic for accept', async () => {
    const body = new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d, 0x31, 0x2e, 0x34, 0x0a])
    const f = new File([body], 'a.pdf', { type: 'application/octet-stream' })
    const r = await validateLocalAttachment(f, { accept: ['application/pdf'] })
    expect(r.ok).toBe(true)
  })

  it('rejects pdf filename with png magic', async () => {
    const body = new Uint8Array([
      0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 0, 0, 0, 0, 0,
    ])
    const f = new File([body], 'disguise.pdf', { type: 'application/pdf' })
    const r = await validateLocalAttachment(f, undefined)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.message).toBe('文件内容与类型不一致')
  })

  it('rejects pe disguised as pdf', async () => {
    const body = new Uint8Array([0x4d, 0x5a, 0x90, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    const f = new File([body], 'trojan.pdf', { type: 'application/octet-stream' })
    const r = await validateLocalAttachment(f, undefined)
    expect(r.ok).toBe(false)
  })
})
