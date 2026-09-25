import { useState } from 'react'
import { Logo, Nav } from './components/Nav'
import { PlayerPreview } from './components/PlayerPreview'
import { Audiences, HowItWorks, Library, Trust } from './components/Sections'
import { TalkCard, type Mode, type TalkResult } from './components/TalkCard'
import './App.css'

function App() {
  const [mode, setMode] = useState<Mode>('patient')
  const [result, setResult] = useState<TalkResult | null>(null)

  function pickAudience(next: Mode) {
    setMode(next)
    document.getElementById('talk')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  return (
    <div id="top">
      <Nav />
      <main>
        <section className="hero">
          <div className="wrap hero-grid">
            <div className="hero-copy">
              <p className="eyebrow">AI medical video agent</p>
              <h1>
                See the procedure <em>before</em> it happens.
              </h1>
              <p className="hero-lede">
                Describe any procedure out loud. Attend turns it into a clear, animated explainer video:
                plain language for patients, clinically detailed for students.
              </p>
              <TalkCard mode={mode} onModeChange={setMode} onResult={setResult} />
            </div>
            <PlayerPreview mode={mode} transcript={result?.text || null} />
          </div>
        </section>
        <HowItWorks />
        <Audiences onPick={pickAudience} />
        <Library />
        <Trust />
      </main>
      <footer className="footer">
        <div className="wrap footer-inner">
          <Logo />
          <p>Patient education, not medical advice. Always follow your care team’s instructions.</p>
        </div>
      </footer>
    </div>
  )
}

export default App
