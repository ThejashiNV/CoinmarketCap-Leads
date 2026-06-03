import { useEffect, useState } from "react"

// Deployment config: set VITE_API_BASE to the backend URL in Vercel.
const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000"

const SUPPORTED_DOMAINS = [
  "coinmarketcap.com",
  "coingecko.com",
  "coinranking.com",
]

const PLATFORM_OPTIONS = [
  "CoinMarketCap",
  "CoinGecko",
  "Coinranking",
]

const TOP_N_OPTIONS = [10, 20, 50]

function validateCategoryUrl(value) {
  const url = (value || "").trim()
  if (!url) return "Please enter a platform category URL."

  let parsed
  try {
    parsed = new URL(url)
  } catch {
    return "That is not a valid URL."
  }

  if (!/^https?:$/.test(parsed.protocol)) {
    return "URL must start with http:// or https://"
  }

  const host = parsed.hostname.replace(/^www\./, "")
  const supported = SUPPORTED_DOMAINS.some(
    (d) => host === d || host.endsWith("." + d)
  )
  if (!supported) {
    return "Unsupported platform. Use CoinMarketCap, CoinGecko or Coinranking."
  }

  if (!/categor/i.test(parsed.pathname)) {
    return "Enter a CATEGORY listing URL, e.g. .../cryptocurrency-category/"
  }

  return ""
}

/* ---- Icons (inline SVG) ---- */
const IconRocket = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M15.59 14.37a6 6 0 01-5.84 7.38v-4.8m5.84-2.58a14.98 14.98 0 003.46-8.62 2.25 2.25 0 00-1.93-2.32 14.98 14.98 0 00-8.62 3.46m5.09 7.48V16.5a2.25 2.25 0 00-2.25 2.25H9a2.25 2.25 0 00-2.25-2.25v-2.13m5.84-2.58L9.41 9.63m0 0a5.98 5.98 0 00-7.38 5.84h4.8m2.58-5.84v-.13A2.25 2.25 0 0111.66 7.5h.13" />
  </svg>
)
const IconDownload = () => (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
  </svg>
)
const IconTerminal = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 7.5l3 2.25-3 2.25m4.5 0h3m-9 8.25h13.5A2.25 2.25 0 0021 18V6a2.25 2.25 0 00-2.25-2.25H5.25A2.25 2.25 0 003 6v12a2.25 2.25 0 002.25 2.25z" />
  </svg>
)
const IconTable = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M3.375 19.5h17.25m-17.25 0a1.125 1.125 0 01-1.125-1.125M3.375 19.5h7.5c.621 0 1.125-.504 1.125-1.125m-9.75 0V5.625m0 12.75v-1.5c0-.621.504-1.125 1.125-1.125m18.375 2.625V5.625m0 12.75c0 .621-.504 1.125-1.125 1.125m1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125m0 3.75h-7.5A1.125 1.125 0 0112 18.375m9.75-12.75c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125m19.5 0v1.5c0 .621-.504 1.125-1.125 1.125M2.25 5.625v1.5c0 .621.504 1.125 1.125 1.125m0 0h17.25m-17.25 0h7.5c.621 0 1.125.504 1.125 1.125M3.375 8.25c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125m17.25-3.75h-7.5c-.621 0-1.125.504-1.125 1.125m8.625-1.125c.621 0 1.125.504 1.125 1.125v1.5c0 .621-.504 1.125-1.125 1.125m-17.25 0h7.5m-7.5 0c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125M12 10.875v-1.5m0 1.5c0 .621-.504 1.125-1.125 1.125M12 10.875c0 .621.504 1.125 1.125 1.125m-2.25 0c.621 0 1.125.504 1.125 1.125M13.125 12h7.5m-7.5 0c-.621 0-1.125.504-1.125 1.125M20.625 12c.621 0 1.125.504 1.125 1.125v1.5c0 .621-.504 1.125-1.125 1.125m-17.25 0h7.5M12 14.625v-1.5m0 1.5c0 .621-.504 1.125-1.125 1.125M12 14.625c0 .621.504 1.125 1.125 1.125m-2.25 0c.621 0 1.125.504 1.125 1.125m0 0v1.5c0 .621-.504 1.125-1.125 1.125" />
  </svg>
)
const Spinner = () => (
  <svg className="w-5 h-5 animate-spin-slow" fill="none" viewBox="0 0 24 24">
    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
  </svg>
)

