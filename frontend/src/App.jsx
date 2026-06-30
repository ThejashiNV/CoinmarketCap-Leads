import { useCallback, useEffect, useRef, useState } from "react"

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000"

const SUPPORTED_DOMAINS = ["coinmarketcap.com", "coingecko.com", "coinranking.com", "defillama.com"]
const PLATFORM_OPTIONS = ["CoinMarketCap", "CoinGecko", "Coinranking", "DeFiLlama Raises"]

const PLATFORM_LISTING_URL = {
  "DeFiLlama Raises": "https://defillama.com/raises",
}

// Platforms that expose a fixed listing URL rather than user-selectable categories.
const LISTING_ONLY_PLATFORMS = new Set(["DeFiLlama Raises"])
const TOP_N_OPTIONS = [10, 20, 50, 100, 250]

// ─── Helpers ──────────────────────────────────────────────────────────────────

function validateCategoryUrl(value) {
  const url = (value || "").trim()
  if (!url) return "Please enter a platform category URL."
  let parsed
  try { parsed = new URL(url) } catch { return "Not a valid URL." }
  if (!/^https?:$/.test(parsed.protocol)) return "URL must start with http:// or https://"
  const host = parsed.hostname.replace(/^www\./, "")
  if (!SUPPORTED_DOMAINS.some((d) => host === d || host.endsWith("." + d)))
    return "Unsupported platform. Use CoinMarketCap, CoinGecko, Coinranking, or DeFiLlama Raises."
  // DeFiLlama: only /raises is a valid listing URL
  if (host === "defillama.com") {
    if (!parsed.pathname.startsWith("/raises"))
      return "For DeFiLlama, use https://defillama.com/raises"
    return ""
  }
  // Accept any non-root listing path: /view/*, /cryptocurrency-category/*, /categories/*, /coins, /tags
  if (!parsed.pathname || parsed.pathname === "/")
    return "Enter a category listing URL, not just the homepage."
  return ""
}

function leadScore(lead) {
  const has = (f) => lead[f] && lead[f] !== "N/A" && lead[f] !== ""
  let s = 0
  if (has("Official Website URL"))  s += 15
  if (has("Official Email IDs"))    s += 30
  if (has("LinkedIn URLs"))         s += 20
  if (has("Telegram URLs"))         s += 10
  if (has("GitHub URLs"))           s += 10
  if (has("Founder Name"))          s += 10
  if (has("Founder LinkedIn"))      s += 5
  return s
}

function leadGrade(score) {
  if (score >= 90) return { label: "A+", bg: "bg-emerald-500/15", text: "text-emerald-400", border: "border-emerald-500/30" }
  if (score >= 70) return { label: "A",  bg: "bg-green-500/15",   text: "text-green-400",   border: "border-green-500/30" }
  if (score >= 50) return { label: "B",  bg: "bg-sky-500/15",     text: "text-sky-400",     border: "border-sky-500/30" }
  if (score >= 30) return { label: "C",  bg: "bg-amber-500/15",   text: "text-amber-400",   border: "border-amber-500/30" }
  return             { label: "D",  bg: "bg-red-500/15",     text: "text-red-400",     border: "border-red-500/30" }
}

function fmtUrl(raw) {
  if (!raw || raw === "N/A") return null
  const first = String(raw).split(";")[0].trim()
  if (!/^https?:\/\//.test(first)) return null
  try {
    const u = new URL(first)
    let label = u.hostname.replace(/^www\./, "") + (u.pathname !== "/" ? u.pathname : "")
    if (label.length > 32) label = label.slice(0, 30) + "…"
    return { href: first, label }
  } catch { return null }
}

function fmtEta(sec) {
  if (!sec || sec <= 0) return null
  if (sec < 60) return `${sec}s`
  return `${Math.floor(sec / 60)}m ${sec % 60}s`
}

// ─── Canvas particle background ───────────────────────────────────────────────

function ParticleCanvas() {
  const ref = useRef(null)
  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const ctx = canvas.getContext("2d")
    let raf

    const resize = () => {
      canvas.width = canvas.offsetWidth
      canvas.height = canvas.offsetHeight
    }
    resize()
    window.addEventListener("resize", resize)

    const COUNT = 55
    const particles = Array.from({ length: COUNT }, () => ({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height,
      vx: (Math.random() - 0.5) * 0.25,
      vy: (Math.random() - 0.5) * 0.25,
      r: Math.random() * 1.5 + 0.5,
    }))

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      for (const p of particles) {
        p.x = (p.x + p.vx + canvas.width) % canvas.width
        p.y = (p.y + p.vy + canvas.height) % canvas.height
      }
      for (let i = 0; i < COUNT; i++) {
        for (let j = i + 1; j < COUNT; j++) {
          const dx = particles[i].x - particles[j].x
          const dy = particles[i].y - particles[j].y
          const d = Math.sqrt(dx * dx + dy * dy)
          if (d < 110) {
            ctx.beginPath()
            ctx.strokeStyle = `rgba(99,102,241,${0.12 * (1 - d / 110)})`
            ctx.lineWidth = 0.6
            ctx.moveTo(particles[i].x, particles[i].y)
            ctx.lineTo(particles[j].x, particles[j].y)
            ctx.stroke()
          }
        }
        ctx.beginPath()
        ctx.arc(particles[i].x, particles[i].y, particles[i].r, 0, Math.PI * 2)
        ctx.fillStyle = "rgba(139,92,246,0.35)"
        ctx.fill()
      }
      raf = requestAnimationFrame(draw)
    }
    draw()
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener("resize", resize)
    }
  }, [])
  return <canvas ref={ref} className="absolute inset-0 w-full h-full pointer-events-none" />
}

// ─── Design tokens ────────────────────────────────────────────────────────────

const card = "bg-white/[0.03] border border-white/[0.07] rounded-2xl backdrop-blur-sm"
const inputCls = "w-full bg-black/40 border border-white/[0.08] rounded-xl px-4 py-2.5 text-sm text-white placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-violet-500/40 focus:border-violet-500/40 disabled:opacity-40 transition-all"
const labelCls = "block text-slate-500 text-[11px] font-semibold uppercase tracking-widest mb-1.5"
const btnPrimary = "inline-flex items-center gap-2 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white font-semibold text-sm px-6 py-2.5 rounded-xl shadow-lg shadow-violet-500/20 hover:shadow-violet-500/30 transition-all duration-200 disabled:opacity-40 disabled:shadow-none"
const btnGhost = "inline-flex items-center gap-2 bg-white/[0.05] hover:bg-white/[0.09] border border-white/[0.08] text-slate-300 hover:text-white font-medium text-xs px-4 py-2 rounded-lg transition-all"

// ─── Icons ────────────────────────────────────────────────────────────────────

const Ic = {
  Rocket: () => (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M15.59 14.37a6 6 0 01-5.84 7.38v-4.8m5.84-2.58a14.98 14.98 0 003.46-8.62 2.25 2.25 0 00-1.93-2.32 14.98 14.98 0 00-8.62 3.46m5.09 7.48V16.5a2.25 2.25 0 00-2.25 2.25H9a2.25 2.25 0 00-2.25-2.25v-2.13m5.84-2.58L9.41 9.63m0 0a5.98 5.98 0 00-7.38 5.84h4.8m2.58-5.84v-.13A2.25 2.25 0 0111.66 7.5h.13" />
    </svg>
  ),
  Download: () => (
    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
    </svg>
  ),
  Terminal: () => (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 7.5l3 2.25-3 2.25m4.5 0h3m-9 8.25h13.5A2.25 2.25 0 0021 18V6a2.25 2.25 0 00-2.25-2.25H5.25A2.25 2.25 0 003 6v12a2.25 2.25 0 002.25 2.25z" />
    </svg>
  ),
  Table: () => (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.375 19.5h17.25m-17.25 0a1.125 1.125 0 01-1.125-1.125M3.375 19.5h7.5c.621 0 1.125-.504 1.125-1.125m-9.75 0V5.625m0 12.75v-1.5c0-.621.504-1.125 1.125-1.125m18.375 2.625V5.625m0 12.75c0 .621-.504 1.125-1.125 1.125m1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125m0 3.75h-7.5A1.125 1.125 0 0112 18.375m9.75-12.75c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125m19.5 0v1.5c0 .621-.504 1.125-1.125 1.125M2.25 5.625v1.5c0 .621.504 1.125 1.125 1.125m0 0h17.25m-17.25 0h7.5c.621 0 1.125.504 1.125 1.125M3.375 8.25c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125m17.25-3.75h-7.5c-.621 0-1.125.504-1.125 1.125m8.625-1.125c.621 0 1.125.504 1.125 1.125v1.5c0 .621-.504 1.125-1.125 1.125m-17.25 0h7.5" />
    </svg>
  ),
  Grid: () => (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z" />
    </svg>
  ),
  Chart: () => (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
    </svg>
  ),
  Search: () => (
    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
    </svg>
  ),
  ChevronUp: () => (
    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 15.75l7.5-7.5 7.5 7.5" />
    </svg>
  ),
  ChevronDown: () => (
    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
    </svg>
  ),
  Copy: () => (
    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 17.25v3.375c0 .621-.504 1.125-1.125 1.125h-9.75a1.125 1.125 0 01-1.125-1.125V7.875c0-.621.504-1.125 1.125-1.125H6.75a9.06 9.06 0 011.5.124m7.5 10.376h3.375c.621 0 1.125-.504 1.125-1.125V11.25c0-4.46-3.243-8.161-7.5-8.876a9.06 9.06 0 00-1.5-.124H9.375c-.621 0-1.125.504-1.125 1.125v3.5m7.5 10.375H9.375a1.125 1.125 0 01-1.125-1.125v-9.25m12 6.625v-1.875a3.375 3.375 0 00-3.375-3.375h-1.5a1.125 1.125 0 01-1.125-1.125v-1.5a3.375 3.375 0 00-3.375-3.375H9.75" />
    </svg>
  ),
  Stop: () => (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 7.5A2.25 2.25 0 017.5 5.25h9a2.25 2.25 0 012.25 2.25v9a2.25 2.25 0 01-2.25 2.25h-9a2.25 2.25 0 01-2.25-2.25v-9z" />
    </svg>
  ),
  Spinner: () => (
    <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  ),
}

