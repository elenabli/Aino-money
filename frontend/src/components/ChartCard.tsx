import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip as RTooltip,
  XAxis,
  YAxis,
} from 'recharts'

export interface ChartSpec {
  kind: 'line' | 'bar' | 'donut'
  title: string
  labels: string[]
  values?: number[]
  values2?: number[]
  series_names?: [string, string]
  series?: { name: string; data: number[] }[]
  unit?: 'eur' | 'pct'
  secondary?: { label: string; value: number; max: number }
}

const COLORS = ['#007a4d', '#3fae6a', '#ffb03a', '#e0654a', '#5b7ea8', '#8f6bb8']

function Donut({ chart }: { chart: ChartSpec }) {
  const isPct = chart.unit === 'pct'
  const rawValues = chart.values ?? []
  const total = isPct ? 100 : rawValues.reduce((a, b) => a + b, 0) || 1
  const data = chart.labels.map((label, i) => {
    const v = rawValues[i] ?? 0
    return { name: label, value: v, share: Math.round((v / total) * 100) }
  })
  return (
    <div className="donut-wrap">
      <div className="donut-pie">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              nameKey="name"
              innerRadius="58%"
              outerRadius="92%"
              paddingAngle={2}
              strokeWidth={0}
            >
              {data.map((_, i) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} />
              ))}
            </Pie>
            <RTooltip
              formatter={(v) => (isPct ? `${Number(v).toFixed(1)}%` : `${Number(v).toFixed(2)} €`)}
              contentStyle={{ borderRadius: 10, fontSize: 12 }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="donut-legend">
        {data.map((d, i) => (
          <div key={i} className="legend-row">
            <span className="legend-dot" style={{ background: COLORS[i % COLORS.length] }} />
            <span className="legend-name">{d.name}</span>
            <span className="legend-value">
              {isPct ? `${d.value.toFixed(1)}%` : `${d.value.toFixed(0)} €`}
              <em>{d.share}%</em>
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

function Secondary({ s }: { s: NonNullable<ChartSpec['secondary']> }) {
  const pct = Math.min(100, Math.round((s.value / s.max) * 100))
  return (
    <div className="secondary">
      <div className="secondary-row">
        <span>{s.label}</span>
        <strong>
          {s.value}/{s.max}
        </strong>
      </div>
      <div className="secondary-track">
        <div className="secondary-fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

const shortEur = (v: unknown) => {
  const n = Number(v ?? 0)
  return n >= 100 ? `${Math.round(n)}` : `${n.toFixed(1)}`
}

export function ChartCard({ chart }: { chart: ChartSpec }) {
  const data =
    chart.kind === 'line' && chart.series
      ? chart.labels.map((label, i) => {
          const row: Record<string, string | number> = { month: label }
          chart.series!.forEach((s) => (row[s.name] = s.data[i] ?? 0))
          return row
        })
      : chart.labels.map((label, i) => ({
          name: label,
          value: chart.values?.[i] ?? 0,
          value2: chart.values2?.[i] ?? 0,
        }))

  return (
    <div className="chart-card">
      <div className="chart-title">{chart.title}</div>
      <div className="chart-body">
        {chart.kind === 'line' && chart.series ? (
          <ResponsiveContainer width="100%" height={190}>
            <LineChart data={data} margin={{ top: 5, right: 6, left: -14, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5ebe7" />
              <XAxis dataKey="month" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} unit="€" width={50} />
              <RTooltip
                formatter={(v) => `${Number(v).toFixed(2)} €`}
                contentStyle={{ borderRadius: 10, fontSize: 12 }}
              />
              <Legend wrapperStyle={{ fontSize: 10 }} />
              {chart.series.map((s, i) => (
                <Line
                  key={s.name}
                  type="monotone"
                  dataKey={s.name}
                  stroke={COLORS[i % COLORS.length]}
                  strokeWidth={2}
                  dot={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        ) : chart.kind === 'donut' ? (
          <Donut chart={chart} />
        ) : chart.values2 ? (
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={data} margin={{ top: 16, right: 6, left: -14, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5ebe7" vertical={false} />
              <XAxis dataKey="name" tick={{ fontSize: 10 }} interval={0} />
              <YAxis tick={{ fontSize: 10 }} unit="€" width={50} />
              <RTooltip
                formatter={(v) => `${Number(v).toFixed(0)} €`}
                contentStyle={{ borderRadius: 10, fontSize: 12 }}
              />
              <Legend wrapperStyle={{ fontSize: 10 }} />
              <Bar dataKey="value" name={chart.series_names?.[0] ?? 'You'} fill="#007a4d" radius={[5, 5, 0, 0]}>
                <LabelList dataKey="value" position="top" formatter={shortEur} style={{ fontSize: 9, fill: '#00603c', fontWeight: 700 }} />
              </Bar>
              <Bar dataKey="value2" name={chart.series_names?.[1] ?? 'Average'} fill="#c3d4cb" radius={[5, 5, 0, 0]}>
                <LabelList dataKey="value2" position="top" formatter={shortEur} style={{ fontSize: 9, fill: '#7a8a82' }} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <ResponsiveContainer width="100%" height={190}>
            <BarChart data={data} margin={{ top: 16, right: 6, left: -14, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5ebe7" vertical={false} />
              <XAxis dataKey="name" tick={{ fontSize: 10 }} interval={0} />
              <YAxis tick={{ fontSize: 10 }} unit="€" width={50} />
              <RTooltip
                formatter={(v) => `${Number(v).toFixed(2)} €`}
                contentStyle={{ borderRadius: 10, fontSize: 12 }}
              />
              <Bar dataKey="value" fill="#007a4d" radius={[5, 5, 0, 0]}>
                <LabelList dataKey="value" position="top" formatter={shortEur} style={{ fontSize: 9, fill: '#00603c', fontWeight: 700 }} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
      {chart.secondary && <Secondary s={chart.secondary} />}
    </div>
  )
}
