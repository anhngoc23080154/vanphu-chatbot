import { useEffect, useState } from 'react'

export interface ScrollState {
  /** Vị trí cuộn hiện tại (px). */
  scrollY: number
  /** Phần trăm đã cuộn của toàn trang (0-100). */
  progress: number
}

/**
 * Theo dõi vị trí cuộn, throttle bằng requestAnimationFrame.
 * Dùng cho header sticky và nút cuộn lên đầu trang.
 */
export function useScrollProgress(): ScrollState {
  const [state, setState] = useState<ScrollState>({ scrollY: 0, progress: 0 })

  useEffect(() => {
    let ticking = false

    const update = () => {
      const scrollY = window.scrollY
      const scrollable =
        document.documentElement.scrollHeight - window.innerHeight
      const progress =
        scrollable > 0 ? Math.min((scrollY / scrollable) * 100, 100) : 0
      setState({ scrollY, progress })
      ticking = false
    }

    const onScroll = () => {
      if (ticking) return
      ticking = true
      requestAnimationFrame(update)
    }

    update()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
    }
  }, [])

  return state
}
