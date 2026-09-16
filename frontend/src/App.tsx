import { About } from './components/About/About'
import { ChatWidget } from './components/ChatWidget/ChatWidget'
import { Footer } from './components/Footer/Footer'
import { Header } from './components/Header/Header'
import { ScrollToTop } from './components/ScrollToTop/ScrollToTop'

export default function App() {
  return (
    <>
      <Header />
      <main>
        <About />
      </main>
      <Footer />
      <ScrollToTop />
      <ChatWidget />
    </>
  )
}
