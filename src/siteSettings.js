import { useEffect, useState } from 'react'

// Значения по умолчанию совпадают с backend/site_settings.py.
// Сайт показывает их сразу, а затем заменяет настройками
// из панели администратора (/api/site/settings).
export const DEFAULT_SETTINGS = {
  hero: {
    id: 'hero_discount_20',
    value: '20%',
    title: 'Месяц мега-скидок',
    text: 'Заявка на бесплатный замер с главного экрана',
  },
  promotions: [
    {
      id: 'svo_discount_10',
      value: '10%',
      title: 'Скидка участникам СВО и семьям',
      text: 'Скидка 10% на услуги компании при заказе от 9 500 ₽. Условия уточняйте у специалиста.',
      button: 'Получить скидку',
    },
    {
      id: 'combined_discount_25',
      value: '25%',
      title: 'Суммируем скидки',
      text: 'Комбинация акционных условий 10 + 10 + 5. Подробности расскажет инженер по замеру.',
      button: 'Узнать условия',
    },
    {
      id: 'successful_day_12',
      value: '12%',
      title: '«Успешный день»',
      text: 'При заключении договора в день замера действует скидка 12% на работы «под ключ».',
      button: 'Записаться на замер',
    },
    {
      id: 'design_project_3d',
      value: '3D',
      title: 'Дизайн-проект бесплатно',
      text: 'Для нестандартных конструкций подготовим визуализацию будущего потолка.',
      button: 'Хочу проект',
    },
    {
      id: 'lights_discount_20',
      value: '20%',
      title: 'Светильники со скидкой',
      text: 'При покупке натяжного потолка специальные LED-светильники доступны со скидкой 20%.',
      button: 'Подобрать освещение',
    },
    {
      id: 'measurement_bonus_500',
      value: '500 ₽',
      title: 'Дополнительная скидка за замер',
      text: 'Запишитесь на бесплатный замер и получите ещё одну персональную выгоду.',
      button: 'Вызвать замерщика',
    },
  ],
  calculator: {
    types: [
      { name: 'Матовый', price_per_m2: 450 },
      { name: 'Глянцевый', price_per_m2: 500 },
      { name: 'Сатиновый', price_per_m2: 480 },
      { name: 'Тканевый', price_per_m2: 900 },
    ],
    price_per_corner: 150,
    price_per_light: 300,
  },
  price_cards: [
    { room: 'ГОСТИНАЯ', title: 'Многоуровневый потолок', price: 'от 9 000 ₽' },
    { room: 'СПАЛЬНЯ', title: 'Тканевый потолок', price: 'от 13 000 ₽' },
    { room: 'ДЕТСКАЯ', title: 'Фотопечать', price: 'от 7 200 ₽' },
    { room: 'КУХНЯ', title: 'Глянцевый потолок', price: 'от 4 900 ₽' },
    { room: 'ПРИХОЖАЯ', title: 'Световые линии', price: 'от 4 900 ₽' },
  ],
}

// Один запрос на всю страницу, сколько бы разделов ни использовали настройки
let request = null

function loadSettings() {
  if (!request) {
    request = fetch('/api/site/settings')
      .then((response) => (response.ok ? response.json() : DEFAULT_SETTINGS))
      .catch(() => DEFAULT_SETTINGS)
  }

  return request
}

export function useSiteSettings() {
  const [settings, setSettings] = useState(DEFAULT_SETTINGS)

  useEffect(() => {
    let isActive = true

    loadSettings().then((loaded) => {
      if (isActive) {
        setSettings(loaded)
      }
    })

    return () => {
      isActive = false
    }
  }, [])

  return settings
}
