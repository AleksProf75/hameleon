import { useState } from 'react'

import Header from './sections/Header/Header'
import Hero from './sections/Hero/Hero'
import Calculator from './sections/Calculator/Calculator'
import Promotions from './sections/Promotions/Promotions'
import Advantages from './sections/Advantages/Advantages'
import Portfolio from './sections/Portfolio/Portfolio'
import Price from './sections/Price/Price'
import Production from './sections/Production/Production'
import Partners from './sections/Partners/Partners'
import Team from './sections/Team/Team'
import Contact from './sections/Contact/Contact'
import Footer from './sections/Footer/Footer'
import ChatWidget from './components/ChatWidget/ChatWidget'

function App() {
  const [calculatorData, setCalculatorData] = useState(null)

  return (
    <>
      <Header />

      <main>
        <Hero />

        <Calculator
          onCalculate={setCalculatorData}
        />

        <Promotions />
        <Advantages />
        <Portfolio />
        <Price />
        <Production />
        <Partners />
        <Team />

        <Contact
          calculatorData={calculatorData}
        />
      </main>

      <Footer />

      <ChatWidget />
    </>
  )
}

export default App