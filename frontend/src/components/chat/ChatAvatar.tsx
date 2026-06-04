interface ChatAvatarProps {
  label: string
  imageUrl?: string
  variant: 'agent' | 'user'
  className?: string
}

/** 对话流中的圆形头像：助手用配置图或首字；用户侧固定「我」。 */
export default function ChatAvatar({
  label,
  imageUrl,
  variant,
  className = '',
}: ChatAvatarProps) {
  const base =
    'shrink-0 w-9 h-9 rounded-xl flex items-center justify-center text-xs font-bold shadow-sm ring-2 ring-white overflow-hidden'

  if (imageUrl) {
    return (
      <img
        src={imageUrl}
        alt=""
        className={`${base} object-cover bg-slate-100 ${className}`}
      />
    )
  }

  if (variant === 'user') {
    return (
      <div
        className={`${base} bg-gradient-to-br from-slate-600 to-slate-800 text-white ${className}`}
        aria-hidden
      >
        我
      </div>
    )
  }

  const letter = label.trim()[0] || 'A'
  return (
    <div
      className={`${base} bg-gradient-to-br from-primary-600 to-primary-800 text-white ${className}`}
      aria-hidden
    >
      {letter}
    </div>
  )
}
