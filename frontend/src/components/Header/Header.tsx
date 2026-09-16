import { useEffect, useState } from 'react'
import { navItems } from '../../data/site'
import { useScrollProgress } from '../../hooks/useScrollProgress'
import { HeartIcon } from '../icons'
import { MobileMenu } from './MobileMenu'
import './Header.css'

export function Header() {
  const { scrollY } = useScrollProgress()
  const [menuOpen, setMenuOpen] = useState(false)
  const [lang, setLang] = useState<'vi' | 'en'>('vi')

  // Bản gốc thêm class "sticky" khi cuộn quá 10px.
  const isSticky = scrollY > 10

  // Khoá cuộn nền khi drawer mobile đang mở.
  useEffect(() => {
    document.body.classList.toggle('no-scroll', menuOpen)
    return () => document.body.classList.remove('no-scroll')
  }, [menuOpen])

  return (
    <>
      <header className={`header${isSticky ? ' header--sticky' : ''}`}>
        <div className="header__inner">
          <div className="header__left">
            <button
              type="button"
              className={`header__toggle${menuOpen ? ' header__toggle--open' : ''}`}
              aria-label={menuOpen ? 'Đóng menu' : 'Mở menu'}
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((open) => !open)}
            >
              <span />
              <span />
              <span />
            </button>

            <a className="header__logo" href="#" aria-label="Văn Phú - Trang chủ">
              <img
                src="/images/logo-dark.png"
                alt="Văn Phú"
                width={910}
                height={160}
              />
            </a>
          </div>

          <div className="header__right">
            <nav className="header__nav" aria-label="Điều hướng chính">
              <ul className="header__menu">
                {navItems.map((item) => (
                  <li key={item.label}>
                    <a href={item.href} onClick={(e) => e.preventDefault()}>
                      <span>{item.label}</span>
                    </a>
                  </li>
                ))}
              </ul>
            </nav>

            <a
              className="header__wishlist"
              href="#"
              aria-label="Danh sách yêu thích"
              onClick={(e) => e.preventDefault()}
            >
              <HeartIcon />
            </a>

            <div className="header__lang">
              <button
                type="button"
                className={lang === 'vi' ? 'is-current' : ''}
                onClick={() => setLang('vi')}
              >
                VI
              </button>
              <span className="header__lang-divider" aria-hidden="true" />
              <button
                type="button"
                className={lang === 'en' ? 'is-current' : ''}
                onClick={() => setLang('en')}
              >
                EN
              </button>
            </div>
          </div>
        </div>
      </header>

      <MobileMenu open={menuOpen} onClose={() => setMenuOpen(false)} />
    </>
  )
}
