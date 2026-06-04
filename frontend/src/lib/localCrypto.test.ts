import { describe, expect, it } from 'vitest'

import {
  aesGcmDecryptUtf8,
  aesGcmEncryptUtf8,
  canUseSubtleCrypto,
  deriveWidgetStorageKey,
} from '@/lib/localCrypto'

describe('localCrypto', () => {
  it('roundtrips utf8 with PBKDF2-derived key', async () => {
    if (!canUseSubtleCrypto()) {
      return
    }
    const sampleHash =
      'a'.repeat(64)
    const key = await deriveWidgetStorageKey(sampleHash)
    const enc = await aesGcmEncryptUtf8(key, '{"hello":"世界"}')
    const out = await aesGcmDecryptUtf8(key, enc)
    expect(out).toBe('{"hello":"世界"}')
  })
})
