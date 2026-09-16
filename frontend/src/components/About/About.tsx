import { aboutContent, stats } from '../../data/site'
import { useInView } from '../../hooks/useInView'
import { StatCounter } from './StatCounter'
import './About.css'

export function About() {
  const [statsRef, statsInView] = useInView<HTMLDivElement>(0.3)

  return (
    <section className="about" id="ve-chung-toi">
      <div className="about__inner">
        <div className="about__media">
          <picture>
            <source
              media="(max-width: 767px)"
              srcSet="/images/about-mobile.png"
            />
            <img
              src="/images/about-desktop.png"
              alt="Dự án tiêu biểu của Văn Phú"
              width={1186}
              height={1200}
              fetchPriority="high"
            />
          </picture>
        </div>

        <div className="about__content">
          <div className="about__heading">
            <h4 className="about__eyebrow">{aboutContent.eyebrow}</h4>
            <h1 className="about__title">
              {aboutContent.titleLine1}
              <br />
              {aboutContent.titleLine2}
            </h1>
            <p className="about__description">{aboutContent.description}</p>
          </div>

          <div className="about__stats" ref={statsRef}>
            {stats.map((stat) => (
              <StatCounter
                key={stat.label}
                value={stat.value}
                label={stat.label}
                start={statsInView}
              />
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
