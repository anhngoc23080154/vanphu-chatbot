import { useEffect } from 'react'
import { navItems } from '../../data/site'
import { CloseIcon } from '../icons'

interface MobileMenuProps {
  open: boolean
  onClose: () => void
}

export function MobileMenu({ open, onClose }: MobileMenuProps) {
  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [open, onClose])

  return (
    <>
      <div
        className={`mobile-menu__overlay${open ? ' is-open' : ''}`}
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        className={`mobile-menu${open ? ' is-open' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-label="Menu"
        aria-hidden={!open}
      >
        <div className="mobile-menu__head">
          <img
            src="/images/logo-dark.png"
            alt="Văn Phú"
            className="mobile-menu__logo"
          />
          <button type="button" onClick={onClose} aria-label="Đóng menu">
            <CloseIcon />
          </button>
        </div>

        <nav aria-label="Điều hướng di động">
          <ul className="mobile-menu__list">
            {navItems.map((item) => (
              <li key={item.label}>
                <a
                  href={item.href}
                  onClick={(e) => {
                    e.preventDefault()
                    onClose()
                  }}
                  tabIndex={open ? 0 : -1}
                >
                  {item.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </>
  )
}
