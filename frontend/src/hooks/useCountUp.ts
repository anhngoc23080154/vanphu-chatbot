import { useEffect, useState } from 'react'

const prefersReducedMotion = () =>
  typeof window !== 'undefined' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches

/** easeOutQuad - chậm dần về cuối, giống hiệu ứng counter của bản gốc. */
const easeOut = (t: number) => 1 - (1 - t) * (1 - t)

/**
 * Đếm từ 0 tới target trong duration ms, bắt đầu khi `start` thành true.
 */
export function useCountUp(target: number, start: boolean, duration = 2000) {
  const [value, setValue] = useState(0)

  useEffect(() => {
    if (!start) return

    if (prefersReducedMotion()) {
      setValue(target)
      return
    }

    let frameId = 0
    let startTime: number | null = null

    const tick = (now: number) => {
      if (startTime === null) startTime = now
      const progress = Math.min((now - startTime) / duration, 1)
      setValue(Math.round(easeOut(progress) * target))
      if (progress < 1) {
        frameId = requestAnimationFrame(tick)
      }
    }

    frameId = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frameId)
  }, [target, start, duration])

  return value
}
