import { useEffect, useRef, useState } from 'react'

/**
 * Trả về ref và cờ cho biết phần tử đã lọt vào viewport hay chưa.
 * Chỉ kích hoạt một lần (dùng cho animation đếm số).
 */
export function useInView<T extends HTMLElement>(
  threshold = 0.3,
): [React.RefObject<T | null>, boolean] {
  const ref = useRef<T>(null)
  const [inView, setInView] = useState(false)

  useEffect(() => {
    const element = ref.current
    if (!element) return

    if (typeof IntersectionObserver === 'undefined') {
      setInView(true)
      return
    }

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          setInView(true)
          observer.disconnect()
        }
      },
      { threshold },
    )

    observer.observe(element)
    return () => observer.disconnect()
  }, [threshold])

  return [ref, inView]
}
