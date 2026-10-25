import { useState } from 'react'

import './Hero.css'

import Button from '../../components/Button/Button'

import heroBg from '../../assets/images/hero-bg.webp'
import { useSiteSettings } from '../../siteSettings'

function Hero() {
  const { hero } = useSiteSettings()

  const [formData, setFormData] = useState({
    name: '',
    phone: '',
  })

  const [status, setStatus] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [openedAt] = useState(() => Date.now())

  const handleChange = (event) => {
    const { name, value } = event.target

    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }))
  }

  const handleSubmit = async (event) => {
    event.preventDefault()

    setIsLoading(true)
    setStatus('')

    try {
      const response = await fetch(
        '/api/leads',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            name: formData.name,
            phone: formData.phone,
            source: 'hero_discount',
            promotion_id: hero.id,
            website: event.target.elements.website.value,
            form_elapsed_ms: Date.now() - openedAt,
          }),
        },
      )

      if (response.status === 429) {
        setStatus('rate_limit')
        return
      }

      if (!response.ok) {
        throw new Error('Ошибка отправки заявки')
      }

      setStatus('success')

      setFormData({
        name: '',
        phone: '',
      })
    } catch (error) {
      console.error('Ошибка отправки:', error)
      setStatus('error')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <section
      className="hero"
      style={{
        backgroundImage: `url(${heroBg})`,
      }}
    >
      <div className="hero__overlay"></div>

      <div className="container hero__inner">
        <div className="hero__content">
          <div className="hero__eyebrow">
            <span className="hero__eyebrow-line"></span>
            Производство и установка под ключ
          </div>

          <h1 className="hero__title">
            Натяжные потолки
            <br />
            в Ростове-на-Дону,
            <br />
            <span className="hero__title-gradient">
              которые меняют
              <br />
              пространство
            </span>
          </h1>

          <p className="hero__description">
            Проектируем, производим и устанавливаем современные
            натяжные потолки — от лаконичных матовых решений до
            световых линий и сложных конструкций.
          </p>

          <div className="hero__actions">
            <Button href="#calculator">
              Рассчитать стоимость
            </Button>

            <a
              className="hero__secondary-button"
              href="#portfolio"
            >
              Смотреть проекты
            </a>
          </div>

          <div className="hero__advantages">
            <div className="hero__advantage">
              Бесплатный замер
            </div>

            <div className="hero__advantage">
              Монтаж за 24 часа
            </div>

            <div className="hero__advantage">
              Гарантия 10 лет
            </div>

            <div className="hero__advantage">
              Рассрочка 0%
            </div>
          </div>
        </div>

        <div className="hero__form-card">
          <div className="hero__discount">
            {hero.value}
          </div>

          <h2 className="hero__form-title">
            {hero.title}
          </h2>

          <p className="hero__form-text">
            Оставьте заявку на бесплатный замер.
            Инженер свяжется с вами, рассчитает
            стоимость и расскажет, как получить
            максимальную скидку.
          </p>

          <div className="hero__form-line"></div>

          <form
            className="hero__form"
            onSubmit={handleSubmit}
          >
            <input
              type="text"
              name="name"
              value={formData.name}
              onChange={handleChange}
              placeholder="Ваше имя"
              autoComplete="name"
              required
            />

            <input
              type="tel"
              name="phone"
              value={formData.phone}
              onChange={handleChange}
              placeholder="+7 (___) ___-__-__"
              autoComplete="tel"
              required
            />

            {/* Поле-ловушка для ботов: человек его не видит */}
            <input
              type="text"
              name="website"
              tabIndex={-1}
              autoComplete="off"
              aria-hidden="true"
              style={{ position: 'absolute', left: '-10000px' }}
            />

            <label className="hero__consent">
              <input
                type="checkbox"
                name="privacy"
                required
              />

              <span>
                Я согласен на обработку персональных данных и принимаю{' '}
                <a
                  href="/privacy.html"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  политику обработки персональных данных
                </a>
              </span>
            </label>

            <Button
              type="submit"
              className="hero__submit"
            >
              {isLoading
                ? 'Отправляем...'
                : 'Забрать скидку'}
            </Button>
          </form>

          {status === 'success' && (
            <p className="hero__status hero__status--success">
              Заявка отправлена ✓
            </p>
          )}

          {status === 'error' && (
            <p className="hero__status hero__status--error">
              Не удалось отправить заявку
            </p>
          )}

          {status === 'rate_limit' && (
            <p className="hero__status hero__status--error">
              Слишком много заявок. Попробуйте через несколько минут.
            </p>
          )}
        </div>
      </div>
    </section>
  )
}

export default Hero