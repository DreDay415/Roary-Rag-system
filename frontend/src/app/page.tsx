'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import JSZip from 'jszip'

type Status = 'idle' | 'ingesting' | 'thinking' | 'ready' | 'error'

type TabKey = 'summary' | 'engineer' | 'marketer' | 'ghostwriter'

interface FeedEvent {
  id: number
  status: Status
  message: string
  timestamp: string
}

interface ReportResponse {
  repo_name: string
  github_url: string
  markdown: string
  execution_time_seconds: number
  generated_at: string
  saved_path: string
  engineer_output: string
  marketer_output: string
  ghostwriter_output: string
  critic_output: string
  token_usage: {
    total_tokens: number
    prompt_tokens: number
    completion_tokens: number
    cached_prompt_tokens: number
    successful_requests: number
  }
}

const STATUS_LABELS: Record<Status, string> = {
  idle: 'Idle',
  ingesting: 'Ingesting Repo...',
  thinking: 'Agents Thinking...',
  ready: 'Report Ready',
  error: 'Error',
}

const STATUS_COLORS: Record<Status, string> = {
  idle: 'text-[var(--foreground-muted)]',
  ingesting: 'text-yellow-400',
  thinking: 'text-[var(--neon-blue)]',
  ready: 'text-emerald-400',
  error: 'text-red-400',
}

const STATUS_DOT: Record<Status, string> = {
  idle: 'bg-[var(--foreground-muted)]',
  ingesting: 'bg-yellow-400 animate-pulse',
  thinking: 'bg-[var(--neon-blue)] animate-pulse',
  ready: 'bg-emerald-400',
  error: 'bg-red-400',
}

const TABS: { key: TabKey; label: string; description: string }[] = [
  { key: 'summary', label: 'Summary', description: 'Quality Critic final review + full report' },
  { key: 'engineer', label: 'Lead Engineer', description: 'Technical brief' },
  { key: 'marketer', label: 'Product Marketer', description: 'Value propositions' },
  { key: 'ghostwriter', label: 'Ghostwriter', description: 'LinkedIn thread draft' },
]

function timestamp(): string {
  return new Date().toLocaleTimeString('en-US', { hour12: false })
}

function slugify(name: string): string {
  return name.replace(/[^a-zA-Z0-9_-]/g, '_')
}

