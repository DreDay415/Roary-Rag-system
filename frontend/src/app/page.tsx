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

interface HistoryItem {
  id: string
  type: 'report' | 'chat'
  repo_name: string
  title: string
  github_url: string
  generated_at: string
}

interface ChatResponse {
  type: 'chat'
  repo_name: string
  question: string
  answer: string
  sources: string[]
  generated_at: string
}

export default function RoaryDashboard() {
  const [url, setUrl] = useState('')
  const [question, setQuestion] = useState('')
  const [status, setStatus] = useState<Status>('idle')
  const [feed, setFeed] = useState<FeedEvent[]>([
    { id: 0, status: 'idle', message: 'Awaiting GitHub URL.', timestamp: timestamp() },
  ])
  const [report, setReport] = useState<ReportResponse | null>(null)
  const [chat, setChat] = useState<ChatResponse | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<TabKey>('summary')
  const [showSidebar, setShowSidebar] = useState(false)
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [isHistoryLoading, setIsHistoryLoading] = useState(false)
  
  const feedEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    feedEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [feed])

  // Initial fetch
  useEffect(() => {
    fetchHistory()
  }, [])

  // Close sidebar on mobile when report is ready
  useEffect(() => {
    if ((status === 'ready' || status === 'error') && typeof window !== 'undefined' && window.innerWidth < 1024) {
      setShowSidebar(false)
    }
  }, [status])

  async function fetchHistory() {
    setIsHistoryLoading(true)
    try {
      const backendUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      const res = await fetch(`${backendUrl}/history`)
      if (res.ok) {
        const data = await res.json()
        setHistory(data)
      }
    } catch (err) {
      console.error('Failed to fetch history:', err)
    } finally {
      setIsHistoryLoading(false)
    }
  }

  async function loadFromHistory(item: HistoryItem) {
    setStatus('thinking')
    pushFeed('thinking', `Loading archive: ${item.title}...`)
    setReport(null)
    setChat(null)
    
    // Close sidebar on mobile
    if (typeof window !== 'undefined' && window.innerWidth < 1024) {
      setShowSidebar(false)
    }

    try {
      const backendUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      const res = await fetch(`${backendUrl}/history/${item.id}`)
      if (!res.ok) throw new Error(`Could not load item: ${res.statusText}`)
      
      const data = await res.json()
      if (data.type === 'chat') {
        setChat(data)
      } else {
        setReport(data)
        setActiveTab('summary')
      }
      setStatus('ready')
      pushFeed('ready', `Restored ${item.type} for "${item.repo_name}" from vault.`)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load archive'
      setStatus('error')
      setErrorMessage(msg)
      pushFeed('error', msg)
    }
  }

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
    setChat(null)
    setErrorMessage(null)
    setActiveTab('summary')
    pushFeed('ingesting', `Crawling ${url.trim()}`)

    try {
      await new Promise(r => setTimeout(r, 400))
      setStatus('thinking')
      pushFeed('thinking', 'Newsroom running — Lead Engineer → Marketer → Ghostwriter → Critic')

      const backendUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      const res = await fetch(`${backendUrl}/generate-report`, {
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
        `"${data.repo_name}" report done — ${data.execution_time_seconds.toFixed(1)}s`
      )
      
      // Refresh history after a successful run
      fetchHistory()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Unknown error'
      setStatus('error')
      setErrorMessage(msg)
      pushFeed('error', msg)
    }
  }

  async function handleChat() {
    if (!question.trim() || !url.trim() || status === 'ingesting' || status === 'thinking') return

    const currentUrl = url.trim()
    const currentQuestion = question.trim()
    
    setStatus('thinking')
    setReport(null)
    setChat(null)
    setErrorMessage(null)
    setQuestion('')
    pushFeed('thinking', `Querying Roary: "${currentQuestion}"`)

    try {
      const backendUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      const res = await fetch(`${backendUrl}/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ github_url: currentUrl, question: currentQuestion }),
      })

      if (!res.ok) {
        const text = await res.text()
        throw new Error(`Chat API ${res.status}: ${text}`)
      }

      const data: ChatResponse = await res.json()
      setChat(data)
      setStatus('ready')
      pushFeed('ready', 'Roary has answered.')
      
      fetchHistory()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Chat failed'
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
        className="flex items-center justify-between px-4 lg:px-6 py-4 border-b flex-shrink-0 sticky top-0 z-50"
        style={{ borderColor: 'var(--border)', background: 'var(--glass-bg)', backdropFilter: 'blur(12px)' }}
      >
        <div className="flex items-center gap-3">
          <button 
            onClick={() => setShowSidebar(!showSidebar)}
            className="lg:hidden p-2 -ml-2 rounded-lg hover:bg-[var(--surface-2)] transition-colors"
            style={{ color: 'var(--foreground)' }}
          >
            <IconMenu />
          </button>
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center font-bold text-sm text-white"
            style={{ background: 'var(--neon-blue)', boxShadow: '0 0 12px var(--neon-blue-glow)' }}
          >
            R
          </div>
          <span className="font-semibold tracking-tight" style={{ color: 'var(--foreground)' }}>ROARY</span>
        </div>
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${STATUS_DOT[status]}`} />
          <span className={`text-xs font-medium ${STATUS_COLORS[status]}`}>{STATUS_LABELS[status]}</span>
        </div>
      </nav>

      {/* Main layout */}
      <div className="flex flex-1 overflow-hidden relative">
        {/* Sidebar */}
        <aside
          className={`
            fixed inset-y-0 left-0 z-40 w-80 transform transition-transform duration-300 ease-in-out lg:relative lg:translate-x-0
            flex flex-col border-r overflow-y-auto
            ${showSidebar ? 'translate-x-0' : '-translate-x-full'}
          `}
          style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}
        >
          {/* Main Actions */}
          <div className="p-4 flex flex-col gap-4">
            {/* Report card */}
            <div
              className="rounded-2xl p-5"
              style={{
                background: 'var(--glass-bg)',
                border: '1px solid var(--glass-border)',
                backdropFilter: 'blur(16px)',
                boxShadow: url ? '0 0 24px var(--neon-blue-glow)' : 'none',
              }}
            >
              <h1 className="text-base font-bold mb-1" style={{ color: 'var(--foreground)' }}>
                Repo → Content
              </h1>
              <p className="text-xs mb-4" style={{ color: 'var(--foreground-muted)' }}>
                Paste a GitHub URL to generate reports.
              </p>
              <div className="flex flex-col gap-2">
                <input
                  type="url"
                  value={url}
                  onChange={e => setUrl(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') handleGenerate() }}
                  placeholder="https://github.com/..."
                  disabled={isLoading}
                  className="w-full rounded-lg px-3 py-3 text-sm outline-none transition-all disabled:opacity-50"
                  style={{ background: 'var(--surface-2)', border: '1px solid var(--glass-border)', color: 'var(--foreground)' }}
                  onFocus={e => (e.currentTarget.style.borderColor = 'var(--neon-blue)')}
                  onBlur={e => (e.currentTarget.style.borderColor = 'var(--glass-border)')}
                />
                <button
                  onClick={handleGenerate}
                  disabled={isLoading || !url.trim()}
                  className="w-full rounded-lg py-3 text-sm font-semibold transition-all disabled:opacity-40 disabled:cursor-not-allowed active:scale-[0.98]"
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
                      {status === 'ingesting' ? 'Ingesting…' : 'Thinking…'}
                    </span>
                  ) : (
                    'Generate Report'
                  )}
                </button>
              </div>
            </div>

            {/* Chat card */}
            <div
              className="rounded-2xl p-5"
              style={{
                background: 'var(--glass-bg)',
                border: '1px solid var(--glass-border)',
                backdropFilter: 'blur(16px)',
              }}
            >
              <h2 className="text-base font-bold mb-1" style={{ color: 'var(--foreground)' }}>
                Ask Roary (RAG)
              </h2>
              <p className="text-xs mb-4" style={{ color: 'var(--foreground-muted)' }}>
                Query the repo documentation directly.
              </p>
              <div className="flex flex-col gap-2">
                <textarea
                  value={question}
                  onChange={e => setQuestion(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleChat() } }}
                  placeholder="What is the architecture?"
                  disabled={isLoading || !url.trim()}
                  className="w-full rounded-lg px-3 py-3 text-sm outline-none transition-all disabled:opacity-50 resize-none h-20"
                  style={{ background: 'var(--surface-2)', border: '1px solid var(--glass-border)', color: 'var(--foreground)' }}
                  onFocus={e => (e.currentTarget.style.borderColor = 'var(--neon-blue)')}
                  onBlur={e => (e.currentTarget.style.borderColor = 'var(--glass-border)')}
                />
                <button
                  onClick={handleChat}
                  disabled={isLoading || !url.trim() || !question.trim()}
                  className="w-full rounded-lg py-2 text-xs font-semibold transition-all disabled:opacity-40 disabled:cursor-not-allowed active:scale-[0.98]"
                  style={{
                    border: '1px solid var(--neon-blue)',
                    color: 'var(--neon-blue)',
                    background: 'transparent'
                  }}
                >
                  {isLoading ? <Spinner /> : 'Ask Question'}
                </button>
              </div>
            </div>
          </div>

          {/* Download buttons — shown only when report ready */}
          {report && status === 'ready' && (
            <div className="px-4 pb-4 flex flex-col gap-2">
              <button
                onClick={handleDownloadMd}
                className="w-full flex items-center justify-center gap-2 rounded-lg py-3 text-xs font-medium transition-all active:bg-[var(--surface-2)]"
                style={{
                  background: 'var(--surface-2)',
                  border: '1px solid var(--border)',
                  color: 'var(--foreground)',
                }}
              >
                <IconDownload />
                Download Report (.md)
              </button>
              <button
                onClick={handleDownloadZip}
                className="w-full flex items-center justify-center gap-2 rounded-lg py-3 text-xs font-medium transition-all active:bg-[var(--surface-2)]"
                style={{
                  background: 'var(--surface-2)',
                  border: '1px solid var(--border)',
                  color: 'var(--foreground)',
                }}
              >
                <IconArchive />
                Download Bundle (.zip)
              </button>
            </div>
          )}

          {/* History Section */}
          {history.length > 0 && (
            <div className="px-4 pb-4">
              <h2
                className="text-xs font-semibold uppercase tracking-widest mb-3 flex items-center gap-2 px-1"
                style={{ color: 'var(--foreground-muted)' }}
              >
                <IconHistory />
                Vault Cache
              </h2>
              <div className="flex flex-col gap-2">
                {history.map(item => (
                  <button
                    key={item.id}
                    onClick={() => loadFromHistory(item)}
                    className={`w-full text-left rounded-lg p-3 text-xs transition-all group border ${item.type === 'chat' ? 'border-dashed' : 'border-solid'}`}
                    style={{ background: 'var(--surface-2)', borderColor: 'var(--border)' }}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className={`font-semibold truncate pr-2 group-hover:text-[var(--neon-blue)] ${item.type === 'chat' ? 'text-[var(--neon-blue)]' : ''}`} style={{ color: item.type === 'chat' ? 'var(--neon-blue)' : 'var(--foreground)' }}>
                        {item.title}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-[10px]" style={{ color: 'var(--foreground-muted)' }}>
                      <span className="truncate">{item.repo_name}</span>
                      <span>{new Date(item.generated_at).toLocaleDateString([], { month: 'short', day: 'numeric' })}</span>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Pipeline feed */}
          <div className="flex-1 px-4 pb-4 pt-2">
            <h2
              className="text-xs font-semibold uppercase tracking-widest mb-2 px-1"
              style={{ color: 'var(--foreground-muted)' }}
            >
              Pipeline Log
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

        {/* Viewport */}
        <main className="flex-1 flex flex-col overflow-hidden">
          {status === 'idle' && !errorMessage && !report && !chat && (
            <div className="flex-1 flex flex-col items-center justify-center p-6 text-center">
              <div className="w-16 h-16 rounded-2xl mb-6 flex items-center justify-center opacity-20" style={{ background: 'var(--foreground)' }}>
                <IconGitHub size={32} />
              </div>
              <h2 className="text-xl font-bold mb-2" style={{ color: 'var(--foreground)' }}>No content yet</h2>
              <p className="max-w-xs text-sm" style={{ color: 'var(--foreground-muted)' }}>
                Enter a GitHub URL and click Generate Report or ask a question to begin analysis.
              </p>
            </div>
          )}

          {(status === 'ingesting' || status === 'thinking') && !report && !chat && (
            <div className="flex-1 overflow-y-auto p-4 lg:p-8">
              <LoadingState status={status} />
            </div>
          )}

          {errorMessage && (
            <div className="m-6 p-4 rounded-xl border flex items-center gap-3" style={{ background: 'var(--error-bg)', borderColor: 'var(--red)', color: 'var(--red)' }}>
              <IconAlert />
              <div className="text-sm font-medium">{errorMessage}</div>
            </div>
          )}

          {/* Chat Result */}
          {chat && status === 'ready' && (
            <div className="flex-1 overflow-y-auto p-4 lg:p-8">
              <div className="max-w-3xl mx-auto flex flex-col gap-6">
                <div className="p-6 rounded-2xl border" style={{ background: 'var(--surface-2)', borderColor: 'var(--border)' }}>
                  <div className="flex items-center gap-2 mb-4 text-[var(--neon-blue)] text-sm font-bold uppercase tracking-wider">
                    <IconHistory /> Question
                  </div>
                  <h2 className="text-xl font-bold mb-2" style={{ color: 'var(--foreground)' }}>{chat.question}</h2>
                  <div className="flex items-center gap-3 text-xs" style={{ color: 'var(--foreground-muted)' }}>
                    <span>{chat.repo_name}</span>
                    <span>•</span>
                    <span>{new Date(chat.generated_at).toLocaleString()}</span>
                  </div>
                </div>

                <div className="p-8 rounded-3xl" style={{ background: 'var(--glass-bg)', border: '1px solid var(--glass-border)', boxShadow: '0 8px 32px rgba(0,0,0,0.5)' }}>
                  <div className="flex items-center gap-2 mb-6 text-[var(--neon-blue)] text-sm font-bold uppercase tracking-wider">
                    <div className="w-6 h-6 rounded flex items-center justify-center text-white text-[10px]" style={{ background: 'var(--neon-blue)' }}>R</div>
                    Roary Response
                  </div>
                  <div className="prose prose-invert max-w-none prose-p:leading-relaxed prose-pre:bg-[var(--black)] prose-pre:border prose-pre:border-[var(--border)]">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{chat.answer}</ReactMarkdown>
                  </div>
                  {chat.sources && chat.sources.length > 0 && (
                    <div className="mt-8 pt-6 border-t flex flex-wrap gap-2" style={{ borderColor: 'var(--border)' }}>
                      <span className="text-[10px] uppercase font-bold tracking-widest block w-full mb-2" style={{ color: 'var(--foreground-muted)' }}>Sources (README Chunks)</span>
                      {chat.sources.map((s, i) => (
                        <span key={i} className="px-2 py-1 rounded text-[10px] font-mono" style={{ background: 'var(--surface-2)', color: 'var(--neon-blue)', border: '1px solid var(--glass-border)' }}>
                          chunk_{s}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Report View */}
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
        className="flex flex-wrap items-center gap-2 sm:gap-3 mb-4 rounded-xl px-4 py-3"
        style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
      >
        <div className="w-full sm:w-auto mb-2 sm:mb-0">
          <span className="font-semibold text-sm block truncate" style={{ color: 'var(--foreground)' }}>
            {report.repo_name}
          </span>
          <span className="text-[10px] sm:text-xs" style={{ color: 'var(--foreground-muted)' }}>
            {new Date(report.generated_at).toLocaleString()}
          </span>
        </div>
        <div className="hidden sm:block flex-1" />
        <div className="flex flex-wrap items-center gap-2">
          <MetaPill label="Time" value={`${report.execution_time_seconds.toFixed(1)}s`} />
          <MetaPill label="Tokens" value={report.token_usage.total_tokens.toLocaleString()} />
          <MetaPill label="Reqs" value={String(report.token_usage.successful_requests)} />
          <MetaPill
            label="Cost"
            value={estimateCost(report.token_usage.prompt_tokens, report.token_usage.completion_tokens)}
            highlight
          />
        </div>
      </div>

      {/* Tab bar */}
      <div
        className="flex items-center gap-1 mb-4 rounded-xl p-1 overflow-x-auto no-scrollbar"
        style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
      >
        {TABS.map(tab => (
          <button
            key={tab.key}
            onClick={() => onTabChange(tab.key)}
            className="flex-1 whitespace-nowrap rounded-lg py-2.5 px-3 text-xs font-medium transition-all active:scale-[0.95]"
            style={{
              background: activeTab === tab.key ? 'var(--neon-blue)' : 'transparent',
              color: activeTab === tab.key ? '#fff' : 'var(--foreground-muted)',
              boxShadow: activeTab === tab.key ? '0 0 12px var(--neon-blue-glow)' : 'none',
              minWidth: '90px'
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab description + copy button */}
      <div className="flex items-center justify-between mb-4 px-1 gap-4">
        <span className="text-xs leading-tight" style={{ color: 'var(--foreground-muted)' }}>
          {TABS.find(t => t.key === activeTab)?.description}
        </span>
        <CopyButton text={content} />
      </div>

      {/* Markdown body */}
      <div
        className="markdown-body rounded-2xl p-5 sm:p-6"
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
      className="flex items-center gap-1.5 rounded-lg px-3 py-2.5 text-xs font-medium transition-all active:scale-[0.95]"
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
      className="flex items-center gap-1 rounded-md px-2 py-1 text-[10px] sm:text-xs"
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
    <div className="h-full flex flex-col items-center justify-center text-center gap-4 opacity-40 px-6">
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

/* ── 3D Cube Loader ── */

function CubeLoader() {
  return (
    <div className="flex items-center justify-center mb-12" style={{ perspective: '1200px' }}>
      <div className="cube-container">
        {[...Array(6)].map((_, i) => (
          <div key={i} className="side" />
        ))}
      </div>
    </div>
  )
}

function LoadingState({ status }: { status: Status }) {
  return (
    <div className="max-w-3xl mx-auto">
      {/* Skeleton meta bar — 20% opacity, secondary element */}
      <div
        className="flex items-center gap-3 mb-4 rounded-xl px-4 py-3"
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', opacity: 0.2 }}
      >
        <div className="h-4 w-32 rounded animate-pulse" style={{ background: 'var(--surface-2)' }} />
        <div className="flex-1" />
        {[56, 72, 64, 52].map((w, i) => (
          <div key={i} className="h-6 rounded-md animate-pulse" style={{ background: 'var(--surface-2)', width: w }} />
        ))}
      </div>

      {/* Skeleton tab bar — 20% opacity */}
      <div
        className="flex items-center gap-1 mb-4 rounded-xl p-1"
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', opacity: 0.2 }}
      >
        {[0, 1, 2, 3].map(i => (
          <div key={i} className="flex-1 h-8 rounded-lg animate-pulse" style={{ background: i === 0 ? 'var(--neon-blue-dim)' : 'var(--surface-2)' }} />
        ))}
      </div>

      {/* Primary focus: cube + status */}
      <div className="flex flex-col items-center gap-4 py-6 px-4">
        <CubeLoader />
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full flex-shrink-0 ${STATUS_DOT[status]}`} />
          <span className={`text-xs font-medium ${STATUS_COLORS[status]}`}>
            {status === 'ingesting' ? 'Crawling repository…' : 'Newsroom agents running…'}
          </span>
        </div>
      </div>

      {/* Skeleton content card — 20% opacity */}
      <div
        className="rounded-2xl p-6"
        style={{
          background: 'var(--glass-bg)',
          border: '1px solid var(--glass-border)',
          backdropFilter: 'blur(12px)',
          opacity: 0.2,
        }}
      >
        <div className="flex flex-col gap-6">
          {SKELETON_SECTIONS.map((section, si) => (
            <div key={si} className="flex flex-col gap-2">
              <div className="flex items-center gap-2 mb-1">
                <div className="h-3 w-3 rounded-sm animate-pulse" style={{ background: 'var(--neon-blue-dim)' }} />
                <span className="text-xs font-semibold uppercase tracking-widest" style={{ color: 'var(--foreground-muted)' }}>
                  {section.label}
                </span>
              </div>
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
      className="max-w-xl mx-auto mt-8 sm:mt-16 rounded-2xl p-6"
      style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.3)' }}
    >
      <h3 className="font-semibold text-red-400 mb-2">Generation Failed</h3>
      <p className="text-sm font-mono break-all" style={{ color: 'var(--foreground-muted)' }}>{message}</p>
      <p className="text-xs mt-3" style={{ color: 'var(--foreground-muted)' }}>
        Make sure the backend is reachable and the URL is public.
      </p>
    </div>
  )
}

/* ── Icons ── */

function IconGitHub({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4" />
      <path d="M9 18c-4.51 2-5-2-7-2" />
    </svg>
  )
}

function IconHistory() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 8v4l3 3" />
      <path d="M3.05 11a9 9 0 1 1 .5 4m-.5 5v-5h5" />
    </svg>
  )
}

function IconMenu() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="3" y1="12" x2="21" y2="12" />
      <line x1="3" y1="6" x2="21" y2="6" />
      <line x1="3" y1="18" x2="21" y2="18" />
    </svg>
  )
}

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
