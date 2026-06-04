/**
 * Optional IndexedDB encryption (docs/11-chat-widget.md, prd.md §10.3).
 * PBKDF2(SHA-256) + AES-GCM-256; IKM = server `user_id_hash` (hex).
 */

const PBKDF2_SALT_UTF8 = 'agent-factory.widget.idb.v1'
const PBKDF2_ITERATIONS = 100_000

export function canUseSubtleCrypto(): boolean {
  return typeof globalThis.crypto !== 'undefined' && !!globalThis.crypto.subtle
}

function hexToBytes(hex: string): Uint8Array {
  const t = hex.trim().toLowerCase()
  if (t.length % 2 !== 0 || !/^[0-9a-f]+$/.test(t)) {
    throw new Error('user_id_hash 格式无效')
  }
  const out = new Uint8Array(t.length / 2)
  for (let i = 0; i < out.length; i++) {
    out[i] = parseInt(t.slice(i * 2, i * 2 + 2), 16)
  }
  return out
}

function u8ToB64(u8: Uint8Array): string {
  let bin = ''
  u8.forEach((b) => {
    bin += String.fromCharCode(b)
  })
  return btoa(bin)
}

function b64ToU8(b64: string): Uint8Array {
  const bin = atob(b64)
  const out = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) {
    out[i] = bin.charCodeAt(i)
  }
  return out
}

/**
 * Derive AES-GCM key from portal-stable user_id_hash (64-char hex).
 */
export async function deriveWidgetStorageKey(
  userIdHashHex: string,
): Promise<CryptoKey> {
  const ikm = hexToBytes(userIdHashHex) as BufferSource
  const baseKey = await crypto.subtle.importKey(
    'raw',
    ikm,
    'PBKDF2',
    false,
    ['deriveKey'],
  )
  const salt = new TextEncoder().encode(PBKDF2_SALT_UTF8)
  return crypto.subtle.deriveKey(
    {
      name: 'PBKDF2',
      salt,
      iterations: PBKDF2_ITERATIONS,
      hash: 'SHA-256',
    },
    baseKey,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt'],
  )
}

export async function aesGcmEncryptUtf8(
  key: CryptoKey,
  plaintext: string,
): Promise<string> {
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const data = new TextEncoder().encode(plaintext)
  const ct = new Uint8Array(
    await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, data),
  )
  const pack = new Uint8Array(iv.length + ct.length)
  pack.set(iv)
  pack.set(ct, iv.length)
  return u8ToB64(pack)
}

export async function aesGcmDecryptUtf8(
  key: CryptoKey,
  envelopeB64: string,
): Promise<string> {
  const raw = b64ToU8(envelopeB64)
  if (raw.length < 13) {
    throw new Error('密文无效')
  }
  const iv = raw.slice(0, 12)
  const ct = raw.slice(12)
  const pt = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv },
    key,
    ct,
  )
  return new TextDecoder().decode(pt)
}
