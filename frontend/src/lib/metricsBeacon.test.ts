import { describe, expect, it } from 'vitest'
import { serializeFrontendMetric } from './metricsBeacon'

describe('serializeFrontendMetric', () => {
  it('includes event_type and optional fields', () => {
    const s = serializeFrontendMetric({
      agentId: 'a1',
      eventType: 'widget_ready',
      durationMs: 42,
      payload: { k: 1 },
    })
    const o = JSON.parse(s) as Record<string, unknown>
    expect(o.event_type).toBe('widget_ready')
    expect(o.agent_id).toBe('a1')
    expect(o.duration_ms).toBe(42)
    expect(o.payload).toEqual({ k: 1 })
  })

  it('omits undefined optional keys', () => {
    const s = serializeFrontendMetric({ eventType: 'ping' })
    const o = JSON.parse(s) as Record<string, unknown>
    expect(Object.keys(o).sort()).toEqual(['event_type'])
    expect(o.event_type).toBe('ping')
  })
})
