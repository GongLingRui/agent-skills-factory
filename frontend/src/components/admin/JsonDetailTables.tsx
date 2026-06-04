const FIELD_LABELS: Record<string, string> = {
  id: 'ID',
  version: '版本',
  name: '名称',
  description: '描述',
  when_to_use: '适用场景',
  owner: '负责人',
  risk_tier: '风险等级',
  skill_package_hash: '包哈希',
  package_metadata: '包元数据',
  storage_path: '存储路径',
  status: '状态',
  created_at: '创建时间',
  updated_at: '更新时间',
  mounted_agents: '已挂载 Agent',
  versions: '版本列表',
  input_schema: '输入 Schema',
  output_schema: '输出 Schema',
  permission_required: '所需权限',
  timeout_seconds: '超时（秒）',
  rate_limit: '速率限制',
  implementation: '实现配置',
  run_id: 'Run ID',
  session_id: '会话 ID',
  timestamp: '时间',
  level: '级别',
  user_id_hash: '用户哈希',
  agent_id: 'Agent',
  department: '部门',
  tool_calls: '工具调用',
  tool_calls_so_far: '工具调用记录',
  token_count: 'Token 用量',
  cost: '成本',
  error_code: '错误码',
  retrieval_ids: '检索 ID',
  prompt_summary: 'Prompt 摘要',
  full_prompt: '完整 Prompt',
  full_output: '完整输出',
  checkpoint_id: 'Checkpoint ID',
  turn_number: '轮次',
  tool_id: '工具 ID',
  type: '类型',
  function: '函数',
}

function labelFor(key: string): string {
  return FIELD_LABELS[key] ?? key
}

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === 'object' && !Array.isArray(v)
}

function isObjectArray(arr: unknown[]): arr is Record<string, unknown>[] {
  return arr.length > 0 && arr.every((item) => isPlainObject(item))
}

function formatScalar(v: unknown): string {
  if (v == null || v === '') return '—'
  if (typeof v === 'boolean') return v ? '是' : '否'
  if (typeof v === 'number') return v.toLocaleString('zh-CN')
  if (typeof v === 'string') {
    if (v.length > 500) return `${v.slice(0, 497)}…`
    return v
  }
  return String(v)
}

function formatCell(v: unknown): string {
  if (v == null || v === '') return '—'
  if (typeof v === 'object') {
    const s = JSON.stringify(v)
    return s.length > 200 ? `${s.slice(0, 197)}…` : s
  }
  return formatScalar(v)
}

function collectKeys(rows: Record<string, unknown>[]): string[] {
  const keys = new Set<string>()
  for (const row of rows) {
    for (const k of Object.keys(row)) keys.add(k)
  }
  return [...keys]
}

const tableWrap =
  'overflow-x-auto rounded-lg border border-slate-200/80 dark:border-slate-600'
const tableClass = 'min-w-full text-xs'
const thClass =
  'px-3 py-2 font-semibold text-left text-slate-500 border-b border-slate-200 dark:border-slate-600'
const tdClass =
  'px-3 py-2 border-b border-slate-100 dark:border-slate-700/80 align-top'
const tdValueClass = `${tdClass} break-words max-w-md`

function KeyValueTable({ rows }: { rows: Array<[string, unknown]> }) {
  if (rows.length === 0) return null
  return (
    <div className={tableWrap}>
      <table className={tableClass}>
        <thead>
          <tr>
            <th className={thClass}>字段</th>
            <th className={thClass}>值</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([key, value]) => (
            <tr key={key}>
              <td className={`${tdClass} font-medium whitespace-nowrap`}>
                {labelFor(key)}
              </td>
              <td className={`${tdValueClass} font-mono`}>
                {formatScalar(value)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ObjectArrayTable({
  title,
  rows,
}: {
  title: string
  rows: Record<string, unknown>[]
}) {
  const keys = collectKeys(rows)
  if (keys.length === 0) {
    return (
      <p className="text-xs text-slate-500">
        {labelFor(title)}：暂无数据
      </p>
    )
  }
  return (
    <section className="space-y-1.5">
      <h4 className="text-xs font-semibold text-slate-600 dark:text-slate-400">
        {labelFor(title)}
        <span className="ml-1.5 font-normal text-slate-400">
          （{rows.length} 条）
        </span>
      </h4>
      <div className={tableWrap}>
        <table className={tableClass}>
          <thead>
            <tr>
              {keys.map((k) => (
                <th key={k} className={thClass}>
                  {labelFor(k)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                {keys.map((k) => (
                  <td key={k} className={`${tdValueClass} font-mono`}>
                    {formatCell(row[k])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function PrimitiveArrayTable({
  title,
  values,
}: {
  title: string
  values: unknown[]
}) {
  if (values.length === 0) {
    return (
      <p className="text-xs text-slate-500">
        {labelFor(title)}：暂无数据
      </p>
    )
  }
  return (
    <section className="space-y-1.5">
      <h4 className="text-xs font-semibold text-slate-600 dark:text-slate-400">
        {labelFor(title)}
        <span className="ml-1.5 font-normal text-slate-400">
          （{values.length} 项）
        </span>
      </h4>
      <div className={tableWrap}>
        <table className={tableClass}>
          <thead>
            <tr>
              <th className={thClass}>序号</th>
              <th className={thClass}>值</th>
            </tr>
          </thead>
          <tbody>
            {values.map((v, i) => (
              <tr key={i}>
                <td className={`${tdClass} whitespace-nowrap`}>{i + 1}</td>
                <td className={`${tdValueClass} font-mono`}>
                  {formatCell(v)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export interface JsonDetailTablesProps {
  data: unknown
  excludeKeys?: string[]
  className?: string
}

export function JsonDetailTables({
  data,
  excludeKeys = [],
  className = '',
}: JsonDetailTablesProps) {
  if (typeof data === 'string') {
    return <p className="text-sm text-slate-500">{data}</p>
  }
  if (data == null) {
    return <p className="text-sm text-slate-500">暂无数据</p>
  }
  if (!isPlainObject(data)) {
    return (
      <p className="text-sm font-mono text-slate-700 dark:text-slate-300">
        {formatScalar(data)}
      </p>
    )
  }

  const excluded = new Set(excludeKeys)
  const scalars: Array<[string, unknown]> = []
  const objectSections: Array<[string, Record<string, unknown>]> = []
  const arraySections: Array<[string, unknown[]]> = []

  for (const [key, value] of Object.entries(data)) {
    if (excluded.has(key)) continue
    if (value == null || typeof value !== 'object') {
      scalars.push([key, value])
    } else if (Array.isArray(value)) {
      arraySections.push([key, value])
    } else if (isPlainObject(value)) {
      objectSections.push([key, value])
    } else {
      scalars.push([key, value])
    }
  }

  if (
    scalars.length === 0 &&
    objectSections.length === 0 &&
    arraySections.length === 0
  ) {
    return <p className="text-sm text-slate-500">暂无更多字段</p>
  }

  return (
    <div className={`space-y-4 ${className}`.trim()}>
      <KeyValueTable rows={scalars} />
      {arraySections.map(([key, arr]) =>
        isObjectArray(arr) ? (
          <ObjectArrayTable key={key} title={key} rows={arr} />
        ) : (
          <PrimitiveArrayTable key={key} title={key} values={arr} />
        ),
      )}
      {objectSections.map(([key, obj]) => (
        <section key={key} className="space-y-2">
          <h4 className="text-xs font-semibold text-slate-600 dark:text-slate-400">
            {labelFor(key)}
          </h4>
          <JsonDetailTables data={obj} />
        </section>
      ))}
    </div>
  )
}
