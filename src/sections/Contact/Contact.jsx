import { useState } from 'react'

import './Contact.css'

import Button from '../../components/Button/Button'

function Contact({ calculatorData }) {
  const [formData, setFormData] = useState({
    name: '',
    phone: '',
  })

  const [status, setStatus] = useState('')
  const [isLoading, setIsLoading] = useState(false)

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

    let selectedPromotion = null

    const savedPromotion = localStorage.getItem('selectedPromotion')

    if (savedPromotion) {
      try {
        selectedPromotion = JSON.parse(savedPromotion)
      } catch (error) {
        console.error('Ошибка чтения выбранной акции:', error)
      }
    }

    console.log('Данные формы:', formData)
    console.log('Данные калькулятора:', calculatorData)
    console.log('Выбранная акция:', selectedPromotion)

    try {
      const response = await fetch('/api/leads', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          name: formData.name,
          phone: formData.phone,
          source: selectedPromotion
            ? 'promotion'
            : calculatorData
              ? 'calculator'
              : 'contact',
          calculator: calculatorData,
          promotion: selectedPromotion,
        }),
      })

      if (!response.ok) {
        throw new Error('Ошибка отправки')
      }

      const data = await response.json()

      console.log('Ответ сервера:', data)

      setStatus('success')

      setFormData({
        name: '',
        phone: '',
      })

      if (selectedPromotion) {
        localStorage.removeItem('selectedPromotion')
      }
    } catch (error) {
      console.error(error)
      setStatus('error')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <section
      className="contact"
      id="measurement"
    >
      <div className="container">
        <div className="contact__card">
          <div className="contact__content">
            <span className="contact__label">
              Бесплатный замер
            </span>

            <h2 className="contact__title">
              Бесплатный замер натяжного потолка
              <br />
              в Ростове-на-Дону
            </h2>

            <p className="contact__description">
              Инженер приедет в удобное время, выполнит замер помещения,
              покажет образцы полотен, поможет подобрать освещение и конструкцию,
              рассчитает точную стоимость и зафиксирует цену в договоре.
            </p>
          </div>

          <form
            className="contact__form"
            onSubmit={handleSubmit}
          >
            <div className="contact__fields">
              <input
                className="contact__input"
                type="text"
                name="name"
                placeholder="Ваше имя"
                autoComplete="name"
                value={formData.name}
                onChange={handleChange}
                required
              />

              <input
                className="contact__input"
                type="tel"
                name="phone"
                placeholder="+7 (___) ___-__-__"
                autoComplete="tel"
                value={formData.phone}
                onChange={handleChange}
                required
              />
            </div>

            <label className="contact__consent">
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
              className="contact__button"
            >
              {isLoading
                ? 'Отправляем...'
                : 'Вызвать замерщика бесплатно'}
            </Button>

            {status === 'success' && (
              <p className="contact__status contact__status--success">
                Заявка успешно отправлена
              </p>
            )}

            {status === 'error' && (
              <p className="contact__status contact__status--error">
                Не удалось отправить заявку. Попробуйте ещё раз.
              </p>
            )}
          </form>
        </div>
      </div>
    </section>
  )
}

export default Contact
