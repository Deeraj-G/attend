import { PlayIcon } from './Icons'
import type { Mode } from './TalkCard'

const CHAPTERS = ['Before you arrive', 'The procedure', 'Recovery', 'Going home']
const DEFAULT_CAPTION = 'Your heart’s natural pacemaker sends an electrical signal with every beat…'

function firstSentence(text: string) {
  const sentence = text.match(/^.*?[.!?](\s|$)/)?.[0] ?? text
  return sentence.length > 120 ? `${sentence.slice(0, 117).trimEnd()}…` : sentence.trim()
}

/** Preview of the explainer player. Shows the doctor's own words once a transcript exists. */
export function PlayerPreview({ mode, transcript }: { mode: Mode; transcript: string | null }) {
  const caption = transcript ? firstSentence(transcript) : DEFAULT_CAPTION

  return (
    <figure className="player" aria-label="Explainer video preview">
      <div className="player-stage">
        <div className="player-chips">
          <span className="chip chip-mint">{mode === 'patient' ? 'Patient mode' : 'Student mode'}</span>
          <span className="chip">3D · narrated</span>
        </div>

        <svg className="player-art" viewBox="0 0 320 240" aria-hidden="true">
          <path
            d="M160 214C112 180 58 142 58 88c0-30 22-50 49-50 22 0 40 12 53 32 13-20 31-32 53-32 27 0 49 20 49 50 0 54-54 92-102 126Z"
            fill="none"
            stroke="#e4a58c"
            strokeWidth="2"
          />
          <path d="M136 92c6 26 22 44 24 76" fill="none" stroke="#f2eee6" strokeWidth="1.5" strokeDasharray="4 5" />
          <circle cx="136" cy="92" r="16" fill="none" stroke="#6fd6c6" strokeWidth="2" />
          <circle cx="136" cy="92" r="4" fill="#6fd6c6" />
          <circle cx="184" cy="150" r="11" fill="none" stroke="#f2eee6" strokeWidth="1.5" />
          <path d="M152 92h84" stroke="#f2eee6" strokeWidth="1.2" />
        </svg>
        <span className="player-callout">Sinoatrial node</span>

        <figcaption className="player-caption">“{caption}”</figcaption>
      </div>

      <div className="player-bar">
        <span className="player-play" aria-hidden="true">
          <PlayIcon />
        </span>
        <div className="player-track">
          <div className="player-progress" aria-hidden="true">
            <span />
          </div>
          <ol className="player-chapters">
            {CHAPTERS.map((c, i) => (
              <li key={c}>
                {i + 1} · {c}
              </li>
            ))}
          </ol>
        </div>
        <span className="player-time">1:24 / 3:40</span>
      </div>
    </figure>
  )
}
