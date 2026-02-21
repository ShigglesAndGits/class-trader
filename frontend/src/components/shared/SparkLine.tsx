import { ResponsiveContainer, LineChart, Line } from 'recharts'

interface SparkLineProps {
  data: number[]
  color?: string
  height?: number
}

export default function SparkLine({ data, color = '#10B981', height = 32 }: SparkLineProps) {
  if (!data || data.length < 2) return null

  const chartData = data.map((v, i) => ({ i, v }))

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={chartData}>
        <Line
          type="monotone"
          dataKey="v"
          stroke={color}
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
