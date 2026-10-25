import './Promotions.css'

import { useSiteSettings } from '../../siteSettings'

function Promotions() {
  const { promotions } = useSiteSettings()

  const handlePromotionClick = (promotion) => {
    localStorage.setItem(
      'selectedPromotion',
      // Сохраняем только ID: условия акции сервер берёт из своего списка
      JSON.stringify({
        id: promotion.id,
      }),
    )

    const measurementForm = document.getElementById('measurement')

    if (measurementForm) {
      measurementForm.scrollIntoView({
        behavior: 'smooth',
        block: 'start',
      })
    }
  }

  return (
    <section className="promotions" id="promotions">
      <div className="container">
        <div className="promotions__inner">
          <div className="promotions__header">
            <h2 className="promotions__title">
              Акции и скидки на натяжные потолки{' '}
              <span className="promotions__title-gradient">
                в Ростове-на-Дону
              </span>
            </h2>

            <p className="promotions__description">
              Выберите подходящее предложение и получите скидку
              на натяжной потолок, бесплатный замер или дополнительные
              условия на освещение и дизайн-проект.
            </p>
          </div>

          <div className="promotions__grid">
            {promotions.map((promotion) => (
              <article
                className="promotions__card"
                key={promotion.id}
              >
                <div className="promotions__card-content">
                  <div className="promotions__value">
                    {promotion.value}
                  </div>

                  <h3 className="promotions__card-title">
                    {promotion.title}
                  </h3>

                  <p className="promotions__card-text">
                    {promotion.text}
                  </p>
                </div>

                <button
                  type="button"
                  className="promotions__card-button"
                  onClick={() => handlePromotionClick(promotion)}
                >
                  {promotion.button}
                </button>
              </article>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

export default Promotions
