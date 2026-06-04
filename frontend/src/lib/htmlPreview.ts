/** Detect and prepare assistant HTML for sandboxed iframe preview. */

export function isHtmlLikeSegment(lang: string, code: string): boolean {
  const l = lang.trim().toLowerCase()
  if (l === 'html' || l === 'htm') return true
  const t = code.trimStart()
  return (
    /^<!DOCTYPE\s+html/i.test(t) ||
    /^<html[\s>]/i.test(t) ||
    /^<head[\s>]/i.test(t) ||
    /^<section[\s>]/i.test(t) ||
    /^<main[\s>]/i.test(t)
  )
}

/** Strip document wrapper from continuation segments (P6+). */
function stripDeckContinuationWrapper(chunk: string): string {
  let t = chunk.trim()
  t = t.replace(/^<!DOCTYPE[^>]*>\s*/i, '')
  t = t.replace(/^<html[^>]*>\s*/i, '')
  t = t.replace(/^<head[\s\S]*?<\/head>\s*/i, '')
  t = t.replace(/^<body[^>]*>\s*/i, '')
  t = t.replace(/\s*<\/body>\s*<\/html>\s*$/i, '')
  return t.trim()
}

/** Insert continuation HTML before closing body/html tags when present. */
function appendDeckContinuation(doc: string, chunk: string): string {
  const piece = stripDeckContinuationWrapper(chunk)
  if (!piece) return doc
  if (/<\/body>/i.test(doc)) {
    return doc.replace(/<\/body>/i, `${piece}\n</body>`)
  }
  if (/<\/html>/i.test(doc)) {
    return doc.replace(/<\/html>/i, `${piece}\n</html>`)
  }
  return `${doc.trim()}\n${piece}`
}

/** Join segmented deck HTML (STATE_3_GEN) into one document string. */
export function mergeHtmlDeckSegments(segments: string[]): string {
  const cleaned = segments.map((s) => s.trim()).filter(Boolean)
  if (!cleaned.length) return ''
  let doc = cleaned[0]
  for (let i = 1; i < cleaned.length; i += 1) {
    doc = appendDeckContinuation(doc, cleaned[i])
  }
  return doc
}

/**
 * Ensure iframe srcDoc is a document. Fragments (mid-deck sections) pass through
 * as-is so the parent can merge multiple assistant turns.
 */
export function prepareHtmlDocument(raw: string): string {
  const t = raw.trim()
  if (!t) return ''
  if (/^<!DOCTYPE\s+html/i.test(t) || /^<html[\s>]/i.test(t)) {
    return t
  }
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Preview</title>
</head>
<body>
${t}
</body>
</html>`
}

/** True when merged segments form a runnable deck (has closing html). */
export function isCompleteHtmlDocument(html: string): boolean {
  const t = html.trim().toLowerCase()
  return t.includes('</html>') && (t.startsWith('<!doctype') || t.includes('<html'))
}

function collectFencedBlocks(raw: string): Array<{ lang: string; code: string }> {
  const blocks: Array<{ lang: string; code: string }> = []
  const closedRe = /```(\w*)\s*(?:\r?\n)([\s\S]*?)```/g
  let m: RegExpExecArray | null
  let last = 0
  while ((m = closedRe.exec(raw)) !== null) {
    blocks.push({ lang: m[1] || '', code: m[2].trim() })
    last = closedRe.lastIndex
  }
  if (last < raw.length) {
    const tail = raw.slice(last)
    const unclosed = tail.match(/^([\s\S]*?)```(\w*)\s*(?:\r?\n)?([\s\S]+)$/)
    if (unclosed) {
      blocks.push({ lang: unclosed[2] || '', code: unclosed[3].trim() })
    }
  }
  return blocks
}

export function extractHtmlSegmentsFromText(raw: string): string[] {
  const segments: string[] = []
  for (const { lang, code } of collectFencedBlocks(raw)) {
    if (code && isHtmlLikeSegment(lang, code)) {
      segments.push(code)
    }
  }
  return segments
}
