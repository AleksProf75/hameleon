import './Advantages.css'

import Button from '../../components/Button/Button'

import qualityIcon from '../../assets/icons/quality.svg'
import productionIcon from '../../assets/icons/production.svg'
import teamIcon from '../../assets/icons/team.svg'
import controlIcon from '../../assets/icons/control.svg'
import speedIcon from '../../assets/icons/speed.svg'
import warrantyIcon from '../../assets/icons/warranty.svg'
import paymentIcon from '../../assets/icons/payment.svg'
import installmentIcon from '../../assets/icons/installment.svg'

const advantages = [
  {
    icon: qualityIcon,
    title: 'Качественные материалы',
    text: 'Полотна без запаха, безопасные для здоровья. Предоставляем сертификаты.',
  },
  {
    icon: productionIcon,
    title: 'Своё производство',
    text: 'Изготавливаем сложные формы и конструкции по чертежам и дизайн-проектам.',
  },
  {
    icon: teamIcon,
    title: 'Собственные бригады',
    text: 'Опытные монтажники, сертифицированное и взрывобезопасное оборудование.',
  },
  {
    icon: controlIcon,
    title: 'Контроль качества',
    text: 'Материалы и комплектующие совместимы и проходят внутренний контроль.',
  },
  {
    icon: speedIcon,
    title: 'Короткие сроки',
    text: 'Готовый натяжной потолок во всей квартире — в кратчайшие сроки, вплоть до 24 часов.',
  },
  {
    icon: warrantyIcon,
    title: 'Гарантия',
    text: '10 лет на материалы, 2 года на монтаж и гарантийное обслуживание.',
  },
  {
    icon: paymentIcon,
    title: 'Безналичная оплата',
    text: 'Удобные способы расчёта для частных и корпоративных клиентов.',
  },
  {
    icon: installmentIcon,
    title: 'Рассрочка',
    text: 'Можно распределить стоимость проекта без переплаты на удобный срок.',
  },
]

function Advantages() {
  return (
    <section className="advantages" id="advantages">
      <div className="container">
        <div className="advantages__inner">
          <h2 className="advantages__title">
            Преимущества натяжных потолков{' '}
            <span className="advantages__title-gradient advantages__title-gradient--blue">
              от компании
            </span>{' '}
            <span className="advantages__title-gradient advantages__title-gradient--green">
              «Хамелеон»
            </span>
          </h2>

          <div className="advantages__grid">
            {advantages.map((item) => (
              <article
                className="advantages__card"
                key={item.title}
              >
                <div className="advantages__icon">
                  <img
                    src={item.icon}
                    alt=""
                    aria-hidden="true"
                  />
                </div>

                <h3 className="advantages__card-title">
                  {item.title}
                </h3>

                <p className="advantages__card-text">
                  {item.text}
                </p>
              </article>
            ))}
          </div>

          <div className="advantages__installment">
            <div className="advantages__installment-content">
              <span className="advantages__installment-label">
                Рассрочка
              </span>

              <strong className="advantages__installment-title">
                0% · 0% · 6 месяцев
              </strong>
            </div>

            <Button
              href="#calculator"
              className="advantages__button"
            >
              Рассчитать проект
            </Button>
          </div>
        </div>
      </div>
    </section>
  )
}

export default Advantages