function App() {
  const [platformName, setPlatformName] = useState("CoinMarketCap")
  const [platformUrl, setPlatformUrl] = useState("")
  const [urlError, setUrlError] = useState("")

  const [categories, setCategories] = useState([])
  const [selectedCategory, setSelectedCategory] = useState("")
  const [loadingCategories, setLoadingCategories] = useState(false)

  const [topNOption, setTopNOption] = useState("20")
  const [customN, setCustomN] = useState("")
  const [mode, setMode] = useState("ranked")

  const [loading, setLoading] = useState(false)
  const [logs, setLogs] = useState([])
  const [leads, setLeads] = useState([])

  const fetchLeads = async () => {
    try {
      const response = await fetch(`${API_BASE}/leads`)
      const data = await response.json()
      setLeads(Array.isArray(data) ? data : [])
    } catch (error) {
      console.error(error)
    }
  }

  useEffect(() => {
    fetchLeads()
  }, [])

  const fetchCategories = async () => {
    const error = validateCategoryUrl(platformUrl)
    setUrlError(error)
    if (error) return

    setLoadingCategories(true)
    setCategories([])
    setSelectedCategory("")

    try {
      const response = await fetch(
        `${API_BASE}/categories?url=${encodeURIComponent(platformUrl.trim())}`
      )
      const result = await response.json()

      if (result.status === "ok" && result.categories?.length) {
        setCategories(result.categories)
        setSelectedCategory(result.categories[0].url)
      } else {
        setUrlError(result.message || "Could not load categories.")
      }
    } catch (err) {
      console.error(err)
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

  const streamLogs = () => {
    const eventSource = new EventSource(`${API_BASE}/live-logs`)

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data)
      setLogs((prev) => [data, ...prev])

      if (data.done) {
        eventSource.close()
        setLoading(false)
        fetchLeads()
      }
    }

    eventSource.onerror = () => {
      eventSource.close()
      setLoading(false)
    }
  }

  const startExtraction = async () => {
    if (!selectedCategory) {
      setLogs([{ message: "Select a category first." }])
      return
    }

    const topN = resolveTopN()
    if (!topN) {
      setLogs([{ message: "Enter a valid number of projects." }])
      return
    }

    setLoading(true)
    setLogs([])

    try {
      const response = await fetch(`${API_BASE}/start-extraction`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category_url: selectedCategory, top_n: topN, mode }),
      })
      const result = await response.json()

      if (result.status === "started") {
        streamLogs()
      } else {
        setLogs([{ message: result.message || "Could not start extraction." }])
        setLoading(false)
      }
    } catch (err) {
      console.error(err)
      setLogs([{ message: "Failed to reach the extraction API." }])
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#020617] text-white overflow-x-hidden">
      {/* Ambient glow orbs */}
      <div className="fixed top-[-10%] left-[-5%] w-[500px] h-[500px] rounded-full bg-cyan-500/10 blur-[150px] animate-pulse-glow pointer-events-none" />
      <div className="fixed bottom-[-10%] right-[-5%] w-[500px] h-[500px] rounded-full bg-purple-600/10 blur-[150px] animate-pulse-glow pointer-events-none" style={{ animationDelay: "2s" }} />
      <div className="fixed top-[40%] left-[50%] w-[300px] h-[300px] rounded-full bg-indigo-500/5 blur-[120px] animate-pulse-glow pointer-events-none" style={{ animationDelay: "3s" }} />

      <div className="relative z-10 max-w-[1400px] mx-auto px-4 sm:px-6 lg:px-10 py-8 lg:py-12">

        {/* ---- Header ---- */}
        <header className="mb-10 animate-fade-in-up">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-400 to-purple-500 flex items-center justify-center shadow-lg shadow-cyan-500/20">
              <IconRocket />
            </div>
            <span className="text-xs font-semibold tracking-widest uppercase text-slate-500">
              Lead Intelligence Platform
            </span>
          </div>
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-black tracking-tight">
            <span className="bg-gradient-to-r from-cyan-300 via-sky-400 to-purple-400 bg-clip-text text-transparent">
              Crypto Lead
            </span>{" "}
            <span className="text-white">Extraction</span>
          </h1>
          <p className="text-slate-500 mt-2 text-base lg:text-lg max-w-2xl">
            Multi-platform category-driven enrichment. Extract emails, LinkedIn profiles, and Telegram channels from top crypto projects.
          </p>
        </header>

        {/* ---- Control Panel ---- */}
        <section className="glass-card rounded-2xl p-6 lg:p-8 mb-8 animate-fade-in-up animate-fade-in-up-1">
          <div className="flex items-center gap-2 mb-6">
            <div className="w-2 h-2 rounded-full bg-cyan-400" />
            <h2 className="text-lg font-bold text-white tracking-tight">Configure Extraction</h2>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {/* Platform */}
            <div>
              <label className="block text-slate-500 text-xs font-semibold uppercase tracking-wider mb-2">
                Platform
              </label>
              <select
                value={platformName}
                onChange={(e) => setPlatformName(e.target.value)}
                disabled={loading}
                className="w-full bg-slate-900/80 border border-white/[0.06] rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:ring-2 focus:ring-cyan-500/30 focus:border-cyan-500/40 disabled:opacity-40 transition-all"
              >
                {PLATFORM_OPTIONS.map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </div>

            {/* Category URL */}
            <div>
              <label className="block text-slate-500 text-xs font-semibold uppercase tracking-wider mb-2">
                Category URL
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={platformUrl}
                  onChange={(e) => {
                    setPlatformUrl(e.target.value)
                    if (urlError) setUrlError("")
                  }}
                  placeholder="https://coinmarketcap.com/cryptocurrency-category/"
                  disabled={loading}
                  className="flex-1 bg-slate-900/80 border border-white/[0.06] rounded-xl px-4 py-3 text-sm text-white placeholder-slate-700 focus:outline-none focus:ring-2 focus:ring-cyan-500/30 focus:border-cyan-500/40 disabled:opacity-40 transition-all"
                />
                <button
                  onClick={fetchCategories}
                  disabled={loading || loadingCategories}
                  className="bg-white/[0.06] hover:bg-white/[0.1] border border-white/[0.06] text-white font-medium text-sm px-5 py-3 rounded-xl transition-all disabled:opacity-40 whitespace-nowrap"
                >
                  {loadingCategories ? (
                    <span className="flex items-center gap-2"><Spinner /> Loading</span>
                  ) : "Fetch"}
                </button>
              </div>
              {urlError && (
                <p className="text-rose-400/90 text-xs mt-2 flex items-center gap-1">
                  <span className="w-1 h-1 rounded-full bg-rose-400 inline-block" />
                  {urlError}
                </p>
              )}
            </div>

            {/* Category dropdown */}
            <div>
              <label className="block text-slate-500 text-xs font-semibold uppercase tracking-wider mb-2">
                Category{" "}
                {categories.length > 0 && (
                  <span className="text-cyan-400/70 normal-case">
                    ({categories.length} found)
                  </span>
                )}
              </label>
              <select
                value={selectedCategory}
                onChange={(e) => setSelectedCategory(e.target.value)}
                disabled={loading || categories.length === 0}
                className="w-full bg-slate-900/80 border border-white/[0.06] rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:ring-2 focus:ring-cyan-500/30 focus:border-cyan-500/40 disabled:opacity-40 transition-all"
              >
                {categories.length === 0 ? (
                  <option value="">Fetch categories first</option>
                ) : (
                  categories.map((c) => (
                    <option key={c.url} value={c.url}>{c.name}</option>
                  ))
                )}
              </select>
            </div>

            {/* Top N */}
            <div>
              <label className="block text-slate-500 text-xs font-semibold uppercase tracking-wider mb-2">
                Number of Projects
              </label>
              <div className="flex gap-2">
                <select
                  value={topNOption}
                  onChange={(e) => setTopNOption(e.target.value)}
                  disabled={loading}
                  className="flex-1 bg-slate-900/80 border border-white/[0.06] rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:ring-2 focus:ring-cyan-500/30 focus:border-cyan-500/40 disabled:opacity-40 transition-all"
                >
                  {TOP_N_OPTIONS.map((n) => (
                    <option key={n} value={String(n)}>Top {n}</option>
                  ))}
                  <option value="custom">Custom</option>
                </select>
                {topNOption === "custom" && (
                  <input
                    type="number"
                    min="1"
                    value={customN}
                    onChange={(e) => setCustomN(e.target.value)}
                    placeholder="e.g. 35"
                    disabled={loading}
                    className="w-28 bg-slate-900/80 border border-white/[0.06] rounded-xl px-4 py-3 text-sm text-white placeholder-slate-700 focus:outline-none focus:ring-2 focus:ring-cyan-500/30 focus:border-cyan-500/40 disabled:opacity-40 transition-all"
                  />
                )}
              </div>
            </div>
          </div>

          {/* Extraction Mode */}
          <div className="mt-5">
            <label className="block text-slate-500 text-xs font-semibold uppercase tracking-wider mb-2">
              Extraction Mode
            </label>
            <div className="inline-flex rounded-xl overflow-hidden border border-white/[0.06]">
              <button
                type="button"
                onClick={() => setMode("ranked")}
                disabled={loading}
                className={`px-5 py-2.5 text-sm font-semibold transition-all ${
                  mode === "ranked"
                    ? "bg-gradient-to-r from-cyan-500/20 to-cyan-500/10 text-cyan-300 border-r border-white/[0.06]"
                    : "bg-slate-900/60 text-slate-500 hover:text-slate-300 border-r border-white/[0.06]"
                } disabled:opacity-40`}
              >
                Top Ranked
              </button>
              <button
                type="button"
                onClick={() => setMode("recent")}
                disabled={loading}
                className={`px-5 py-2.5 text-sm font-semibold transition-all ${
                  mode === "recent"
                    ? "bg-gradient-to-r from-purple-500/20 to-purple-500/10 text-purple-300"
                    : "bg-slate-900/60 text-slate-500 hover:text-slate-300"
                } disabled:opacity-40`}
              >
                Recently Added
              </button>
            </div>
            <p className="text-slate-600 text-xs mt-1.5">
              {mode === "ranked"
                ? "Projects sorted by market cap rank."
                : "Projects sorted by listing date (newest first)."}
            </p>
          </div>

          {/* Start Button */}
          <div className="mt-7">
            <button
              onClick={startExtraction}
              disabled={loading || categories.length === 0}
              className="group relative inline-flex items-center gap-2.5 bg-gradient-to-r from-cyan-500 to-purple-600 hover:from-cyan-400 hover:to-purple-500 text-white font-bold text-sm px-8 py-3.5 rounded-xl shadow-lg shadow-cyan-500/20 hover:shadow-cyan-400/30 transition-all duration-300 disabled:opacity-40 disabled:shadow-none"
            >
              {loading ? (
                <>
                  <Spinner />
                  <span>Running Extraction...</span>
                </>
              ) : (
                <>
                  <IconRocket />
                  <span>Start Extraction</span>
                </>
              )}
            </button>
          </div>
        </section>

        {/* ---- Live Logs ---- */}
        <section className="glass-card rounded-2xl p-6 mb-8 animate-fade-in-up animate-fade-in-up-2">
          <div className="flex items-center gap-2 mb-4">
            <IconTerminal />
            <h2 className="text-lg font-bold text-white tracking-tight">Live Progress</h2>
            {loading && (
              <span className="ml-auto flex items-center gap-1.5 text-xs text-cyan-400/80 font-medium">
                <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
                Streaming
              </span>
            )}
          </div>
          <div className="bg-black/50 rounded-xl p-4 h-[240px] overflow-y-auto border border-white/[0.03]">
            {logs.length === 0 ? (
              <p className="text-slate-700 font-mono text-xs">
                {">"} Logs will appear here once extraction starts...
              </p>
            ) : (
              logs.map((log, index) => (
                <div
                  key={index}
                  className={`font-mono text-xs leading-relaxed break-all ${
                    log.done
                      ? "text-cyan-400 font-semibold"
                      : log.message?.includes("error")
                      ? "text-rose-400/80"
                      : log.message?.includes("website=")
                      ? "text-slate-400"
                      : "text-emerald-400/80"
                  }`}
                >
                  <span className="text-slate-700 select-none mr-1">{">"}</span>
                  {log.message}
                </div>
              ))
            )}
          </div>
        </section>

        {/* ---- Extracted Leads ---- */}
        <section className="glass-card rounded-2xl p-6 animate-fade-in-up animate-fade-in-up-3">
          <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4 mb-5">
            <div className="flex items-center gap-2">
              <IconTable />
              <h2 className="text-lg font-bold text-white tracking-tight">
                Extracted Leads
              </h2>
              <span className="ml-1 bg-white/[0.06] text-slate-400 text-xs font-semibold px-2.5 py-0.5 rounded-full">
                {leads.length}
              </span>
            </div>
            <div className="flex gap-2">
              <a
                href={`${API_BASE}/download/csv`}
                className="inline-flex items-center gap-1.5 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/20 font-medium text-xs px-4 py-2 rounded-lg transition-all"
              >
                <IconDownload /> CSV
              </a>
              <a
                href={`${API_BASE}/download/xlsx`}
                className="inline-flex items-center gap-1.5 bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-400 border border-indigo-500/20 font-medium text-xs px-4 py-2 rounded-lg transition-all"
              >
                <IconDownload /> XLSX
              </a>
            </div>
          </div>

          <div
            className="overflow-auto rounded-xl border border-white/[0.04]"
            style={{ maxHeight: "560px" }}
          >
            <table className="w-full text-left text-sm">
              <thead className="sticky top-0 z-10">
                <tr className="bg-slate-900/95 backdrop-blur-sm border-b border-white/[0.04]">
                  <th className="px-4 py-3.5 text-xs font-semibold uppercase tracking-wider text-slate-500">#</th>
                  <th className="px-4 py-3.5 text-xs font-semibold uppercase tracking-wider text-slate-500">Project</th>
                  <th className="px-4 py-3.5 text-xs font-semibold uppercase tracking-wider text-slate-500">Website</th>
                  <th className="px-4 py-3.5 text-xs font-semibold uppercase tracking-wider text-slate-500">Email</th>
                  <th className="px-4 py-3.5 text-xs font-semibold uppercase tracking-wider text-slate-500">LinkedIn</th>
                  <th className="px-4 py-3.5 text-xs font-semibold uppercase tracking-wider text-slate-500">Telegram</th>
                  <th className="px-4 py-3.5 text-xs font-semibold uppercase tracking-wider text-slate-500">Twitter</th>
                </tr>
              </thead>
              <tbody>
                {leads.length === 0 ? (
                  <tr>
                    <td
                      colSpan={7}
                      className="px-4 py-16 text-center"
                    >
                      <div className="flex flex-col items-center gap-2">
                        <div className="w-10 h-10 rounded-full bg-white/[0.03] flex items-center justify-center">
                          <IconTable />
                        </div>
                        <p className="text-slate-600 text-sm">No leads yet. Run an extraction to populate this table.</p>
                      </div>
                    </td>
                  </tr>
                ) : (
                  leads.map((lead, index) => (
                    <tr
                      key={index}
                      className="border-t border-white/[0.03] table-row-hover"
                    >
                      <td className="px-4 py-3 text-slate-600 text-xs font-mono">
                        {index + 1}
                      </td>
                      <td className="px-4 py-3 font-semibold text-white text-sm">
                        {lead["Project Name"]}
                      </td>
                      <td className="px-4 py-3">
                        <Cell value={lead["Official Website URL"]} link />
                      </td>
                      <td className="px-4 py-3">
                        <EmailCell value={lead["Official Email ID"]} />
                      </td>
                      <td className="px-4 py-3">
                        <Cell value={lead["LinkedIn URLs"]} link />
                      </td>
                      <td className="px-4 py-3">
                        <Cell value={lead["Telegram URLs"]} link />
                      </td>
                      <td className="px-4 py-3">
                        <Cell value={lead["Twitter URLs"]} link />
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>

        {/* ---- Footer ---- */}
        <footer className="mt-10 text-center text-slate-700 text-xs pb-4">
          Crypto Lead Extraction Platform
        </footer>
      </div>
    </div>
  )
}

/* ---- Cell renderers ---- */
function Cell({ value, link }) {
  if (!value || value === "N/A") {
    return <span className="text-slate-700">--</span>
  }
  const first = String(value).split(";")[0].trim()
  if (link && /^https?:\/\//.test(first)) {
    // Show clean domain/path instead of full URL
    let label = first
    try {
      const u = new URL(first)
      label = u.hostname.replace(/^www\./, "") + (u.pathname !== "/" ? u.pathname : "")
      if (label.length > 35) label = label.slice(0, 33) + "..."
    } catch { /* keep raw */ }
    return (
      <a
        href={first}
        target="_blank"
        rel="noreferrer"
        className="text-sky-400/80 hover:text-sky-300 text-xs transition-colors"
        title={first}
      >
        {label}
      </a>
    )
  }
  return <span className="text-sm">{value}</span>
}

function EmailCell({ value }) {
  if (!value || value === "N/A") {
    return <span className="text-slate-700">--</span>
  }
  return (
    <span className="text-emerald-400/80 text-xs font-medium">{value}</span>
  )
}

export default App
