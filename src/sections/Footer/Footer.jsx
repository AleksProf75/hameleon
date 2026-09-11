import './Footer.css'

import logo from '../../assets/logos/logo.svg'

function Footer() {
  return (
    <footer className="footer" id="contacts">
      <div className="container">
        <div className="footer__inner">
          <div className="footer__top">
            <div className="footer__brand">
              <a
                className="footer__logo"
                href="#top"
                aria-label="Хамелеон — на главную"
              >
                <img
                  className="footer__logo-mark"
                  src={logo}
                  alt="Хамелеон — натяжные потолки"
                />

                <div className="footer__logo-text">
                  <strong>ХАМЕЛЕОН</strong>
                  <span>НАТЯЖНЫЕ ПОТОЛКИ</span>
                </div>
              </a>

              <p className="footer__description">
                Производство и установка натяжных потолков
                в Ростове-на-Дону.
              </p>
            </div>

            <div className="footer__column">
              <span className="footer__label">
                Контакты
              </span>

              <a
                className="footer__phone"
                href="tel:+79282706862"
              >
                +7 (928) 270-68-62
              </a>

              <address className="footer__address">
                г. Ростов-на-Дону
                <br />
                ул. Нансена, 81с3
              </address>
            </div>

            <div className="footer__column">
              <span className="footer__label">
                График работы
              </span>

              <p className="footer__schedule">
                Пн–Вс · 9:00–21:00
              </p>

              <p className="footer__office">
                Офис: Пн–Пт · 9:00–17:00
              </p>

              <a
                className="footer__privacy"
                href="/privacy.html"
                target="_blank"
                rel="noopener noreferrer"
              >
                Политика обработки персональных данных
              </a>
            </div>
          </div>

          <div className="footer__bottom">
            <p>© «Хамелеон» 2026</p>

            <p>
              Натяжные потолки в Ростове-на-Дону
            </p>
          </div>
        </div>
      </div>
    </footer>
  )
}

export default Footer