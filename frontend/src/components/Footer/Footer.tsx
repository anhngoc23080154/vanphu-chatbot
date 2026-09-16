import {
  contactInfo,
  copyright,
  footerIntro,
  navItems,
  privacyNote,
  socialLinks,
} from '../../data/site'
import {
  FacebookIcon,
  LinkedInIcon,
  LocationIcon,
  MailIcon,
  PhoneIcon,
  YoutubeIcon,
} from '../icons'
import './Footer.css'

const contactIcons = {
  location: LocationIcon,
  phone: PhoneIcon,
  mail: MailIcon,
}

const socialIcons = [FacebookIcon, LinkedInIcon, YoutubeIcon]

export function Footer() {
  return (
    <footer className="footer">
      <div className="container">
        <div className="footer__top">
          <a href="#" onClick={(e) => e.preventDefault()}>
            <img
              className="footer__logo"
              src="/images/logo-white.png"
              alt="Văn Phú"
              width={932}
              height={197}
              loading="lazy"
            />
          </a>
          <p className="footer__intro">{footerIntro}</p>
          <div className="footer__line" />
        </div>

        <div className="footer__cols">
          <div className="footer__col footer__col--contact">
            <h6 className="footer__title">Liên hệ</h6>
            <ul className="footer__list">
              {contactInfo.map((item) => {
                const Icon = contactIcons[item.icon]
                return (
                  <li key={item.text}>
                    <a href={item.href}>
                      <Icon className="footer__icon" />
                      <span>{item.text}</span>
                    </a>
                  </li>
                )
              })}
            </ul>

            <p className="footer__note">
              {privacyNote.text}{' '}
              <a href={privacyNote.href} onClick={(e) => e.preventDefault()}>
                {privacyNote.linkText}
              </a>
            </p>
            <p className="footer__copyright">{copyright}</p>
          </div>

          <div className="footer__col">
            <h6 className="footer__title">Khám phá</h6>
            <ul className="footer__list footer__list--menu">
              {navItems.map((item) => (
                <li key={item.label}>
                  <a href={item.href} onClick={(e) => e.preventDefault()}>
                    <span>{item.label}</span>
                  </a>
                </li>
              ))}
            </ul>
          </div>

          <div className="footer__col">
            <h6 className="footer__title">Kết nối với chúng tôi</h6>
            <ul className="footer__list">
              {socialLinks.map((item, index) => {
                const Icon = socialIcons[index]
                return (
                  <li key={item.label}>
                    <a
                      href={item.href}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <Icon className="footer__icon" />
                      <span>{item.label}</span>
                    </a>
                  </li>
                )
              })}
            </ul>
          </div>
        </div>
      </div>
    </footer>
  )
}
