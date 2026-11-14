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
import type { ChartSpec } from '../api'

export type { ChartSpec }

const COLORS = ['#007a4d', '#f2a33a', '#5b7ea8', '#e0654a', '#3fae6a', '#8f6bb8', '#2a9d9d', '#c2557a']
const SHORT_LABELS: Record<string, string> = {
  Transportation: 'Transport', Entertainment: 'Leisure', Restaurants: 'Dining', 'Home & Tech': 'Home/Tech',
  'Safe to spend': 'Free', Unexpected: 'Irregular',
  'Household & care': 'Household', 'Dairy & eggs': 'Dairy', 'Fruit & veg': 'Fruit/veg', 'Snacks & sweets': 'Sweets',
  'Bread & grains': 'Bread', 'Ready meals': 'Ready', 'Household essential': 'Household',
}
const TOOLTIP = { borderRadius: 10, fontSize: 12, border: '1px solid #e3e9e5' }
const eur = (v: unknown, digits = 0) => `${Number(v ?? 0).toLocaleString('en-IE', { maximumFractionDigits: digits })} €`

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
            <Pie data={data} dataKey="value" nameKey="name" innerRadius="58%" outerRadius="92%"
              paddingAngle={2} strokeWidth={0} animationDuration={700}>
              {data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
            </Pie>
            <RTooltip formatter={(v) => (isPct ? `${Number(v).toFixed(1)}%` : eur(v, 2))} contentStyle={TOOLTIP} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="donut-legend">
        {data.map((d, i) => (
          <div key={i} className="legend-row">
            <span className="legend-dot" style={{ background: COLORS[i % COLORS.length] }} />
            <span className="legend-name">{d.name}</span>
            <span className="legend-value">
              {isPct ? `${d.value.toFixed(1)}%` : eur(d.value)}
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
        <strong>{s.value}/{s.max}</strong>
      </div>
      <div className="secondary-track">
        <div className="secondary-fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

const shortEur = (v: unknown) => {
  const n = Number(v ?? 0)
  if (!n) return ''
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${Math.round(n)}`
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
  const manyBars = chart.labels.length > 3
  const crowded = chart.labels.length > 5
  const axis = { fontSize: 10, fill: '#6b7670' }

  return (
    <figure className="chart-card">
      <figcaption className="chart-title">{chart.title}</figcaption>
      {chart.highlight && (
        <div className="chart-highlight">
          <small>{chart.highlight.label}</small>
          <strong>{chart.highlight.value}</strong>
        </div>
      )}
      <div className="chart-body">
        {chart.kind === 'line' && chart.series ? (
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={data} margin={{ top: 5, right: 8, left: -14, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5ebe7" vertical={false} />
              <XAxis dataKey="month" tick={axis} tickLine={false} axisLine={false} />
              <YAxis tick={axis} tickFormatter={shortEur} width={44} tickLine={false} axisLine={false} />
              <RTooltip formatter={(v) => eur(v, 2)} contentStyle={TOOLTIP} />
              <Legend wrapperStyle={{ fontSize: 10 }} iconType="circle" iconSize={8} />
              {chart.series.map((s, i) => (
                <Line key={s.name} type="monotone" dataKey={s.name} stroke={COLORS[i % COLORS.length]}
                  strokeWidth={2.5} dot={{ r: 2.5 }} animationDuration={700} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        ) : chart.kind === 'donut' ? (
          <Donut chart={chart} />
        ) : (
          <ResponsiveContainer width="100%" height={crowded ? 230 : 210}>
            <BarChart data={data} margin={{ top: 18, right: 4, left: -14, bottom: 0 }} barGap={2}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5ebe7" vertical={false} />
              <XAxis dataKey="name" tick={axis} interval={0} tickLine={false} axisLine={false}
                angle={crowded ? -35 : 0} textAnchor={crowded ? 'end' : 'middle'} height={crowded ? 48 : 30}
                tickFormatter={(v: string) => {
                  const short = SHORT_LABELS[v] ?? v
                  return !crowded && manyBars && short.length > 9 ? `${short.slice(0, 8)}…` : short
                }} />
              <YAxis tick={axis} tickFormatter={shortEur} width={44} tickLine={false} axisLine={false} />
              <RTooltip formatter={(v) => eur(v, 2)} contentStyle={TOOLTIP} cursor={{ fill: '#f0f4f1' }} />
              {chart.values2 && <Legend wrapperStyle={{ fontSize: 11 }} iconType="circle" iconSize={8} />}
              <Bar dataKey="value" name={chart.series_names?.[0] ?? 'Spent'} fill={COLORS[0]}
                radius={[5, 5, 0, 0]} animationDuration={700}>
                <LabelList dataKey="value" position="top" formatter={shortEur}
                  style={{ fontSize: 9, fill: '#00603c', fontWeight: 700 }} />
              </Bar>
              {chart.values2 && (
                <Bar dataKey="value2" name={chart.series_names?.[1] ?? 'Compare'} fill="#f2a33a"
                  radius={[5, 5, 0, 0]} animationDuration={700}>
                  <LabelList dataKey="value2" position="top" formatter={shortEur}
                    style={{ fontSize: 9, fill: '#8a5a12', fontWeight: 600 }} />
                </Bar>
              )}
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
      {chart.secondary && <Secondary s={chart.secondary} />}
      {chart.note && <p className="chart-note">{chart.note}</p>}
    </figure>
  )
}