export default function RoaryDashboard() {
  const [url, setUrl] = useState('')
  const [status, setStatus] = useState<Status>('idle')
  const [feed, setFeed] = useState<FeedEvent[]>([
    { id: 0, status: 'idle', message: 'Awaiting GitHub URL.', timestamp: timestamp() },
  ])
  const [report, setReport] = useState<ReportResponse | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<TabKey>('summary')
  const feedEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    feedEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [feed])

  function pushFeed(s: Status, message: string) {
    setFeed(prev => [
      ...prev,
      { id: prev.length, status: s, message, timestamp: timestamp() },
    ])
  }

  async function handleGenerate() {
    if (!url.trim() || status === 'ingesting' || status === 'thinking') return

    setStatus('ingesting')
    setReport(null)
    setErrorMessage(null)
    setActiveTab('summary')
    pushFeed('ingesting', `Crawling ${url.trim()}`)

    try {
      await new Promise(r => setTimeout(r, 400))
      setStatus('thinking')
      pushFeed('thinking', 'Newsroom running — Lead Engineer → Marketer → Ghostwriter → Critic')

      const res = await fetch('http://localhost:8000/generate-report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ github_url: url.trim() }),
      })

      if (!res.ok) {
        const text = await res.text()
        throw new Error(`API ${res.status}: ${text}`)
      }

      const data: ReportResponse = await res.json()
      setReport(data)
      setStatus('ready')
      pushFeed(
        'ready',
        `"${data.repo_name}" done — ${data.execution_time_seconds.toFixed(1)}s · ${data.token_usage.total_tokens.toLocaleString()} tokens`,
      )
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Unknown error'
      setStatus('error')
      setErrorMessage(msg)
      pushFeed('error', msg)
    }
  }

  const handleDownloadMd = useCallback(() => {
    if (!report) return
    const blob = new Blob([report.markdown], { type: 'text/markdown' })
    const href = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = href
    a.download = `${slugify(report.repo_name)}_report.md`
    a.click()
    URL.revokeObjectURL(href)
  }, [report])

  const handleDownloadZip = useCallback(async () => {
    if (!report) return
    const zip = new JSZip()
    const folder = zip.folder(slugify(report.repo_name)) ?? zip
    folder.file('engineer.md', `# Lead Engineer — Technical Brief\n\n${report.engineer_output}`)
    folder.file('marketer.md', `# Product Marketer — Value Propositions\n\n${report.marketer_output}`)
    folder.file('ghostwriter.md', `# Ghostwriter — LinkedIn Thread Draft\n\n${report.ghostwriter_output}`)
    folder.file('critic.md', `# Quality Critic — Final Review\n\n${report.critic_output}`)
    folder.file('full_report.md', report.markdown)
    const blob = await zip.generateAsync({ type: 'blob' })
    const href = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = href
    a.download = `${slugify(report.repo_name)}_bundle.zip`
    a.click()
    URL.revokeObjectURL(href)
  }, [report])

  const isLoading = status === 'ingesting' || status === 'thinking'

  function getTabContent(tab: TabKey): string {
    if (!report) return ''
    switch (tab) {
      case 'summary': return report.critic_output?.trim() || report.markdown?.trim() || ''
      case 'engineer': return report.engineer_output?.trim() || ''
      case 'marketer': return report.marketer_output?.trim() || ''
      case 'ghostwriter': return report.ghostwriter_output?.trim() || ''
    }
  }

  return (
    <div className="min-h-screen flex flex-col" style={{ background: 'var(--background)' }}>
      {/* Nav */}
      <nav
        className="flex items-center justify-between px-6 py-4 border-b flex-shrink-0"
        style={{ borderColor: 'var(--border)', background: 'var(--glass-bg)', backdropFilter: 'blur(12px)' }}
      >
        <div className="flex items-center gap-3">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center font-bold text-sm text-white"
            style={{ background: 'var(--neon-blue)', boxShadow: '0 0 12px var(--neon-blue-glow)' }}
          >
            R
          </div>
          <span className="font-semibold tracking-tight" style={{ color: 'var(--foreground)' }}>ROARY</span>
          <span
            className="text-xs px-2 py-0.5 rounded-full font-medium"
            style={{ background: 'var(--neon-blue-dim)', color: 'var(--neon-blue)', border: '1px solid var(--glass-border)' }}
          >
            v0.4.0
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${STATUS_DOT[status]}`} />
          <span className={`text-xs font-medium ${STATUS_COLORS[status]}`}>{STATUS_LABELS[status]}</span>
        </div>
      </nav>

      {/* Main layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <aside
          className="w-80 flex-shrink-0 flex flex-col border-r overflow-y-auto"
          style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}
        >
          {/* Input card */}
          <div
            className="m-4 rounded-2xl p-5"
            style={{
              background: 'var(--glass-bg)',
              border: '1px solid var(--glass-border)',
              backdropFilter: 'blur(16px)',
              boxShadow: '0 0 24px var(--neon-blue-glow)',
            }}
          >
            <h1 className="text-base font-bold mb-1" style={{ color: 'var(--foreground)' }}>
              Repo → Content
            </h1>
            <p className="text-xs mb-4" style={{ color: 'var(--foreground-muted)' }}>
              Paste any public GitHub URL to generate an executive report.
            </p>
            <div className="flex flex-col gap-2">
              <input
                type="url"
                value={url}
                onChange={e => setUrl(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') handleGenerate() }}
                placeholder="https://github.com/owner/repo"
                disabled={isLoading}
                className="w-full rounded-lg px-3 py-2 text-sm outline-none transition-all disabled:opacity-50"
                style={{ background: 'var(--surface-2)', border: '1px solid var(--glass-border)', color: 'var(--foreground)' }}
                onFocus={e => (e.currentTarget.style.borderColor = 'var(--neon-blue)')}
                onBlur={e => (e.currentTarget.style.borderColor = 'var(--glass-border)')}
              />
              <button
                onClick={handleGenerate}
                disabled={isLoading || !url.trim()}
                className="w-full rounded-lg py-2 text-sm font-semibold transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                style={{
                  background: isLoading ? 'var(--neon-blue-dim)' : 'var(--neon-blue)',
                  color: isLoading ? 'var(--neon-blue)' : '#fff',
                  border: '1px solid var(--glass-border)',
                  boxShadow: isLoading ? 'none' : '0 0 16px var(--neon-blue-glow)',
                }}
              >
                {isLoading ? (
                  <span className="flex items-center justify-center gap-2">
                    <Spinner />
                    {status === 'ingesting' ? 'Ingesting…' : 'Agents Running…'}
                  </span>
                ) : (
                  'Generate Report'
                )}
              </button>
            </div>
          </div>

          {/* Download buttons — shown only when ready */}
          {report && status === 'ready' && (
            <div className="px-4 pb-2 flex flex-col gap-2">
              <button
                onClick={handleDownloadMd}
                className="w-full flex items-center justify-center gap-2 rounded-lg py-2 text-xs font-medium transition-all"
                style={{
                  background: 'var(--surface-2)',
                  border: '1px solid var(--border)',
                  color: 'var(--foreground)',
                }}
                onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--neon-blue)')}
                onMouseLeave={e => (e.currentTarget.style.borderColor = 'var(--border)')}
              >
                <IconDownload />
                Download Report (.md)
              </button>
              <button
                onClick={handleDownloadZip}
                className="w-full flex items-center justify-center gap-2 rounded-lg py-2 text-xs font-medium transition-all"
                style={{
                  background: 'var(--surface-2)',
                  border: '1px solid var(--border)',
                  color: 'var(--foreground)',
                }}
                onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--neon-blue)')}
                onMouseLeave={e => (e.currentTarget.style.borderColor = 'var(--border)')}
              >
                <IconArchive />
                Download Bundle (.zip)
              </button>
            </div>
          )}

          {/* Process feed */}
          <div className="flex-1 px-4 pb-4 pt-2">
            <h2
              className="text-xs font-semibold uppercase tracking-widest mb-2"
              style={{ color: 'var(--foreground-muted)' }}
            >
              Process Feed
            </h2>
            <div className="flex flex-col gap-2">
              {feed.map(event => (
                <div
                  key={event.id}
                  className="rounded-lg px-3 py-2 text-xs"
                  style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}
                >
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${STATUS_DOT[event.status]}`} />
                    <span className={`font-medium ${STATUS_COLORS[event.status]}`}>
                      {STATUS_LABELS[event.status]}
                    </span>
                    <span className="ml-auto" style={{ color: 'var(--foreground-muted)' }} suppressHydrationWarning>
                      {event.timestamp}
                    </span>
                  </div>
                  <p style={{ color: 'var(--foreground-muted)' }} className="leading-relaxed">
                    {event.message}
                  </p>
                </div>
              ))}
              <div ref={feedEndRef} />
            </div>
          </div>
        </aside>

        {/* Report viewer */}
        <main className="flex-1 overflow-y-auto p-6">
          {status === 'idle' && !report && <EmptyState />}
          {isLoading && <LoadingState status={status} />}
          {status === 'error' && errorMessage && <ErrorState message={errorMessage} />}
          {report && status === 'ready' && (
            <ReportView
              report={report}
              activeTab={activeTab}
              onTabChange={setActiveTab}
              getTabContent={getTabContent}
            />
          )}
        </main>
      </div>
    </div>
  )
}

