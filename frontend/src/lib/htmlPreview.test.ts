import { describe, expect, it } from 'vitest'
import {
  extractHtmlSegmentsFromText,
  isCompleteHtmlDocument,
  isHtmlLikeSegment,
  mergeHtmlDeckSegments,
  prepareHtmlDocument,
} from './htmlPreview'

describe('htmlPreview', () => {
  it('detects html fences and doctype', () => {
    expect(isHtmlLikeSegment('html', '<!DOCTYPE html><html></html>')).toBe(true)
    expect(isHtmlLikeSegment('', '<section class="slide"></section>')).toBe(true)
    expect(isHtmlLikeSegment('json', '{"a":1}')).toBe(false)
  })

  it('wraps fragments', () => {
    const doc = prepareHtmlDocument('<section class="slide">A</section>')
    expect(doc).toContain('<!DOCTYPE html>')
    expect(doc).toContain('<section class="slide">A</section>')
  })

  it('merges deck segments', () => {
    const merged = mergeHtmlDeckSegments([
      '<!DOCTYPE html><html><head></head><body><main>',
      '<section>P2</section></main></body></html>',
    ])
    expect(merged).toContain('<section>P2</section>')
  })

  it('splices middle segments before closing body', () => {
    const merged = mergeHtmlDeckSegments([
      '<!DOCTYPE html><html><body><section>P1</section>',
      '<section>P6</section>',
    ])
    expect(merged).toContain('<section>P1</section>')
    expect(merged).toContain('<section>P6</section>')
    expect(merged.indexOf('P1')).toBeLessThan(merged.indexOf('P6'))
  })

  it('extracts html blocks from markdown', () => {
    const parts = extractHtmlSegmentsFromText(
      'intro\n\n```html\n<section>A</section>\n```\n',
    )
    expect(parts).toEqual(['<section>A</section>'])
  })

  it('extracts unclosed html fences (streamed deck segment)', () => {
    const parts = extractHtmlSegmentsFromText(
      '📋 HTML 第 1 段\n\n```html\n<!DOCTYPE html>\n<html><head></head><body>',
    )
    expect(parts).toHaveLength(1)
    expect(parts[0]).toContain('<!DOCTYPE html>')
  })

  it('detects complete documents', () => {
    expect(isCompleteHtmlDocument('<!DOCTYPE html><html></html>')).toBe(true)
    expect(isCompleteHtmlDocument('<section only')).toBe(false)
  })
})
