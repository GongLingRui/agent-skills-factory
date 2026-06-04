/** Cryptographically-safe(ish) message ID generation.
 *
 * Falls back to a high-entropy timestamp-based ID when `crypto.randomUUID`
 * is unavailable (e.g. non-secure contexts).
 */
export function generateMsgId(prefix: string): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return `${prefix}_${crypto.randomUUID()}`
  }
  const rand = Math.random().toString(36).slice(2, 10)
  return `${prefix}_${Date.now()}_${rand}`
}
