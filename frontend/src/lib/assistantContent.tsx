/**
 * Strip reasoning markup and split assistant text into prose vs fenced code
 * for clearer Widget rendering.
 *
 * Patterns align with ``backend/src/agent_factory/core/model_output_parse.py``.
 */

import type { ContentBlock } from '@/types/message'

const REASONING_INNER = [
  /<think\b[^>]*>([\s\S]*?)<\/redacted_thinking>/gi,
  /<thinking>([\s\S]*?)<\/thinking>/gi,
  /<think>([\s\S]*?)<\/redacted_thinking>/gi,
  /<think\b[^>]*>([\s\S]*?)<\/think>/gi,
]

const MINIMAX_TOOL_BLOCK = /<minimax:tool_call>[\s\S]*?<\/minimax:tool_call>/gi
const BRACKET_TOOL_BLOCK = /\[TOOL_CALL\][\s\S]*?\[\/TOOL_CALL\]/gi
const ANGLE_TOOL_BLOCK = /<tool_call\b[^>]*>[\s\S]*?<\/tool_call\s*>/gi

export interface ReasoningBlock {
  /** Stable key for React list */
  key: string
  body: string
}

let _reasonKeySeq = 0

/** Extract chain-of-thought blocks for collapsible UI (main prose still in ``raw``). */
export function extractReasoningBlocks(raw: string): ReasoningBlock[] {
  const blocks: ReasoningBlock[] = []
  for (const pattern of REASONING_INNER) {
    const re = new RegExp(pattern.source, pattern.flags)
    let m: RegExpExecArray | null
    while ((m = re.exec(raw)) !== null) {
      const body = (m[1] || '').trim()
      if (body) {
        _reasonKeySeq += 1
        blocks.push({ key: `r_${_reasonKeySeq}`, body })
      }
    }
  }
  return blocks
}

/** Strip reasoning + embedded tool pseudo-markup from assistant markdown. */
export function stripReasoningAndToolNoise(raw: string): string {
  let t = raw
  for (const re of REASONING_INNER) {
    t = t.replace(re, '')
  }
  t = t.replace(MINIMAX_TOOL_BLOCK, '')
  t = t.replace(BRACKET_TOOL_BLOCK, '')
  t = t.replace(ANGLE_TOOL_BLOCK, '')
  return t.replace(/\n{3,}/g, '\n\n').trim()
}

/** Visible assistant copy without chain-of-thought blocks. */
export function stripReasoningForDisplay(raw: string): string {
  return stripReasoningAndToolNoise(raw)
}

export type AssistantSegment =
  | { kind: 'text'; text: string }
  | { kind: 'code'; lang: string; code: string }

/** Closed fence; lang may be empty; newline after lang is optional for some models. */
const CLOSED_FENCE_RE = /```(\w*)\s*(?:\r?\n)([\s\S]*?)```/g
/** Trailing fence without closing ``` (common for long streamed HTML decks). */
const UNCLOSED_FENCE_RE = /^([\s\S]*?)```(\w*)\s*(?:\r?\n)?([\s\S]+)$/

/** Split markdown ``` fences so JSON/code can use monospace styling. */
export function segmentAssistantContent(raw: string): AssistantSegment[] {
  const text = stripReasoningForDisplay(raw)
  if (!text.trim()) return [{ kind: 'text', text: '' }]

  const parts: AssistantSegment[] = []
  let last = 0
  let m: RegExpExecArray | null
  const re = new RegExp(CLOSED_FENCE_RE.source, CLOSED_FENCE_RE.flags)
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) {
      const chunk = text.slice(last, m.index)
      if (chunk.trim()) parts.push({ kind: 'text', text: chunk })
    }
    parts.push({
      kind: 'code',
      lang: m[1] || 'text',
      code: m[2].trim(),
    })
    last = re.lastIndex
  }
  if (last < text.length) {
    const chunk = text.slice(last)
    const unclosed = chunk.match(UNCLOSED_FENCE_RE)
    if (unclosed) {
      const [, before, lang, code] = unclosed
      if (before.trim()) parts.push({ kind: 'text', text: before })
      if (code.trim()) {
        parts.push({ kind: 'code', lang: lang || 'text', code: code.trim() })
      }
    } else if (chunk.trim()) {
      parts.push({ kind: 'text', text: chunk })
    }
  }
  return parts.length ? parts : [{ kind: 'text', text }]
}

/**
 * Merge consecutive streamed ``text`` deltas and strip reasoning once per run.
 *
 * ``useChatStream`` appends each SSE text delta as its own block; rendering
 * those fragments with ReactMarkdown leaves reasoning tags split across
 * chunks so regex strip never matches, while
 * ``extractReasoningBlocks(message.content)`` still finds them — causing
 * duplicate reasoning (collapsible + raw body). Coalescing fixes that.
 */
export function coalesceTextBlocksForDisplay(
  blocks: ContentBlock[],
): ContentBlock[] {
  const out: ContentBlock[] = []
  let buf = ''
  const flush = () => {
    if (!buf) return
    const cleaned = stripReasoningForDisplay(buf)
    if (cleaned.trim()) {
      out.push({ kind: 'text', text: cleaned })
    }
    buf = ''
  }
  for (const b of blocks) {
    if (b.kind === 'text') {
      buf += b.text
    } else {
      flush()
      out.push(b)
    }
  }
  flush()
  return out
}
