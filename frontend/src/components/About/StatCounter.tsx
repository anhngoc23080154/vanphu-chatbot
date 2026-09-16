import { useCountUp } from '../../hooks/useCountUp'

interface StatCounterProps {
  value: number
  label: string
  /** Chỉ bắt đầu đếm khi section đã lọt vào viewport. */
  start: boolean
}

export function StatCounter({ value, label, start }: StatCounterProps) {
  const current = useCountUp(value, start, 2000)

  return (
    <div className="about__stat">
      <div className="about__stat-number">{current}</div>
      <div className="about__stat-label">{label}</div>
    </div>
  )
}
