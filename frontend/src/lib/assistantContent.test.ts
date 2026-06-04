import { describe, expect, it } from 'vitest'
import { segmentAssistantContent } from './assistantContent'

describe('segmentAssistantContent', () => {
  it('splits closed html fences', () => {
    const parts = segmentAssistantContent(
      'title\n\n```html\n<section>A</section>\n```\n',
    )
    expect(parts).toHaveLength(2)
    expect(parts[0].kind).toBe('text')
    expect(parts[0].kind === 'text' && parts[0].text.trim()).toBe('title')
    expect(parts[1]).toMatchObject({
      kind: 'code',
      lang: 'html',
      code: '<section>A</section>',
    })
  })

  it('splits unclosed html fences at end of message', () => {
    const parts = segmentAssistantContent(
      '📋 HTML 第 1 段\n\n```html\n<!DOCTYPE html>\n<html lang="zh-CN">',
    )
    expect(parts).toHaveLength(2)
    expect(parts[0].kind).toBe('text')
    expect(parts[1]).toMatchObject({
      kind: 'code',
      lang: 'html',
    })
    expect(parts[1].kind === 'code' && parts[1].code).toContain('<!DOCTYPE html>')
  })
})
