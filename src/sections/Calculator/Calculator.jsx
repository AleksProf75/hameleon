import { useMemo, useState } from 'react'

import './Calculator.css'
import Button from '../../components/Button/Button'

function Calculator({ onCalculate }) {
  const [width, setWidth] = useState(4.2)
  const [length, setLength] = useState(5)
  const [ceilingType, setCeilingType] = useState('Матовый')
  const [corners, setCorners] = useState(4)
  const [lights, setLights] = useState(6)

  const area = useMemo(() => {
    const result = Number(width) * Number(length)

    if (!Number.isFinite(result)) {
      return 0
    }

    return Math.round(result * 10) / 10
  }, [width, length])

  const price = useMemo(() => {
    const priceByType = {
      Матовый: 450,
      Глянцевый: 500,
      Сатиновый: 480,
      Тканевый: 900,
    }

    const basePrice = area * (priceByType[ceilingType] || 450)
    const cornersPrice = Number(corners) * 150
    const lightsPrice = Number(lights) * 300

    const result = basePrice + cornersPrice + lightsPrice

    return Math.max(0, Math.round(result / 100) * 100)
  }, [area, ceilingType, corners, lights])

  const formattedPrice = new Intl.NumberFormat('ru-RU').format(price)

  const handleExactCalculation = () => {
    // Площадь и цену сервер пересчитывает сам по этим параметрам
    const data = {
      width: Number(width),
      length: Number(length),
      ceiling_type: ceilingType,
      corners: Number(corners),
      lights: Number(lights),
    }


    onCalculate?.(data)

    document
      .getElementById('measurement')
      ?.scrollIntoView({
        behavior: 'smooth',
        block: 'start',
      })
  }

  return (
    <section className="calculator" id="calculator">
      <div className="container">
        <div className="calculator__card">
          <div className="calculator__content">
            <h2 className="calculator__title">
              Калькулятор стоимости натяжного потолка
            </h2>

            <p className="calculator__description">
              Рассчитайте предварительную стоимость натяжного потолка
              в Ростове-на-Дону по площади помещения, типу полотна,
              количеству углов и светильников. При записи на бесплатный
              замер действует дополнительная скидка 500 ₽.
            </p>

            <div className="calculator__grid">
              <label className="calculator__field">
                <span>ШИРИНА, М</span>

                <input
                  type="number"
                  min="1"
                  step="0.1"
                  value={width}
                  onChange={(event) => setWidth(event.target.value)}
                />
              </label>

              <label className="calculator__field">
                <span>ДЛИНА, М</span>

                <input
                  type="number"
                  min="1"
                  step="0.1"
                  value={length}
                  onChange={(event) => setLength(event.target.value)}
                />
              </label>

              <label className="calculator__field">
                <span>ПЛОЩАДЬ, М²</span>

                <input
                  type="text"
                  value={area}
                  readOnly
                />
              </label>

              <label className="calculator__field">
                <span>ТИП ПОТОЛКА</span>

                <select
                  value={ceilingType}
                  onChange={(event) => setCeilingType(event.target.value)}
                >
                  <option value="Матовый">Матовый</option>
                  <option value="Глянцевый">Глянцевый</option>
                  <option value="Сатиновый">Сатиновый</option>
                  <option value="Тканевый">Тканевый</option>
                </select>
              </label>

              <label className="calculator__field">
                <span>УГЛЫ</span>

                <input
                  type="number"
                  min="4"
                  value={corners}
                  onChange={(event) => setCorners(event.target.value)}
                />
              </label>

              <label className="calculator__field">
                <span>СВЕТИЛЬНИКИ</span>

                <input
                  type="number"
                  min="0"
                  value={lights}
                  onChange={(event) => setLights(event.target.value)}
                />
              </label>
            </div>
          </div>

          <aside className="calculator__result">
            <span className="calculator__result-label">
              Предварительная стоимость
            </span>

            <div className="calculator__price">
              от {formattedPrice} ₽
            </div>

            <p className="calculator__result-text">
              Финальная цена фиксируется после замера
              и не меняется после согласования.
            </p>

            <Button
              onClick={handleExactCalculation}
              className="calculator__button"
            >
              Получить точный расчёт
            </Button>
          </aside>
        </div>
      </div>
    </section>
  )
}

export default Calculator