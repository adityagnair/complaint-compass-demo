import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

export default function TrendChart({ data }) {
  if (!data.length) return <p className="panel-empty">Monthly complaint data will appear here once reports have timestamps.</p>
  const chartData = data.map((item) => ({ ...item, count: Number(item.count) }))
  const total = chartData.reduce((sum, item) => sum + item.count, 0)
  return <div className="trend-chart"><div className="chart-area"><ResponsiveContainer width="100%" height="100%"><LineChart data={chartData} margin={{ top: 12, right: 12, left: -18, bottom: 0 }}><CartesianGrid stroke="#343434" vertical={false} /><XAxis dataKey="month" tickFormatter={(value) => value.slice(2)} tickLine={false} axisLine={false} tick={{ fill: '#858585', fontSize: 10 }} /><YAxis allowDecimals={false} tickLine={false} axisLine={false} tick={{ fill: '#858585', fontSize: 10 }} /><Tooltip formatter={(value) => [`${value} complaints`, 'Volume']} contentStyle={{ backgroundColor: '#1b1b1b', color: '#ededed', border: '1px solid #343434', borderRadius: 5, fontSize: 11, boxShadow: 'none' }} /><Line type="monotone" dataKey="count" stroke="#35d394" strokeWidth={2.5} dot={{ r: 3.5, fill: '#1b1b1b', strokeWidth: 2 }} activeDot={{ r: 5, fill: '#35d394' }} /></LineChart></ResponsiveContainer></div><div className="chart-summary"><span>{chartData.length} months</span><strong>{total.toLocaleString()} reports</strong></div></div>
}
