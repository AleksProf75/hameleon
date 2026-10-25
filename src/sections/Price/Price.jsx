import './Price.css'

import price01 from '../../assets/images/prices/price-1.jpg'
import price02 from '../../assets/images/prices/price-2.jpg'
import price03 from '../../assets/images/prices/price-3.jpg'
import price04 from '../../assets/images/prices/price-4.png'
import price05 from '../../assets/images/prices/price-5.jpg'
import { useSiteSettings } from '../../siteSettings'

const priceItems = [
  {
    image: price01,
    room: 'ГОСТИНАЯ',
    title: 'Многоуровневый потолок',
    price: 'от 9 000 ₽',
    className: 'price__card--1',
  },
  {
    image: price02,
    room: 'СПАЛЬНЯ',
    title: 'Тканевый потолок',
    price: 'от 13 000 ₽',
    className: 'price__card--2',
  },
  {
    image: price03,
    room: 'ДЕТСКАЯ',
    title: 'Фотопечать',
    price: 'от 7 200 ₽',
    className: 'price__card--3',
  },
  {
    image: price04,
    room: 'КУХНЯ',
    title: 'Глянцевый потолок',
    price: 'от 4 900 ₽',
    className: 'price__card--4',
  },
  {
    image: price05,
    room: 'ПРИХОЖАЯ',
    title: 'Световые линии',
    price: 'от 4 900 ₽',
    className: 'price__card--5',
  },
]

function Price() {
  const { price_cards: priceCards } = useSiteSettings()

  return (
    <section className="price" id="price">
      <div className="container">
        <div className="price__inner">
          <h2 className="price__title">
            Цены на натяжные потолки в Ростове-на-Дону
          </h2>

          <div className="price__grid">
            {priceItems.map((card, index) => ({
              ...card,
              // Тексты карточек меняются в панели, картинки и расположение — нет
              ...priceCards[index],
            })).map((item) => (
              <a
                className={`price__card ${item.className}`}
                href="#measurement"
                key={item.className}
              >
                <img
                  className="price__image"
                  src={item.image}
                  alt={`${item.title} в ${item.room.toLowerCase()}`}
                  loading="lazy"
                />

                <div
                  className="price__overlay"
                  aria-hidden="true"
                />

                <div className="price__content">
                  <span className="price__room">
                    {item.room}
                  </span>

                  <div className="price__bottom">
                    <h3 className="price__card-title">
                      {item.title}
                    </h3>

                    <span className="price__value">
                      {item.price}
                    </span>
                  </div>
                </div>
              </a>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

export default Price