// ─── Stat card ────────────────────────────────────────────────────────────────

function StatCard({ label, value, sub, accent = "violet" }) {
  const colors = {
    violet: "from-violet-500/20 to-violet-500/5 border-violet-500/20",
    indigo: "from-indigo-500/20 to-indigo-500/5 border-indigo-500/20",
    emerald: "from-emerald-500/20 to-emerald-500/5 border-emerald-500/20",
    amber:   "from-amber-500/20 to-amber-500/5 border-amber-500/20",
    sky:     "from-sky-500/20 to-sky-500/5 border-sky-500/20",
  }
  const textColors = {
    violet: "text-violet-300", indigo: "text-indigo-300",
    emerald: "text-emerald-300", amber: "text-amber-300", sky: "text-sky-300",
  }
  return (
    <div className={`bg-gradient-to-br ${colors[accent]} border rounded-2xl p-5`}>
      <p className="text-slate-500 text-xs font-semibold uppercase tracking-widest mb-3">{label}</p>
      <p className={`text-3xl font-black ${textColors[accent]} tracking-tight`}>{value}</p>
      {sub && <p className="text-slate-600 text-xs mt-1">{sub}</p>}
    </div>
  )
}

// ─── Coverage bar ─────────────────────────────────────────────────────────────

function CoverageBar({ label, pct, color = "violet" }) {
  const bar = {
    violet: "bg-violet-500", indigo: "bg-indigo-500",
    emerald: "bg-emerald-500", sky: "bg-sky-500", amber: "bg-amber-500",
  }
  return (
    <div>
      <div className="flex justify-between items-center mb-1.5">
        <span className="text-slate-400 text-xs">{label}</span>
        <span className="text-slate-300 text-xs font-semibold">{pct}%</span>
      </div>
      <div className="h-1.5 bg-white/[0.05] rounded-full overflow-hidden">
        <div
          className={`h-full ${bar[color]} rounded-full transition-all duration-700`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

// ─── Progress ring ────────────────────────────────────────────────────────────

function ProgressRing({ pct, size = 120, stroke = 8 }) {
  const r = (size - stroke) / 2
  const circ = 2 * Math.PI * r
  const dash = circ - (pct / 100) * circ
  return (
    <svg width={size} height={size} className="rotate-[-90deg]">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none"
        stroke="rgba(255,255,255,0.04)" strokeWidth={stroke} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none"
        stroke="url(#ring-grad)" strokeWidth={stroke}
        strokeDasharray={circ} strokeDashoffset={dash}
        strokeLinecap="round"
        style={{ transition: "stroke-dashoffset 0.6s ease" }}
      />
      <defs>
        <linearGradient id="ring-grad" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#8b5cf6" />
          <stop offset="100%" stopColor="#6366f1" />
        </linearGradient>
      </defs>
    </svg>
  )
}

// ─── Table cell renderers ─────────────────────────────────────────────────────

function LinkCell({ value }) {
  const parsed = fmtUrl(value)
  if (!parsed) return <span className="text-slate-700 text-xs">—</span>
  return (
    <a href={parsed.href} target="_blank" rel="noreferrer"
      className="text-sky-400/80 hover:text-sky-300 text-xs transition-colors truncate block max-w-[150px]"
      title={parsed.href}>
      {parsed.label}
    </a>
  )
}

function EmailCell({ value }) {
  const [copied, setCopied] = useState(false)
  if (!value || value === "N/A") return <span className="text-slate-700 text-xs">—</span>
  const copy = () => {
    navigator.clipboard?.writeText(value)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }
  return (
    <div className="flex items-center gap-1.5 group">
      <span className="text-emerald-400/90 text-xs font-medium truncate max-w-[160px]" title={value}>{value}</span>
      <button onClick={copy}
        className="opacity-0 group-hover:opacity-100 text-slate-500 hover:text-slate-300 transition-all">
        {copied ? <span className="text-emerald-400 text-[10px]">✓</span> : <Ic.Copy />}
      </button>
    </div>
  )
}

// ─── Main App ─────────────────────────────────────────────────────────────────

function App() {
  const [tab, setTab] = useState("extract")

  // Form state
  const [platformName, setPlatformName] = useState("CoinMarketCap")
  const [platformUrl, setPlatformUrl] = useState("")
  const [urlError, setUrlError] = useState("")
  const [categories, setCategories] = useState([])
  const [selectedCategory, setSelectedCategory] = useState("")
  const [loadingCategories, setLoadingCategories] = useState(false)
  const [topNOption, setTopNOption] = useState("50")
  const [customN, setCustomN] = useState("")
  const [mode, setMode] = useState("recent")
  const [workers, setWorkers] = useState(3)

  // Extraction state
  const [loading, setLoading] = useState(false)
  const [connectionLost, setConnectionLost] = useState(false)
  const [logs, setLogs] = useState([])
  const [logsOpen, setLogsOpen] = useState(true)
  const [progress, setProgress] = useState({ done: 0, total: 0, pct: 0, project: "", eta: 0, workers: 0 })

  // Analytics state
  const [metrics, setMetrics] = useState(null)
  const [metricsHistory, setMetricsHistory] = useState([])
  const [metricsLoading, setMetricsLoading] = useState(false)
  const [analyticsSubTab, setAnalyticsSubTab] = useState("overview")

  // Results state
  const [leads, setLeads] = useState([])
  const [tableSearch, setTableSearch] = useState("")
  const [tableFilter, setTableFilter] = useState("all")
  const [sortCol, setSortCol] = useState(null)
  const [sortDir, setSortDir] = useState("asc")
  const [tablePage, setTablePage] = useState(1)
  const PAGE_SIZE = 50

  const logsEndRef = useRef(null)

  const fetchLeads = useCallback(async (partial = false) => {
    try {
      const endpoint = partial ? `${API_BASE}/leads/partial` : `${API_BASE}/leads`
      const res = await fetch(endpoint)
      const data = await res.json()
      if (Array.isArray(data) && data.length > 0) setLeads(data)
      else if (!partial) setLeads([])
    } catch { /* silent */ }
  }, [])

  const fetchMetrics = useCallback(async () => {
    setMetricsLoading(true)
    try {
      const [mRes, hRes] = await Promise.all([
        fetch(`${API_BASE}/metrics`),
        fetch(`${API_BASE}/metrics/history`),
      ])
      if (mRes.ok) setMetrics(await mRes.json())
      else setMetrics(null)
      if (hRes.ok) setMetricsHistory(await hRes.json())
      else setMetricsHistory([])
    } catch { /* silent */ }
    setMetricsLoading(false)
  }, [])

  useEffect(() => { fetchLeads() }, [fetchLeads])

  useEffect(() => {
    if (tab === "analytics") fetchMetrics()
  }, [tab, fetchMetrics])

  // When switching to a listing-only platform (e.g. DeFiLlama Raises), auto-set
  // the fixed listing URL and clear the category selector so the flow is unblocked.
  const isListingOnly = LISTING_ONLY_PLATFORMS.has(platformName)
  useEffect(() => {
    if (isListingOnly) {
      const listingUrl = PLATFORM_LISTING_URL[platformName] || ""
      setSelectedCategory(listingUrl)
      setPlatformUrl(listingUrl)
      setCategories([])
      setUrlError("")
    } else {
      setSelectedCategory("")
      setPlatformUrl("")
      setCategories([])
      setUrlError("")
    }
  }, [platformName, isListingOnly])

  const fetchCategories = async () => {
    const err = validateCategoryUrl(platformUrl)
    setUrlError(err)
    if (err) return
    setLoadingCategories(true)
    setCategories([])
    setSelectedCategory("")
    try {
      const res = await fetch(`${API_BASE}/categories?url=${encodeURIComponent(platformUrl.trim())}`)
      const result = await res.json()
      if (result.status === "ok" && result.categories?.length) {
        setCategories(result.categories)
        setSelectedCategory(result.categories[0].url)
      } else {
        setUrlError(result.message || "Could not load categories.")
      }
    } catch {
      setUrlError("Failed to reach the API. Is the backend running?")
    }
    setLoadingCategories(false)
  }

  const resolveTopN = () => {
    if (topNOption === "custom") {
      const n = parseInt(customN, 10)
      return Number.isFinite(n) && n > 0 ? n : 0
    }
    return parseInt(topNOption, 10)
  }

  const streamLogs = (reconnectAttempt = 0) => {
    const es = new EventSource(`${API_BASE}/live-logs`)

    es.onmessage = (event) => {
      const data = JSON.parse(event.data)

      if (data.type === "progress") {
        setProgress(data)
        return
      }

      if (!data.done && !data.message) return

      setLogs((prev) => [data, ...prev].slice(0, 800))

      if (data.done) {
        es.close()
        // Confirm with /status before declaring finished — guards against
        // SSE reconnects that emit a stale "idle" done event.
        fetch(`${API_BASE}/status`)
          .then((r) => r.json())
          .then((s) => {
            if (s.running) {
              // Backend still going — reconnect silently.
              setTimeout(() => streamLogs(0), 1500)
            } else {
              setLoading(false)
              fetchLeads()
              setTimeout(() => setTab("results"), 600)
            }
          })
          .catch(() => {
            setLoading(false)
            fetchLeads()
          })
      }
    }

    es.onerror = () => {
      es.close()
      // SSE connection dropped (proxy timeout, network blip, etc.).
      // Do NOT show "Extraction complete" — check if backend is still running.
      fetch(`${API_BASE}/status`)
        .then((r) => r.json())
        .then((s) => {
          if (s.running) {
            // Still running — show whatever has been enriched so far, then reconnect.
            fetchLeads(true)
            const delay = Math.min(1000 * (reconnectAttempt + 1), 3000)
            setLogs((prev) => [
              { message: `Connection lost — reconnecting in ${Math.round(delay / 1000)}s…` },
              ...prev,
            ].slice(0, 800))
            setTimeout(() => streamLogs(reconnectAttempt + 1), delay)
          } else {
            // Genuinely finished or crashed — load final results.
            setLoading(false)
            fetchLeads()
          }
        })
        .catch(() => {
          // Can't reach API at all — the backend likely crashed/restarted
          // (a common cause is an out-of-memory kill when too many Chromium
          // workers run on a small instance).
          setLoading(false)
          setConnectionLost(true)
          setLogs((prev) => [
            { message: "Lost connection to server — the backend stopped responding (it may have restarted or run out of memory). Try fewer workers / a smaller lead count, or use a larger instance." },
            ...prev,
          ].slice(0, 800))
        })
    }
  }

  const startExtraction = async () => {
    if (!selectedCategory) {
      setLogs([{ message: isListingOnly ? "Listing URL not set — try reloading." : "Select a category first." }])
      return
    }
    const topN = resolveTopN()
    if (!topN) {
      setLogs([{ message: "Enter a valid number of projects." }])
      return
    }
    setLoading(true)
    setConnectionLost(false)
    setLogs([])
    setProgress({ done: 0, total: topN, pct: 0, project: "", eta: 0, workers })
    setTab("extract")

    try {
      const res = await fetch(`${API_BASE}/start-extraction`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category_url: selectedCategory, top_n: topN, mode, workers }),
      })
      const result = await res.json()
      if (result.status === "started") {
        streamLogs()
      } else {
        setLogs([{ message: result.message || "Could not start extraction." }])
        setLoading(false)
      }
    } catch {
      setLogs([{ message: "Failed to reach the extraction API." }])
      setLoading(false)
    }
  }

  // ── Table logic ─────────────────────────────────────────────────────────────

  const hasField = (lead, f) => lead[f] && lead[f] !== "N/A" && lead[f] !== ""

  const filteredLeads = leads
    .filter((l) => {
      const q = tableSearch.toLowerCase()
      if (q && !l["Company / Project Name"]?.toLowerCase().includes(q) &&
          !l["Official Email IDs"]?.toLowerCase().includes(q) &&
          !l["Industry / Category"]?.toLowerCase().includes(q)) return false
      if (tableFilter === "email"    && !hasField(l, "Official Email IDs")) return false
      if (tableFilter === "linkedin" && !hasField(l, "LinkedIn URLs"))      return false
      if (tableFilter === "telegram" && !hasField(l, "Telegram URLs"))      return false
      if (tableFilter === "complete" && (
          !hasField(l, "Official Website URL") ||
          !hasField(l, "Official Email IDs")   ||
          !hasField(l, "LinkedIn URLs")         ||
          !hasField(l, "Telegram URLs")
      )) return false
      return true
    })
    .map((l) => ({ ...l, _score: leadScore(l) }))
    .sort((a, b) => {
      if (!sortCol) return 0
      let av = a[sortCol] ?? "", bv = b[sortCol] ?? ""
      if (sortCol === "_score") { av = a._score; bv = b._score }
      if (av < bv) return sortDir === "asc" ? -1 : 1
      if (av > bv) return sortDir === "asc" ? 1 : -1
      return 0
    })

  const pageCount = Math.ceil(filteredLeads.length / PAGE_SIZE)
  const paginated = filteredLeads.slice((tablePage - 1) * PAGE_SIZE, tablePage * PAGE_SIZE)

  const toggleSort = (col) => {
    if (sortCol === col) setSortDir((d) => d === "asc" ? "desc" : "asc")
    else { setSortCol(col); setSortDir("asc") }
    setTablePage(1)
  }

  const SortIcon = ({ col }) => {
    if (sortCol !== col) return <span className="opacity-20"><Ic.ChevronDown /></span>
    return sortDir === "asc" ? <Ic.ChevronUp /> : <Ic.ChevronDown />
  }

  // ── Dashboard stats ─────────────────────────────────────────────────────────

  const totalLeads = leads.length
  const withEmail    = leads.filter((l) => hasField(l, "Official Email IDs")).length
  const withLinkedIn = leads.filter((l) => hasField(l, "LinkedIn URLs")).length
  const withTelegram = leads.filter((l) => hasField(l, "Telegram URLs")).length
  const emailPct = totalLeads ? Math.round((withEmail / totalLeads) * 100) : 0
  const linkedinPct = totalLeads ? Math.round((withLinkedIn / totalLeads) * 100) : 0
  const telegramPct = totalLeads ? Math.round((withTelegram / totalLeads) * 100) : 0

  const gradeMap = totalLeads
    ? leads.reduce((acc, l) => {
        const g = leadGrade(leadScore(l)).label
        acc[g] = (acc[g] || 0) + 1
        return acc
      }, {})
    : {}

  // ── UI ──────────────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-[#07070f] text-white overflow-x-hidden">
      {/* Particle network background */}
      <div className="fixed inset-0 pointer-events-none z-0">
        <ParticleCanvas />
      </div>
      {/* Ambient orbs */}
      <div className="fixed top-0 left-1/4 w-[600px] h-[500px] rounded-full bg-violet-600/8 blur-[160px] pointer-events-none z-0" />
      <div className="fixed bottom-0 right-1/4 w-[500px] h-[400px] rounded-full bg-indigo-600/8 blur-[140px] pointer-events-none z-0" />

      {/* Nav bar */}
      <header className="sticky top-0 z-50 border-b border-white/[0.06] bg-[#07070f]/85 backdrop-blur-xl relative">
        <div className="max-w-[1400px] mx-auto px-6 h-14 flex items-center gap-8">
          {/* Brand */}
          <div className="flex items-center gap-2.5 shrink-0">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-violet-500/30">
              <Ic.Rocket />
            </div>
            <span className="text-sm font-bold text-white tracking-tight hidden sm:block">LeadIntel</span>
          </div>

          {/* Tabs */}
          <nav className="flex items-center gap-1">
            {[
              { id: "extract", label: "Extract", icon: <Ic.Rocket /> },
              { id: "results", label: `Results${leads.length ? ` (${leads.length})` : ""}`, icon: <Ic.Table /> },
              { id: "dashboard", label: "Dashboard", icon: <Ic.Grid /> },
              { id: "analytics", label: "Analytics", icon: <Ic.Chart /> },
            ].map(({ id, label, icon }) => (
              <button key={id} onClick={() => setTab(id)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                  tab === id
                    ? "bg-violet-500/15 text-violet-300 border border-violet-500/25"
                    : "text-slate-500 hover:text-slate-300 hover:bg-white/[0.04]"
                }`}>
                {icon}{label}
              </button>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-2">
            {loading && (
              <div className="flex items-center gap-2 text-xs text-violet-400/80 font-medium">
                <span className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-pulse" />
                {progress.done}/{progress.total} enriched
              </div>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-[1400px] mx-auto px-4 sm:px-6 lg:px-10 py-8 relative z-10">

        {/* ════════════ EXTRACT TAB ════════════ */}
        {tab === "extract" && (
          <div className="space-y-6">
            <div>
              <h1 className="text-2xl font-black tracking-tight">
                <span className="bg-gradient-to-r from-violet-300 via-indigo-300 to-sky-300 bg-clip-text text-transparent">
                  Lead Extraction
                </span>
              </h1>
              <p className="text-slate-600 text-sm mt-1">Configure and run an enrichment pass across a platform category.</p>
            </div>

            {/* Config card */}
            <div className={`${card} p-6`}>
              <div className="flex items-center gap-2 mb-5">
                <div className="w-1.5 h-1.5 rounded-full bg-violet-400" />
                <span className="text-sm font-bold text-white">Configure Extraction</span>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Platform */}
                <div>
                  <label className={labelCls}>Platform</label>
                  <select value={platformName} onChange={(e) => setPlatformName(e.target.value)}
                    disabled={loading} className={inputCls}>
                    {PLATFORM_OPTIONS.map((p) => <option key={p}>{p}</option>)}
                  </select>
                </div>

                {isListingOnly ? (
                  /* DeFiLlama Raises: fixed listing URL, no category fetch needed */
                  <div>
                    <label className={labelCls}>Listing Source</label>
                    <div className={`${inputCls} flex items-center gap-2 opacity-70 cursor-default`}>
                      <span className="w-2 h-2 rounded-full bg-emerald-400 flex-shrink-0" />
                      <span className="text-slate-300 text-xs truncate">{selectedCategory || "Loading…"}</span>
                    </div>
                    <p className="text-slate-600 text-[10px] mt-1">Raises data pulled from the DeFiLlama API — no URL input needed.</p>
                  </div>
                ) : (
                  /* Category-based platforms: show URL input + Fetch button */
                  <div>
                    <label className={labelCls}>Category Index URL</label>
                    <div className="flex gap-2">
                      <input type="text" value={platformUrl}
                        onChange={(e) => { setPlatformUrl(e.target.value); if (urlError) setUrlError("") }}
                        placeholder="https://coinmarketcap.com/cryptocurrency-category/"
                        disabled={loading} className={inputCls} />
                      <button onClick={fetchCategories} disabled={loading || loadingCategories}
                        className={`${btnGhost} shrink-0`}>
                        {loadingCategories ? <Ic.Spinner /> : "Fetch"}
                      </button>
                    </div>
                    {urlError && (
                      <p className="text-rose-400/80 text-xs mt-1.5 flex items-center gap-1">
                        <span className="w-1 h-1 rounded-full bg-rose-400 inline-block" />{urlError}
                      </p>
                    )}
                  </div>
                )}

                {/* Category selector — hidden for listing-only platforms */}
                {!isListingOnly && (
                <div>
                  <label className={labelCls}>
                    Category {categories.length > 0 && (
                      <span className="text-violet-400/70 normal-case ml-1">({categories.length} found)</span>
                    )}
                  </label>
                  <select value={selectedCategory} onChange={(e) => setSelectedCategory(e.target.value)}
                    disabled={loading || categories.length === 0} className={inputCls}>
                    {categories.length === 0
                      ? <option value="">Fetch categories first</option>
                      : categories.map((c) => <option key={c.url} value={c.url}>{c.name}</option>)}
                  </select>
                </div>
                )}

                {/* Count + Workers */}
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className={labelCls}>Lead Count</label>
                    <select value={topNOption} onChange={(e) => { setTopNOption(e.target.value); setTablePage(1) }}
                      disabled={loading} className={inputCls}>
                      {TOP_N_OPTIONS.map((n) => <option key={n} value={String(n)}>Top {n}</option>)}
                      <option value="custom">Custom</option>
                    </select>
                    {topNOption === "custom" && (
                      <input type="number" min="1" max="1000" value={customN}
                        onChange={(e) => setCustomN(e.target.value)} placeholder="e.g. 75"
                        disabled={loading} className={`${inputCls} mt-2`} />
                    )}
                  </div>
                  <div>
                    <label className={labelCls}>Workers</label>
                    <select value={workers} onChange={(e) => setWorkers(Number(e.target.value))}
                      disabled={loading} className={inputCls}>
                      {[1, 2, 3, 4, 5].map((n) => (
                        <option key={n} value={n}>{n} {n === 3 ? "(recommended)" : ""}</option>
                      ))}
                    </select>
                    <p className="text-slate-700 text-[10px] mt-1">~{workers * 250}MB RAM</p>
                  </div>
                </div>
              </div>

              {/* Mode toggle */}
              <div className="mt-5">
                <label className={labelCls}>Extraction Mode</label>
                <div className="inline-flex rounded-xl border border-white/[0.08] overflow-hidden">
                  {(isListingOnly
                    ? [
                        { id: "recent", label: "Latest Raises",  desc: "Newest funding rounds" },
                        { id: "ranked", label: "Largest Raises", desc: "By amount raised" },
                      ]
                    : [
                        { id: "recent", label: "Recently Added", desc: "Newest coins first" },
                        { id: "ranked", label: "Top Ranked",     desc: "By market cap" },
                      ]
                  ).map(({ id, label, desc }) => (
                    <button key={id} type="button" onClick={() => setMode(id)} disabled={loading}
                      className={`px-5 py-2.5 text-xs font-semibold transition-all disabled:opacity-40 ${
                        mode === id
                          ? "bg-violet-500/20 text-violet-300"
                          : "bg-black/20 text-slate-500 hover:text-slate-300"
                      } border-r last:border-r-0 border-white/[0.08]`}>
                      {label}
                      <span className="block text-[10px] font-normal opacity-60 mt-0.5">{desc}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Start */}
              <div className="mt-6 flex items-center gap-3">
                <button onClick={startExtraction} disabled={loading || (!isListingOnly && categories.length === 0)}
                  className={btnPrimary}>
                  {loading ? <><Ic.Spinner /><span>Running…</span></> : <><Ic.Rocket /><span>Start Extraction</span></>}
                </button>
                {loading && (
                  <span className="text-slate-600 text-xs">
                    Processing with {progress.workers || workers} concurrent browsers
                  </span>
                )}
              </div>
            </div>

            {/* Live progress card */}
            {(loading || logs.length > 0) && (
              <div className={`${card} p-6`}>
                {/* Progress header */}
                <div className="flex items-start gap-6">
                  {/* Ring gauge */}
                  <div className="relative shrink-0">
                    <ProgressRing pct={progress.pct || 0} size={100} stroke={7} />
                    <div className="absolute inset-0 flex items-center justify-center flex-col">
                      <span className="text-lg font-black text-white">{Math.round(progress.pct || 0)}%</span>
                    </div>
                  </div>

                  <div className="flex-1 min-w-0 pt-1">
                    <div className="flex items-center gap-2 mb-1">
                      {loading && <span className="w-2 h-2 rounded-full bg-violet-400 animate-pulse" />}
                      {connectionLost && !loading && <span className="w-2 h-2 rounded-full bg-rose-500" />}
                      <span className={`text-sm font-bold ${connectionLost && !loading ? "text-rose-300" : "text-white"}`}>
                        {loading
                          ? "Extracting…"
                          : connectionLost
                            ? "Connection lost — backend stopped responding"
                            : "Extraction complete"}
                      </span>
                    </div>

                    <p className="text-slate-500 text-xs truncate mb-3">
                      {progress.project ? `Processing: ${progress.project}` : "Starting workers…"}
                    </p>

                    {/* Progress bar */}
                    <div className="h-1.5 bg-white/[0.05] rounded-full overflow-hidden mb-3">
                      <div
                        className="h-full rounded-full transition-all duration-500"
                        style={{
                          width: `${progress.pct || 0}%`,
                          background: "linear-gradient(90deg, #7c3aed, #4f46e5)",
                          boxShadow: "0 0 12px rgba(124,58,237,0.5)",
                        }}
                      />
                    </div>

                    {/* Stats row */}
                    <div className="flex items-center gap-5 flex-wrap">
                      <div className="text-center">
                        <p className="text-white font-bold text-lg leading-none">{progress.done || 0}</p>
                        <p className="text-slate-600 text-[10px] mt-0.5">Done</p>
                      </div>
                      <div className="text-center">
                        <p className="text-slate-400 font-bold text-lg leading-none">{progress.total || 0}</p>
                        <p className="text-slate-600 text-[10px] mt-0.5">Total</p>
                      </div>
                      <div className="text-center">
                        <p className="text-slate-400 font-bold text-lg leading-none">
                          {progress.total ? progress.total - (progress.done || 0) : 0}
                        </p>
                        <p className="text-slate-600 text-[10px] mt-0.5">Remaining</p>
                      </div>
                      {progress.eta > 0 && (
                        <div className="text-center">
                          <p className="text-violet-300 font-bold text-lg leading-none">{fmtEta(progress.eta)}</p>
                          <p className="text-slate-600 text-[10px] mt-0.5">ETA</p>
                        </div>
                      )}
                      {progress.workers > 0 && (
                        <div className="flex items-center gap-1.5 ml-2">
                          {Array.from({ length: progress.workers }).map((_, i) => (
                            <div key={i}
                              className={`w-2 h-2 rounded-full ${loading ? "bg-violet-500 animate-pulse" : "bg-slate-700"}`}
                              style={{ animationDelay: `${i * 200}ms` }}
                            />
                          ))}
                          <span className="text-slate-600 text-[10px] ml-1">{progress.workers} workers</span>
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                {/* Live logs */}
                <div className="mt-5">
                  <button onClick={() => setLogsOpen((o) => !o)}
                    className="flex items-center gap-2 text-slate-500 hover:text-slate-300 text-xs font-medium transition-colors mb-2">
                    <Ic.Terminal />
                    Live Logs
                    {logsOpen ? <Ic.ChevronUp /> : <Ic.ChevronDown />}
                    <span className="text-slate-700 ml-1">({logs.length})</span>
                  </button>
                  {logsOpen && (
                    <div className="bg-black/60 border border-white/[0.04] rounded-xl p-3.5 h-[200px] overflow-y-auto font-mono text-[11px] leading-relaxed">
                      {logs.length === 0 ? (
                        <span className="text-slate-700">{">"} Waiting for first project…</span>
                      ) : (
                        logs.map((log, i) => (
                          <div key={i} className={
                            log.done ? "text-violet-400 font-semibold" :
                            log.message?.toLowerCase().includes("error") ? "text-rose-400/80" :
                            log.message?.includes("Benchmark") ? "text-amber-400/80" :
                            log.message?.includes("Done") ? "text-emerald-400/70" :
                            "text-slate-500"
                          }>
                            <span className="text-slate-800 select-none mr-1.5">{">"}</span>
                            {log.message}
                          </div>
                        ))
                      )}
                      <div ref={logsEndRef} />
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ════════════ RESULTS TAB ════════════ */}
        {tab === "results" && (
          <div className="space-y-5">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <h1 className="text-2xl font-black tracking-tight">
                  <span className="bg-gradient-to-r from-violet-300 to-sky-300 bg-clip-text text-transparent">Extracted Leads</span>
                </h1>
                <p className="text-slate-600 text-sm mt-0.5">{filteredLeads.length} of {leads.length} leads shown</p>
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <a href={`${API_BASE}/download/csv`}
                  className="inline-flex items-center gap-1.5 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/20 text-xs font-medium px-3 py-1.5 rounded-lg transition-all">
                  <Ic.Download /> CSV
                </a>
                <a href={`${API_BASE}/download/xlsx`}
                  className="inline-flex items-center gap-1.5 bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-400 border border-indigo-500/20 text-xs font-medium px-3 py-1.5 rounded-lg transition-all">
                  <Ic.Download /> XLSX
                </a>
                <a href={`${API_BASE}/download/json`}
                  className="inline-flex items-center gap-1.5 bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border border-amber-500/20 text-xs font-medium px-3 py-1.5 rounded-lg transition-all">
                  <Ic.Download /> JSON
                </a>
              </div>
            </div>

            {/* Filters bar */}
            <div className={`${card} p-3 flex flex-wrap items-center gap-3`}>
              <div className="relative flex-1 min-w-[160px] max-w-[280px]">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-600"><Ic.Search /></span>
                <input type="text" value={tableSearch} onChange={(e) => { setTableSearch(e.target.value); setTablePage(1) }}
                  placeholder="Search project or email…"
                  className="w-full bg-black/40 border border-white/[0.07] rounded-lg pl-8 pr-3 py-2 text-xs text-white placeholder-slate-700 focus:outline-none focus:ring-1 focus:ring-violet-500/30" />
              </div>

              <div className="flex items-center gap-1 flex-wrap">
                {[
                  { id: "all", label: "All" },
                  { id: "email", label: "Has Email" },
                  { id: "linkedin", label: "Has LinkedIn" },
                  { id: "telegram", label: "Has Telegram" },
                  { id: "complete", label: "Complete" },
                ].map(({ id, label }) => (
                  <button key={id} onClick={() => { setTableFilter(id); setTablePage(1) }}
                    className={`px-2.5 py-1 text-[11px] font-semibold rounded-lg transition-all ${
                      tableFilter === id
                        ? "bg-violet-500/20 text-violet-300 border border-violet-500/30"
                        : "text-slate-500 hover:text-slate-300 bg-white/[0.03] border border-white/[0.05]"
                    }`}>{label}
                  </button>
                ))}
              </div>
            </div>

            {/* Table */}
            <div className={`${card} overflow-hidden`}>
              <div className="overflow-auto" style={{ maxHeight: "65vh" }}>
                <table className="w-full text-left text-sm min-w-[900px]">
                  <thead className="sticky top-0 z-10 bg-[#0c0c18] border-b border-white/[0.06]">
                    <tr>
                      {[
                        { key: "#",          col: null,                       w: "w-10" },
                        { key: "Company",    col: "Company / Project Name",   w: "min-w-[180px]" },
                        { key: "Website",    col: "Official Website URL",     w: "" },
                        { key: "Email IDs",  col: "Official Email IDs",       w: "min-w-[200px]" },
                        { key: "LinkedIn",   col: "LinkedIn URLs",             w: "" },
                        { key: "Telegram",   col: "Telegram URLs",            w: "" },
                        { key: "GitHub",     col: "GitHub URLs",              w: "" },
                        { key: "Twitter/X",  col: "Twitter/X URLs",           w: "" },
                        { key: "Founder",    col: "Founder Name",             w: "" },
                        { key: "Category",   col: "Industry / Category",      w: "" },
                        { key: "Quality",    col: "_score",                   w: "w-20" },
                      ].map(({ key, col, w }) => (
                        <th key={key} onClick={() => col && toggleSort(col)}
                          className={`px-4 py-3 text-[11px] font-semibold uppercase tracking-wider text-slate-600 ${col ? "cursor-pointer hover:text-slate-400" : ""} ${w} whitespace-nowrap`}>
                          <div className="flex items-center gap-1">
                            {key}{col && <SortIcon col={col} />}
                          </div>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {paginated.length === 0 ? (
                      <tr>
                        <td colSpan={11} className="px-4 py-20 text-center">
                          <div className="flex flex-col items-center gap-3">
                            <div className="w-12 h-12 rounded-full bg-white/[0.03] border border-white/[0.06] flex items-center justify-center text-slate-600">
                              <Ic.Table />
                            </div>
                            <p className="text-slate-600 text-sm">
                              {leads.length === 0
                                ? "No leads yet. Run an extraction to populate this table."
                                : "No leads match the current filters."}
                            </p>
                            {leads.length === 0 && (
                              <button onClick={() => setTab("extract")} className={btnGhost}>
                                <Ic.Rocket /> Go to Extract
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ) : (
                      paginated.map((lead, idx) => {
                        const score = lead._score
                        const grade = leadGrade(score)
                        const rowNum = (tablePage - 1) * PAGE_SIZE + idx + 1
                        return (
                          <tr key={idx}
                            className="border-t border-white/[0.03] hover:bg-white/[0.02] transition-colors group">
                            <td className="px-4 py-2.5 text-slate-700 text-xs font-mono">{rowNum}</td>
                            <td className="px-4 py-2.5 max-w-[220px]">
                              <p className="text-white text-sm font-semibold truncate">{lead["Company / Project Name"]}</p>
                              {lead["Short Description"] && lead["Short Description"] !== "N/A" && (
                                <p className="text-slate-600 text-[10px] truncate mt-0.5" title={lead["Short Description"]}>
                                  {lead["Short Description"]}
                                </p>
                              )}
                            </td>
                            <td className="px-4 py-2.5"><LinkCell value={lead["Official Website URL"]} /></td>
                            <td className="px-4 py-2.5 max-w-[220px]">
                              <EmailCell value={lead["Official Email IDs"]} />
                            </td>
                            <td className="px-4 py-2.5"><LinkCell value={lead["LinkedIn URLs"]} /></td>
                            <td className="px-4 py-2.5"><LinkCell value={lead["Telegram URLs"]} /></td>
                            <td className="px-4 py-2.5"><LinkCell value={lead["GitHub URLs"]} /></td>
                            <td className="px-4 py-2.5"><LinkCell value={lead["Twitter/X URLs"]} /></td>
                            <td className="px-4 py-2.5">
                              {lead["Founder Name"] && lead["Founder Name"] !== "N/A" ? (
                                <span className="text-slate-300 text-xs">{lead["Founder Name"]}</span>
                              ) : (
                                <span className="text-slate-700 text-xs">—</span>
                              )}
                            </td>
                            <td className="px-4 py-2.5">
                              {lead["Industry / Category"] && lead["Industry / Category"] !== "N/A" ? (
                                <span className="text-xs text-violet-300 bg-violet-500/10 border border-violet-500/20 px-2 py-0.5 rounded-md whitespace-nowrap">
                                  {lead["Industry / Category"]}
                                </span>
                              ) : (
                                <span className="text-slate-700 text-xs">—</span>
                              )}
                            </td>
                            <td className="px-4 py-2.5">
                              <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-bold border ${grade.bg} ${grade.text} ${grade.border}`}>
                                {grade.label}
                              </span>
                            </td>
                          </tr>
                        )
                      })
                    )}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              {pageCount > 1 && (
                <div className="flex items-center justify-between px-4 py-3 border-t border-white/[0.05]">
                  <span className="text-slate-600 text-xs">
                    Page {tablePage} of {pageCount} · {filteredLeads.length} results
                  </span>
                  <div className="flex items-center gap-1">
                    <button onClick={() => setTablePage((p) => Math.max(1, p - 1))} disabled={tablePage === 1}
                      className={`${btnGhost} px-2.5 py-1.5 disabled:opacity-30`}>← Prev</button>
                    {Array.from({ length: Math.min(pageCount, 7) }, (_, i) => {
                      const p = tablePage <= 4 ? i + 1
                        : tablePage >= pageCount - 3 ? pageCount - 6 + i
                        : tablePage - 3 + i
                      if (p < 1 || p > pageCount) return null
                      return (
                        <button key={p} onClick={() => setTablePage(p)}
                          className={`w-7 h-7 rounded-lg text-xs font-medium transition-all ${
                            p === tablePage
                              ? "bg-violet-500/20 text-violet-300 border border-violet-500/30"
                              : "text-slate-600 hover:text-slate-300 hover:bg-white/[0.04]"
                          }`}>{p}</button>
                      )
                    })}
                    <button onClick={() => setTablePage((p) => Math.min(pageCount, p + 1))} disabled={tablePage === pageCount}
                      className={`${btnGhost} px-2.5 py-1.5 disabled:opacity-30`}>Next →</button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ════════════ DASHBOARD TAB ════════════ */}
        {tab === "dashboard" && (
          <div className="space-y-6">
            <div>
              <h1 className="text-2xl font-black tracking-tight">
                <span className="bg-gradient-to-r from-violet-300 to-sky-300 bg-clip-text text-transparent">Dashboard</span>
              </h1>
              <p className="text-slate-600 text-sm mt-1">Lead quality analytics and extraction overview.</p>
            </div>

            {/* Stats row */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <StatCard label="Total Leads" value={totalLeads} accent="violet"
                sub={totalLeads ? "across all extractions" : "no extractions yet"} />
              <StatCard label="Email Coverage" value={`${emailPct}%`} accent="emerald"
                sub={`${withEmail} of ${totalLeads} leads`} />
              <StatCard label="LinkedIn Coverage" value={`${linkedinPct}%`} accent="sky"
                sub={`${withLinkedIn} of ${totalLeads} leads`} />
              <StatCard label="Telegram Coverage" value={`${telegramPct}%`} accent="amber"
                sub={`${withTelegram} of ${totalLeads} leads`} />
            </div>

            {totalLeads > 0 ? (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Coverage bars */}
                <div className={`${card} p-6`}>
                  <h3 className="text-sm font-bold text-white mb-5">Field Coverage</h3>
                  <div className="space-y-4">
                    <CoverageBar label="Official Email" pct={emailPct} color="emerald" />
                    <CoverageBar label="LinkedIn" pct={linkedinPct} color="sky" />
                    <CoverageBar label="Telegram" pct={telegramPct} color="violet" />
                    <CoverageBar label="GitHub"
                      pct={totalLeads ? Math.round((leads.filter((l) => hasField(l, "GitHub URLs")).length / totalLeads) * 100) : 0}
                      color="indigo" />
                    <CoverageBar label="Founder Name"
                      pct={totalLeads ? Math.round((leads.filter((l) => hasField(l, "Founder Name")).length / totalLeads) * 100) : 0}
                      color="amber" />
                    <CoverageBar label="Founder LinkedIn"
                      pct={totalLeads ? Math.round((leads.filter((l) => hasField(l, "Founder LinkedIn")).length / totalLeads) * 100) : 0}
                      color="violet" />
                    <CoverageBar label="Twitter/X"
                      pct={totalLeads ? Math.round((leads.filter((l) => hasField(l, "Twitter/X URLs")).length / totalLeads) * 100) : 0}
                      color="emerald" />
                    <CoverageBar label="Website"
                      pct={totalLeads ? Math.round((leads.filter((l) => l["Official Website URL"] && l["Official Website URL"] !== "N/A").length / totalLeads) * 100) : 0}
                      color="amber" />
                  </div>
                </div>

                {/* Quality distribution */}
                <div className={`${card} p-6`}>
                  <h3 className="text-sm font-bold text-white mb-5">Quality Distribution</h3>
                  <div className="space-y-3">
                    {["A+", "A", "B", "C", "D"].map((g) => {
                      const count = gradeMap[g] || 0
                      const pct = totalLeads ? Math.round((count / totalLeads) * 100) : 0
                      const grade = leadGrade(g === "A+" ? 95 : g === "A" ? 75 : g === "B" ? 55 : g === "C" ? 35 : 10)
                      return (
                        <div key={g} className="flex items-center gap-3">
                          <span className={`w-8 text-center text-xs font-bold ${grade.text}`}>{g}</span>
                          <div className="flex-1 h-1.5 bg-white/[0.05] rounded-full overflow-hidden">
                            <div className={`h-full rounded-full transition-all duration-700 ${grade.bg.replace("/15", "/60")}`}
                              style={{ width: `${pct}%` }} />
                          </div>
                          <span className="text-slate-600 text-xs w-16 text-right">{count} ({pct}%)</span>
                        </div>
                      )
                    })}
                  </div>
                  <div className="mt-5 pt-4 border-t border-white/[0.05]">
                    <p className="text-slate-600 text-xs">
                      A+ = Email+LinkedIn+Telegram+Website · D = Website only or empty
                    </p>
                  </div>
                </div>

                {/* Platform breakdown */}
                <div className={`${card} p-6`}>
                  <h3 className="text-sm font-bold text-white mb-5">Platform Breakdown</h3>
                  {(() => {
                    const platforms = leads.reduce((acc, l) => {
                      acc[l["Source Platform"] || "Unknown"] = (acc[l["Source Platform"] || "Unknown"] || 0) + 1
                      return acc
                    }, {})
                    return (
                      <div className="space-y-3">
                        {Object.entries(platforms).map(([plat, count]) => (
                          <div key={plat} className="flex items-center justify-between">
                            <span className="text-slate-400 text-sm capitalize">{plat}</span>
                            <div className="flex items-center gap-3">
                              <div className="w-32 h-1.5 bg-white/[0.05] rounded-full overflow-hidden">
                                <div className="h-full bg-violet-500/50 rounded-full"
                                  style={{ width: `${(count / totalLeads) * 100}%` }} />
                              </div>
                              <span className="text-slate-500 text-xs w-12 text-right">{count} leads</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )
                  })()}
                </div>

                {/* Top leads preview */}
                <div className={`${card} p-6`}>
                  <h3 className="text-sm font-bold text-white mb-5">Top Leads (by score)</h3>
                  <div className="space-y-2">
                    {[...leads]
                      .map((l) => ({ ...l, _score: leadScore(l) }))
                      .sort((a, b) => b._score - a._score)
                      .slice(0, 5)
                      .map((lead, i) => {
                        const grade = leadGrade(lead._score)
                        return (
                          <div key={i} className="flex items-center gap-3 py-1.5">
                            <span className={`w-8 text-center text-xs font-bold border rounded-md px-1 py-0.5 ${grade.bg} ${grade.text} ${grade.border}`}>
                              {grade.label}
                            </span>
                            <div className="flex-1 min-w-0">
                              <p className="text-white text-xs font-semibold truncate">{lead["Company / Project Name"]}</p>
                              <p className="text-slate-600 text-[10px] truncate">{hasField(lead, "Official Email IDs") ? lead["Official Email IDs"].split(";")[0].trim() : "No email"}</p>
                            </div>
                            <span className="text-slate-700 text-xs">{lead._score}pt</span>
                          </div>
                        )
                      })}
                  </div>
                </div>
              </div>
            ) : (
              <div className={`${card} p-16 text-center`}>
                <div className="w-16 h-16 rounded-2xl bg-white/[0.03] border border-white/[0.06] flex items-center justify-center mx-auto mb-4 text-slate-600">
                  <Ic.Grid />
                </div>
                <p className="text-slate-600">No data yet. Run an extraction to see analytics.</p>
                <button onClick={() => setTab("extract")} className={`${btnPrimary} mt-4 mx-auto`}>
                  <Ic.Rocket /> Go to Extract
                </button>
              </div>
            )}
          </div>
        )}
        {/* ════════════ ANALYTICS TAB ════════════ */}
        {tab === "analytics" && (
          <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <h1 className="text-2xl font-black tracking-tight">
                  <span className="bg-gradient-to-r from-violet-300 to-sky-300 bg-clip-text text-transparent">Performance Analytics</span>
                </h1>
                <p className="text-slate-600 text-sm mt-1">
                  {metrics ? `Last run: ${metrics.run_id} · ${metrics.platform} · ${metrics.mode}` : "Run an extraction to generate benchmark data."}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={fetchMetrics} disabled={metricsLoading} className={btnGhost}>
                  {metricsLoading ? <Ic.Spinner /> : "↻"} Refresh
                </button>
                {metrics && (
                  <a href={`${API_BASE}/metrics/export/json`}
                    className="inline-flex items-center gap-1.5 bg-violet-500/10 hover:bg-violet-500/20 text-violet-400 border border-violet-500/20 text-xs font-medium px-3 py-1.5 rounded-lg transition-all">
                    <Ic.Download /> Metrics JSON
                  </a>
                )}
                {metrics && (
                  <a href={`${API_BASE}/metrics/export/csv`}
                    className="inline-flex items-center gap-1.5 bg-sky-500/10 hover:bg-sky-500/20 text-sky-400 border border-sky-500/20 text-xs font-medium px-3 py-1.5 rounded-lg transition-all">
                    <Ic.Download /> Projects CSV
                  </a>
                )}
              </div>
            </div>

            {/* Sub-tab nav */}
            <div className="flex items-center gap-1 border-b border-white/[0.06] pb-1">
              {["overview", "projects", "workers", "history"].map((st) => (
                <button key={st} onClick={() => setAnalyticsSubTab(st)}
                  className={`px-4 py-2 text-xs font-semibold rounded-t-lg capitalize transition-all ${
                    analyticsSubTab === st
                      ? "text-violet-300 bg-violet-500/10 border-b-2 border-violet-400"
                      : "text-slate-500 hover:text-slate-300"
                  }`}>{st}</button>
              ))}
            </div>

            {!metrics && !metricsLoading && (
              <div className={`${card} p-16 text-center`}>
                <div className="w-16 h-16 rounded-2xl bg-white/[0.03] border border-white/[0.06] flex items-center justify-center mx-auto mb-4 text-slate-600">
                  <Ic.Chart />
                </div>
                <p className="text-slate-600 mb-3">No benchmark data yet. Run an extraction first.</p>
                <button onClick={() => setTab("extract")} className={`${btnPrimary} mx-auto`}>
                  <Ic.Rocket /> Go to Extract
                </button>
              </div>
            )}

            {metricsLoading && (
              <div className="flex items-center gap-3 text-slate-500 text-sm">
                <Ic.Spinner /> Loading metrics…
              </div>
            )}

            {/* ── OVERVIEW sub-tab ── */}
            {metrics && analyticsSubTab === "overview" && (() => {
              const stageLabels = metrics.stage_labels || {}
              const stageAvgs = metrics.stage_avg_times_s || {}
              const bottleneck = metrics.biggest_bottleneck_stage
              const stageOrder = ["platform_page","website_load","contact_pages","browser_fallback","linkedin_recovery","telegram_recovery","email_recovery"]
              const maxStageTime = Math.max(...stageOrder.map((s) => stageAvgs[s] || 0), 0.01)

              return (
                <div className="space-y-5">
                  {/* Summary cards */}
                  <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                    <StatCard label="Total Runtime" value={metrics.total_time_human} accent="violet"
                      sub={`Collect ${metrics.collection_time_s}s + Enrich ${metrics.enrichment_time_s}s`} />
                    <StatCard label="Success Rate" value={`${metrics.success_rate}%`} accent="emerald"
                      sub={`${metrics.successful} ok · ${metrics.failed} failed · ${metrics.cached} cached`} />
                    <StatCard label="Throughput" value={`${metrics.throughput_per_minute}/min`} accent="sky"
                      sub={`${metrics.throughput_per_hour}/hr · ${metrics.workers} workers`} />
                    <StatCard label="Avg / Project" value={`${metrics.avg_project_time_s}s`} accent="amber"
                      sub={`p50 ${metrics.median_project_time_s}s · p95 ${metrics.p95_project_time_s}s`} />
                  </div>

                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                    {/* Stage timing chart */}
                    <div className={`${card} p-6`}>
                      <div className="flex items-center justify-between mb-5">
                        <h3 className="text-sm font-bold text-white">Stage Timing (avg sec/project)</h3>
                        <span className="text-xs text-slate-600">bottleneck highlighted</span>
                      </div>
                      <div className="space-y-3">
                        {stageOrder.map((stage) => {
                          const t = stageAvgs[stage] || 0
                          const barW = maxStageTime > 0 ? (t / maxStageTime) * 100 : 0
                          const isBottleneck = stage === bottleneck
                          return (
                            <div key={stage}>
                              <div className="flex justify-between items-center mb-1">
                                <span className={`text-xs ${isBottleneck ? "text-amber-300 font-semibold" : "text-slate-400"}`}>
                                  {stageLabels[stage] || stage}
                                  {isBottleneck && <span className="ml-1.5 text-amber-400 text-[10px]">← BOTTLENECK</span>}
                                </span>
                                <span className={`text-xs font-mono font-semibold ${isBottleneck ? "text-amber-300" : "text-slate-400"}`}>{t.toFixed(1)}s</span>
                              </div>
                              <div className="h-1.5 bg-white/[0.05] rounded-full overflow-hidden">
                                <div
                                  className={`h-full rounded-full transition-all duration-700 ${isBottleneck ? "bg-amber-400/70" : "bg-violet-500/50"}`}
                                  style={{ width: `${barW}%` }}
                                />
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    </div>

                    {/* Coverage + Recovery */}
                    <div className="space-y-5">
                      <div className={`${card} p-6`}>
                        <h3 className="text-sm font-bold text-white mb-5">Coverage</h3>
                        <div className="space-y-3">
                          <CoverageBar label="Email"    pct={metrics.email_coverage}    color="emerald" />
                          <CoverageBar label="LinkedIn" pct={metrics.linkedin_coverage} color="sky" />
                          <CoverageBar label="Telegram" pct={metrics.telegram_coverage} color="violet" />
                          <CoverageBar label="Twitter"  pct={metrics.twitter_coverage}  color="indigo" />
                          <CoverageBar label="Website"  pct={metrics.website_coverage}  color="amber" />
                        </div>
                      </div>
                      <div className={`${card} p-5`}>
                        <h3 className="text-sm font-bold text-white mb-4">Recovery Stats</h3>
                        <div className="grid grid-cols-3 gap-3 text-center">
                          <div>
                            <p className="text-2xl font-black text-violet-300">{metrics.recovery_invocations}</p>
                            <p className="text-slate-600 text-[10px] mt-1">Invocations</p>
                          </div>
                          <div>
                            <p className="text-2xl font-black text-emerald-300">{metrics.recovery_successes}</p>
                            <p className="text-slate-600 text-[10px] mt-1">Successes</p>
                          </div>
                          <div>
                            <p className="text-2xl font-black text-sky-300">{metrics.recovery_success_rate}%</p>
                            <p className="text-slate-600 text-[10px] mt-1">Hit Rate</p>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Speed row */}
                  <div className={`${card} p-5`}>
                    <h3 className="text-sm font-bold text-white mb-4">Latency Distribution</h3>
                    <div className="grid grid-cols-2 sm:grid-cols-5 gap-4 text-center">
                      {[
                        { label: "Fastest", val: `${metrics.fastest_project_s}s`, accent: "text-emerald-300" },
                        { label: "p50 Median", val: `${metrics.median_project_time_s}s`, accent: "text-sky-300" },
                        { label: "Average", val: `${metrics.avg_project_time_s}s`, accent: "text-violet-300" },
                        { label: "p95", val: `${metrics.p95_project_time_s}s`, accent: "text-amber-300" },
                        { label: "Slowest", val: `${metrics.slowest_project_s}s`, accent: "text-rose-300" },
                      ].map(({ label, val, accent }) => (
                        <div key={label}>
                          <p className={`text-xl font-black ${accent}`}>{val}</p>
                          <p className="text-slate-600 text-[10px] mt-1">{label}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )
            })()}

            {/* ── PROJECTS sub-tab ── */}
            {metrics && analyticsSubTab === "projects" && (() => {
              const projects = metrics.projects || []
              return (
                <div className={`${card} overflow-hidden`}>
                  <div className="overflow-auto" style={{ maxHeight: "70vh" }}>
                    <table className="w-full text-left text-xs min-w-[900px]">
                      <thead className="sticky top-0 z-10 bg-[#0c0c18] border-b border-white/[0.06]">
                        <tr>
                          {["#","Project","Status","Total (s)","Platform (s)","Website (s)","Contact (s)","Browser (s)","LI Rec (s)","TG Rec (s)","Email Rec (s)","Email","LI","TG"].map((h) => (
                            <th key={h} className="px-3 py-2.5 text-[10px] font-semibold uppercase tracking-wider text-slate-600 whitespace-nowrap">{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {projects.map((p, i) => {
                          const statusColor = p.status === "success" ? "text-emerald-400" : p.status === "cached" ? "text-slate-500" : "text-rose-400"
                          const bool2 = (v) => v ? <span className="text-emerald-400">✓</span> : <span className="text-slate-700">—</span>
                          return (
                            <tr key={i} className="border-t border-white/[0.03] hover:bg-white/[0.02] transition-colors">
                              <td className="px-3 py-2 text-slate-700 font-mono">{i + 1}</td>
                              <td className="px-3 py-2 text-white font-medium max-w-[180px]">
                                <span className="truncate block" title={p.project_name}>{p.project_name}</span>
                              </td>
                              <td className={`px-3 py-2 font-semibold ${statusColor}`}>{p.status}</td>
                              <td className="px-3 py-2 text-slate-300 font-mono">{(p.total_duration || 0).toFixed(1)}</td>
                              <td className="px-3 py-2 text-slate-400 font-mono">{(p.t_platform || 0).toFixed(1)}</td>
                              <td className="px-3 py-2 text-slate-400 font-mono">{(p.t_website || 0).toFixed(1)}</td>
                              <td className="px-3 py-2 text-slate-400 font-mono">{(p.t_contact || 0).toFixed(1)}</td>
                              <td className="px-3 py-2 text-slate-400 font-mono">{(p.t_browser_fallback || 0).toFixed(1)}</td>
                              <td className="px-3 py-2 text-slate-400 font-mono">{(p.t_linkedin_recovery || 0).toFixed(1)}</td>
                              <td className="px-3 py-2 text-slate-400 font-mono">{(p.t_telegram_recovery || 0).toFixed(1)}</td>
                              <td className="px-3 py-2 text-slate-400 font-mono">{(p.t_email_recovery || 0).toFixed(1)}</td>
                              <td className="px-3 py-2">{bool2(p.email_found)}</td>
                              <td className="px-3 py-2">{bool2(p.linkedin_found)}</td>
                              <td className="px-3 py-2">{bool2(p.telegram_found)}</td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                  <div className="px-4 py-2.5 border-t border-white/[0.05] text-slate-600 text-xs">
                    {projects.length} projects · scroll right for all columns
                  </div>
                </div>
              )
            })()}

            {/* ── WORKERS sub-tab ── */}
            {metrics && analyticsSubTab === "workers" && (() => {
              const workers = metrics.worker_metrics || []
              return (
                <div className={`${card} overflow-hidden`}>
                  <div className="overflow-auto">
                    <table className="w-full text-left text-xs min-w-[700px]">
                      <thead className="sticky top-0 z-10 bg-[#0c0c18] border-b border-white/[0.06]">
                        <tr>
                          {["Worker","Processed","Success","Failed","Cached","Success Rate","Avg (s)","Min (s)","Max (s)","Median (s)"].map((h) => (
                            <th key={h} className="px-4 py-3 text-[10px] font-semibold uppercase tracking-wider text-slate-600 whitespace-nowrap">{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {workers.map((w, i) => (
                          <tr key={i} className="border-t border-white/[0.03] hover:bg-white/[0.02] transition-colors">
                            <td className="px-4 py-3">
                              <div className="flex items-center gap-2">
                                <div className="w-6 h-6 rounded-full bg-violet-500/20 border border-violet-500/30 flex items-center justify-center text-[10px] font-bold text-violet-300">
                                  {w.worker_id}
                                </div>
                                <span className="text-slate-400 text-xs">Worker {w.worker_id}</span>
                              </div>
                            </td>
                            <td className="px-4 py-3 text-white font-semibold">{w.projects_processed}</td>
                            <td className="px-4 py-3 text-emerald-400 font-semibold">{w.projects_successful}</td>
                            <td className="px-4 py-3 text-rose-400 font-semibold">{w.projects_failed}</td>
                            <td className="px-4 py-3 text-slate-500">{w.projects_cached}</td>
                            <td className="px-4 py-3">
                              <div className="flex items-center gap-2">
                                <div className="w-16 h-1.5 bg-white/[0.05] rounded-full overflow-hidden">
                                  <div className="h-full bg-emerald-500/60 rounded-full" style={{ width: `${w.success_rate}%` }} />
                                </div>
                                <span className="text-emerald-300 text-xs font-semibold">{w.success_rate}%</span>
                              </div>
                            </td>
                            <td className="px-4 py-3 text-slate-300 font-mono">{w.avg_duration_s}</td>
                            <td className="px-4 py-3 text-slate-400 font-mono">{w.min_duration_s}</td>
                            <td className="px-4 py-3 text-slate-400 font-mono">{w.max_duration_s}</td>
                            <td className="px-4 py-3 text-slate-400 font-mono">{w.median_duration_s}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )
            })()}

            {/* ── HISTORY sub-tab ── */}
            {analyticsSubTab === "history" && (() => {
              const history = metricsHistory
              return (
                <div className="space-y-4">
                  {history.length === 0 ? (
                    <div className={`${card} p-12 text-center`}>
                      <p className="text-slate-600">No history yet. Previous runs will appear here.</p>
                    </div>
                  ) : (
                    <div className={`${card} overflow-hidden`}>
                      <div className="overflow-auto">
                        <table className="w-full text-left text-xs min-w-[900px]">
                          <thead className="sticky top-0 z-10 bg-[#0c0c18] border-b border-white/[0.06]">
                            <tr>
                              {["Run ID","Timestamp","Platform","Mode","Workers","Leads","Runtime","Success","Email %","LinkedIn %","Telegram %"].map((h) => (
                                <th key={h} className="px-4 py-3 text-[10px] font-semibold uppercase tracking-wider text-slate-600 whitespace-nowrap">{h}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {history.map((run, i) => {
                              const ts = run.timestamp ? new Date(run.timestamp).toLocaleString() : "—"
                              return (
                                <tr key={i} className="border-t border-white/[0.03] hover:bg-white/[0.02] transition-colors">
                                  <td className="px-4 py-3 text-violet-400 font-mono text-[10px]">{run.run_id}</td>
                                  <td className="px-4 py-3 text-slate-500 whitespace-nowrap">{ts}</td>
                                  <td className="px-4 py-3 text-slate-300 capitalize">{run.platform}</td>
                                  <td className="px-4 py-3 text-slate-400">{run.mode}</td>
                                  <td className="px-4 py-3 text-slate-300 font-semibold">{run.workers}</td>
                                  <td className="px-4 py-3 text-white font-semibold">{run.successful}</td>
                                  <td className="px-4 py-3 text-sky-300 font-mono">{run.total_time_human}</td>
                                  <td className="px-4 py-3">
                                    <span className={`font-semibold ${run.success_rate >= 80 ? "text-emerald-400" : run.success_rate >= 50 ? "text-amber-400" : "text-rose-400"}`}>
                                      {run.success_rate}%
                                    </span>
                                  </td>
                                  <td className="px-4 py-3 text-emerald-300 font-mono">{run.email_coverage}%</td>
                                  <td className="px-4 py-3 text-sky-300 font-mono">{run.linkedin_coverage}%</td>
                                  <td className="px-4 py-3 text-violet-300 font-mono">{run.telegram_coverage}%</td>
                                </tr>
                              )
                            })}
                          </tbody>
                        </table>
                      </div>
                      <div className="px-4 py-2.5 border-t border-white/[0.05] text-slate-600 text-xs">
                        {history.length} runs stored (last 20 kept)
                      </div>
                    </div>
                  )}
                </div>
              )
            })()}
          </div>
        )}

      </main>

      {/* Footer */}
      <footer className="border-t border-white/[0.04] mt-10 py-5 relative z-10">
        <div className="max-w-[1400px] mx-auto px-6 flex items-center justify-between text-slate-700 text-xs">
          <span>Lead Intelligence Platform</span>
          <span>Concurrent extraction · {workers} workers · ordered output</span>
        </div>
      </footer>
    </div>
  )
}

export default App
