import { useScrollProgress } from '../../hooks/useScrollProgress'
import { ChevronUpIcon } from '../icons'
import './ScrollToTop.css'

export function ScrollToTop() {
  const { scrollY, progress } = useScrollProgress()
  const visible = scrollY > 100

  const scrollToTop = () => {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  return (
    <button
      type="button"
      className={`scroll-to-top${visible ? ' is-visible' : ''}`}
      onClick={scrollToTop}
      aria-label="Cuộn lên đầu trang"
      tabIndex={visible ? 0 : -1}
      style={{
        // Vòng tiến trình tô theo % đã cuộn, giống bản gốc.
        background: `conic-gradient(#E67E2E ${progress}%, #d7d7d7 ${progress}%)`,
      }}
    >
      <span className="scroll-to-top__progress">
        <ChevronUpIcon />
      </span>
    </button>
  )
}
