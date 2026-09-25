import { PulseIcon } from './Icons'

export function Logo() {
  return (
    <a href="#top" className="logo" aria-label="Attend home">
      <span className="logo-mark">
        <PulseIcon />
      </span>
      Attend
    </a>
  )
}

export function Nav() {
  return (
    <header className="nav">
      <div className="wrap nav-inner">
        <Logo />
        <nav className="nav-links" aria-label="Main">
          <a href="#how">How it works</a>
          <a href="#patients">For patients</a>
          <a href="#students">For students</a>
          <a href="#library">Library</a>
        </nav>
        <div className="nav-cta">
          <a href="#talk" className="btn btn-ink btn-sm">
            Talk to me
          </a>
        </div>
      </div>
    </header>
  )
}