/* ── ReportView with tabs ── */

interface ReportViewProps {
  report: ReportResponse
  activeTab: TabKey
  onTabChange: (tab: TabKey) => void
  getTabContent: (tab: TabKey) => string
}

function ReportView({ report, activeTab, onTabChange, getTabContent }: ReportViewProps) {
  const content = getTabContent(activeTab)

  return (
    <div className="max-w-3xl mx-auto">
      {/* Meta bar */}
      <div
        className="flex flex-wrap items-center gap-3 mb-4 rounded-xl px-4 py-3"
        style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
      >
        <span className="font-semibold text-sm" style={{ color: 'var(--foreground)' }}>
          {report.repo_name}
        </span>
        <div className="flex-1" />
        <MetaPill label="Time" value={`${report.execution_time_seconds.toFixed(1)}s`} />
        <MetaPill label="Tokens" value={report.token_usage.total_tokens.toLocaleString()} />
        <MetaPill label="Requests" value={String(report.token_usage.successful_requests)} />
        <MetaPill
          label="Est. Cost"
          value={estimateCost(report.token_usage.prompt_tokens, report.token_usage.completion_tokens)}
          highlight
        />
        <span className="text-xs" style={{ color: 'var(--foreground-muted)' }}>
          {new Date(report.generated_at).toLocaleString()}
        </span>
      </div>

      {/* Tab bar */}
      <div
        className="flex items-center gap-1 mb-4 rounded-xl p-1"
        style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
      >
        {TABS.map(tab => (
          <button
            key={tab.key}
            onClick={() => onTabChange(tab.key)}
            className="flex-1 rounded-lg py-2 px-3 text-xs font-medium transition-all"
            style={{
              background: activeTab === tab.key ? 'var(--neon-blue)' : 'transparent',
              color: activeTab === tab.key ? '#fff' : 'var(--foreground-muted)',
              boxShadow: activeTab === tab.key ? '0 0 12px var(--neon-blue-glow)' : 'none',
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab description + copy button */}
      <div className="flex items-center justify-between mb-3 px-1">
        <span className="text-xs" style={{ color: 'var(--foreground-muted)' }}>
          {TABS.find(t => t.key === activeTab)?.description}
        </span>
        <CopyButton text={content} />
      </div>

      {/* Markdown body */}
      <div
        className="markdown-body rounded-2xl p-6"
        style={{
          background: 'var(--glass-bg)',
          border: '1px solid var(--glass-border)',
          backdropFilter: 'blur(12px)',
        }}
      >
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {content || '## No content received for this agent.'}
        </ReactMarkdown>
      </div>
    </div>
  )
}

/* ── Copy button ── */

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)

  async function handleCopy() {
    if (!text) return
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard API unavailable — silently ignore
    }
  }

  return (
    <button
      onClick={handleCopy}
      className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-all"
      style={{
        background: copied ? 'rgba(52,211,153,0.12)' : 'var(--surface-2)',
        border: `1px solid ${copied ? 'rgba(52,211,153,0.4)' : 'var(--border)'}`,
        color: copied ? 'rgb(52,211,153)' : 'var(--foreground-muted)',
      }}
    >
      {copied ? <IconCheck /> : <IconCopy />}
      {copied ? 'Copied!' : 'Copy'}
    </button>
  )
}

/* ── Utility sub-components ── */

function Spinner() {
  return (
    <svg className="animate-spin w-4 h-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  )
}

/**
 * Blended cost estimate using actual Sonnet 4.5 + Haiku 3.5 pricing on OpenRouter.
 * Sonnet 4.5:  $3/1M input, $15/1M output  (agents 1–3)
 * Haiku 3.5:   $0.25/1M input, $1.25/1M output  (agent 4 critic)
 *
 * We don't know the per-agent token split, so we use a blended average:
 *   ~75% of calls are Sonnet, ~25% are Haiku.
 *   Blended input  = 0.75*3 + 0.25*0.25  ≈ $2.3125/1M
 *   Blended output = 0.75*15 + 0.25*1.25 ≈ $11.5625/1M
 */
function estimateCost(promptTokens: number, completionTokens: number): string {
  const inputCost = (promptTokens / 1_000_000) * 2.3125
  const outputCost = (completionTokens / 1_000_000) * 11.5625
  const total = inputCost + outputCost
  if (total < 0.005) return '<$0.01'
  return `$${total.toFixed(2)}`
}

function MetaPill({ label, value, highlight = false }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div
      className="flex items-center gap-1 rounded-md px-2 py-1 text-xs"
      style={{
        background: highlight ? 'rgba(52,211,153,0.10)' : 'var(--neon-blue-dim)',
        border: `1px solid ${highlight ? 'rgba(52,211,153,0.3)' : 'var(--glass-border)'}`,
      }}
    >
      <span style={{ color: 'var(--foreground-muted)' }}>{label}</span>
      <span className="font-medium" style={{ color: highlight ? 'rgb(52,211,153)' : 'var(--neon-blue)' }}>{value}</span>
    </div>
  )
}

function EmptyState() {
  return (
    <div className="h-full flex flex-col items-center justify-center text-center gap-4 opacity-40">
      <svg width="56" height="56" fill="none" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
        <path
          d="M12 2C6.477 2 2 6.477 2 12c0 4.42 2.87 8.17 6.84 9.5.5.08.66-.23.66-.5v-1.69c-2.77.6-3.36-1.34-3.36-1.34-.46-1.16-1.11-1.47-1.11-1.47-.91-.62.07-.6.07-.6 1 .07 1.53 1.03 1.53 1.03.87 1.52 2.34 1.07 2.91.83.09-.65.35-1.09.63-1.34-2.22-.25-4.55-1.11-4.55-4.92 0-1.11.38-2 1.03-2.71-.1-.25-.45-1.29.1-2.64 0 0 .84-.27 2.75 1.02.79-.22 1.65-.33 2.5-.33.85 0 1.71.11 2.5.33 1.91-1.29 2.75-1.02 2.75-1.02.55 1.35.2 2.39.1 2.64.65.71 1.03 1.6 1.03 2.71 0 3.82-2.34 4.66-4.57 4.91.36.31.69.92.69 1.85V21c0 .27.16.59.67.5C19.14 20.16 22 16.42 22 12A10 10 0 0012 2z"
          fill="currentColor"
        />
      </svg>
      <div>
        <p className="font-semibold text-sm" style={{ color: 'var(--foreground)' }}>No report yet</p>
        <p className="text-xs mt-1" style={{ color: 'var(--foreground-muted)' }}>
          Enter a GitHub URL and click Generate Report.
        </p>
      </div>
    </div>
  )
}

const SKELETON_SECTIONS = [
  { label: 'Headline', width: 'w-2/3', lines: 1 },
  { label: 'The Problem', width: 'w-full', lines: 2 },
  { label: 'What It Does', width: 'w-full', lines: 3 },
  { label: 'Why It Matters', width: 'w-full', lines: 2 },
  { label: 'Get Started', width: 'w-1/2', lines: 1 },
]

function LoadingState({ status }: { status: Status }) {
  return (
    <div className="max-w-3xl mx-auto">
      {/* Skeleton meta bar */}
      <div
        className="flex items-center gap-3 mb-4 rounded-xl px-4 py-3"
        style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
      >
        <div className="h-4 w-32 rounded animate-pulse" style={{ background: 'var(--surface-2)' }} />
        <div className="flex-1" />
        {[56, 72, 64, 52].map((w, i) => (
          <div key={i} className={`h-6 w-${w === 56 ? '14' : w === 72 ? '16' : w === 64 ? '16' : '12'} rounded-md animate-pulse`} style={{ background: 'var(--surface-2)', width: w }} />
        ))}
      </div>

      {/* Skeleton tab bar */}
      <div
        className="flex items-center gap-1 mb-4 rounded-xl p-1"
        style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
      >
        {[0, 1, 2, 3].map(i => (
          <div key={i} className="flex-1 h-8 rounded-lg animate-pulse" style={{ background: i === 0 ? 'var(--neon-blue-dim)' : 'var(--surface-2)', opacity: i === 0 ? 1 : 0.5 }} />
        ))}
      </div>

      {/* Status label */}
      <div className="flex items-center gap-2 mb-3 px-1">
        <div className={`w-2 h-2 rounded-full flex-shrink-0 ${STATUS_DOT[status]}`} />
        <span className={`text-xs font-medium ${STATUS_COLORS[status]}`}>
          {status === 'ingesting' ? 'Crawling repository…' : 'Newsroom agents running…'}
        </span>
      </div>

      {/* Skeleton content card */}
      <div
        className="rounded-2xl p-6"
        style={{
          background: 'var(--glass-bg)',
          border: '1px solid var(--glass-border)',
          backdropFilter: 'blur(12px)',
        }}
      >
        <div className="flex flex-col gap-6">
          {SKELETON_SECTIONS.map((section, si) => (
            <div key={si} className="flex flex-col gap-2">
              {/* Section label */}
              <div className="flex items-center gap-2 mb-1">
                <div className="h-3 w-3 rounded-sm animate-pulse" style={{ background: 'var(--neon-blue-dim)' }} />
                <span className="text-xs font-semibold uppercase tracking-widest" style={{ color: 'var(--foreground-muted)' }}>
                  {section.label}
                </span>
              </div>
              {/* Skeleton lines */}
              {Array.from({ length: section.lines }).map((_, li) => (
                <div
                  key={li}
                  className={`h-4 rounded animate-pulse ${li === section.lines - 1 && section.lines > 1 ? 'w-3/4' : section.width}`}
                  style={{ background: 'var(--surface-2)' }}
                />
              ))}
            </div>
          ))}
        </div>
        <p className="text-xs mt-6 text-center" style={{ color: 'var(--foreground-muted)' }}>
          This typically takes 60–90 seconds…
        </p>
      </div>
    </div>
  )
}

function ErrorState({ message }: { message: string }) {
  return (
    <div
      className="max-w-xl mx-auto mt-16 rounded-2xl p-6"
      style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.3)' }}
    >
      <h3 className="font-semibold text-red-400 mb-2">Generation Failed</h3>
      <p className="text-sm font-mono break-all" style={{ color: 'var(--foreground-muted)' }}>{message}</p>
      <p className="text-xs mt-3" style={{ color: 'var(--foreground-muted)' }}>
        Make sure the ROARY backend is running on{' '}
        <code className="px-1 py-0.5 rounded" style={{ background: 'var(--surface-2)', color: 'var(--neon-blue)' }}>
          localhost:8000
        </code>{' '}
        and the URL is a public GitHub repo.
      </p>
    </div>
  )
}

/* ── Icons ── */

function IconDownload() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  )
}

function IconArchive() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="21 8 21 21 3 21 3 8" />
      <rect x="1" y="3" width="22" height="5" />
      <line x1="10" y1="12" x2="14" y2="12" />
    </svg>
  )
}

function IconCopy() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
      <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
    </svg>
  )
}

function IconCheck() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  )
}
