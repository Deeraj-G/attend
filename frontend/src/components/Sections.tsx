import { CheckIcon, DocIcon, LockIcon, ShieldIcon, Target } from './Icons'
import type { Mode } from './TalkCard'

const STEPS = [
  {
    title: 'Talk to it',
    body: 'Describe a procedure out loud, or upload a recording. Pick patient or student mode.',
  },
  {
    title: 'Agent builds it',
    body: 'It transcribes on device, researches trusted clinical sources, and storyboards each scene with narration.',
  },
  {
    title: 'Review, then share',
    body: 'The doctor watches every scene and can ask for changes by voice before it reaches a patient.',
  },
]

export function HowItWorks() {
  return (
    <section className="section section-white" id="how">
      <div className="wrap">
        <div className="section-head">
          <h2>From a conversation to a clear video in minutes.</h2>
          <p>The agent researches, scripts, animates and narrates, then adapts depth and vocabulary to who’s watching.</p>
        </div>
        <ol className="steps">
          {STEPS.map((s, i) => (
            <li key={s.title} className="step-card">
              <span className="step-num">{String(i + 1).padStart(2, '0')}</span>
              <h3>{s.title}</h3>
              <p>{s.body}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  )
}

const PATIENT_POINTS = [
  'Plain language, no jargon, or jargon explained',
  'What to expect before, during and after',
  'Narrated, with subtitles',
  'Questions to bring to your doctor, auto-generated',
]

const STUDENT_POINTS = [
  'Step-by-step technique with instrument callouts',
  'Pathophysiology, differentials and complications',
  'Board-style quiz generated from every video',
  'Every claim linked to its source',
]

export function Audiences({ onPick }: { onPick: (mode: Mode) => void }) {
  return (
    <section className="section" id="audiences">
      <div className="wrap audience-grid">
        <article className="audience audience-light" id="patients">
          <p className="eyebrow">For patients &amp; families</p>
          <h2>Walk into your appointment understanding what’s next.</h2>
          <ul className="checks">
            {PATIENT_POINTS.map((p) => (
              <li key={p}>
                <CheckIcon /> {p}
              </li>
            ))}
          </ul>
          <button type="button" className="btn btn-ink" onClick={() => onPick('patient')}>
            Explain my procedure
          </button>
        </article>
        <article className="audience audience-dark" id="students">
          <p className="eyebrow">For medical students</p>
          <h2>Study anatomy and technique the way surgeons see it.</h2>
          <ul className="checks">
            {STUDENT_POINTS.map((p) => (
              <li key={p}>
                <CheckIcon /> {p}
              </li>
            ))}
          </ul>
          <button type="button" className="btn btn-mint" onClick={() => onPick('student')}>
            Start studying
          </button>
        </article>
      </div>
    </section>
  )
}

const LIBRARY = [
  { kind: 'Procedure', title: 'Knee arthroscopy, step by step', time: '4:12', bg: 'var(--surface-2)', fg: '#6fd6c6' },
  { kind: 'Condition', title: 'Type 2 diabetes: what’s happening inside', time: '3:05', bg: '#2a1f1d', fg: '#f1a98c' },
  { kind: 'Procedure', title: 'Cardiac catheterization', time: '5:30', bg: '#12302c', fg: '#6fd6c6' },
  { kind: 'Condition', title: 'Asthma and the airways', time: '2:48', bg: '#1b2433', fg: '#9db8e8' },
  { kind: 'Procedure', title: 'Cesarean delivery', time: '4:45', bg: 'var(--surface-3)', fg: '#f1a98c' },
  { kind: 'Condition', title: 'How a stroke affects the brain', time: '3:52', bg: '#231c2e', fg: '#c3a6f0' },
]

export function Library() {
  return (
    <section className="section" id="library">
      <div className="wrap">
        <div className="library-head">
          <h2>Popular right now</h2>
          <a href="#library" className="text-link">
            Browse the library →
          </a>
        </div>
        <ul className="library-grid">
          {LIBRARY.map((v) => (
            <li key={v.title} className="video-card">
              <div className="video-thumb" style={{ background: v.bg }}>
                <Target color={v.fg} />
                <span className="video-time">{v.time}</span>
              </div>
              <div className="video-body">
                <p className="eyebrow eyebrow-muted">{v.kind}</p>
                <h3>{v.title}</h3>
                <div className="tags">
                  <span className="tag tag-mint">Patient</span>
                  <span className="tag">Student</span>
                </div>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}

const TRUST = [
  {
    icon: <ShieldIcon />,
    title: 'Doctor-approved',
    body: 'Every explainer is reviewed and approved by the treating doctor before a patient sees it.',
  },
  {
    icon: <DocIcon />,
    title: 'Sources on screen',
    body: 'Every fact in a video links back to the guideline or patient-education page it came from.',
  },
  {
    icon: <LockIcon />,
    title: 'Private by design',
    body: 'Your recording is transcribed on this device. Only a de-identified description ever leaves it.',
  },
]

export function Trust() {
  return (
    <section className="section trust-section">
      <div className="wrap">
        <ul className="trust">
          {TRUST.map((t) => (
            <li key={t.title}>
              <span className="trust-icon">{t.icon}</span>
              <h3>{t.title}</h3>
              <p>{t.body}</p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}
