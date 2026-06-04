import { useEffect, useState, type DragEvent } from 'react'
import type { AgentItem } from '@/api/agents'
import { reorderByIndex } from '@/lib/reorderFavorites'

interface FavoritesReorderModalProps {
  open: boolean
  onClose: () => void
  favoriteIds: string[]
  agents: AgentItem[]
  onSave: (orderedIds: string[]) => void
}

export default function FavoritesReorderModal({
  open,
  onClose,
  favoriteIds,
  agents,
  onSave,
}: FavoritesReorderModalProps) {
  const [order, setOrder] = useState<string[]>([])

  useEffect(() => {
    if (!open) {
      return
    }
    let cancelled = false
    queueMicrotask(() => {
      if (!cancelled) {
        setOrder([...favoriteIds])
      }
    })
    return () => {
      cancelled = true
    }
  }, [open, favoriteIds])

  if (!open) return null

  const nameOf = (id: string) => agents.find((a) => a.id === id)?.name || id

  const onDragStart = (idx: number) => (e: DragEvent) => {
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', String(idx))
  }

  const onDragOver = (e: DragEvent) => {
    e.preventDefault()
  }

  const onDrop = (toIdx: number) => (e: DragEvent) => {
    e.preventDefault()
    const from = parseInt(e.dataTransfer.getData('text/plain'), 10)
    if (Number.isNaN(from)) return
    setOrder((prev) => reorderByIndex(prev, from, toIdx))
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
      onKeyDown={(e) => {
        if (e.key === 'Escape') onClose()
      }}
      role="presentation"
    >
      <div className="bg-white rounded-lg shadow-xl max-w-md w-full p-4">
        <h2 className="text-sm font-semibold mb-2">拖拽调整收藏顺序</h2>
        <p className="text-xs text-gray-600 mb-3">
          将条目拖到目标位置；保存后顶栏下拉中的「收藏」分区顺序会更新。
        </p>
        <ul className="border rounded divide-y max-h-64 overflow-y-auto mb-3">
          {order.map((id, idx) => (
            <li
              key={id}
              draggable
              onDragStart={onDragStart(idx)}
              onDragOver={onDragOver}
              onDrop={onDrop(idx)}
              className="px-3 py-2 text-sm cursor-grab active:cursor-grabbing hover:bg-gray-50 flex justify-between gap-2"
            >
              <span className="truncate">{nameOf(id)}</span>
              <span className="text-gray-400 shrink-0">⋮⋮</span>
            </li>
          ))}
        </ul>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            className="px-3 py-1.5 text-sm border rounded"
            onClick={onClose}
          >
            取消
          </button>
          <button
            type="button"
            className="px-3 py-1.5 text-sm rounded bg-primary-600 text-white"
            onClick={() => {
              onSave(order)
              onClose()
            }}
          >
            保存
          </button>
        </div>
      </div>
    </div>
  )
}
