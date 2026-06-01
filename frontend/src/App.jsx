import { useEffect, useState } from "react"

const API_BASE = "http://127.0.0.1:8000"

const SUPPORTED_DOMAINS = [
  "coinmarketcap.com",
  "coingecko.com",
  "coinranking.com",
]

const PLATFORM_OPTIONS = [
  "CoinMarketCap",
  "CoinGecko",
  "Coinnomi",
  "Coinrank",
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

function StatCard({ title, value, accent }) {
  return (
    <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-6 shadow-2xl hover:scale-105 transition-all duration-300">
      <p className="text-slate-400 text-sm">{title}</p>
      <h1 className={`text-4xl font-bold mt-3 ${accent}`}>{value}</h1>
    </div>
  )
}

function App() {
  const [platformName, setPlatformName] = useState("CoinMarketCap")
  const [platformUrl, setPlatformUrl] = useState("")
  const [urlError, setUrlError] = useState("")

  const [categories, setCategories] = useState([])
  const [selectedCategory, setSelectedCategory] = useState("")
  const [loadingCategories, setLoadingCategories] = useState(false)

  const [topNOption, setTopNOption] = useState("20")
  const [customN, setCustomN] = useState("")

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
        body: JSON.stringify({ category_url: selectedCategory, top_n: topN }),
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

  const countWith = (field) =>
    leads.filter((l) => l[field] && l[field] !== "N/A").length

  return (
    <div className="min-h-screen bg-[#020617] text-white p-6 md:p-10 overflow-x-hidden">
      {/* Glow */}
      <div className="absolute top-0 left-0 w-96 h-96 bg-cyan-500/20 blur-[120px]" />
      <div className="absolute bottom-0 right-0 w-96 h-96 bg-purple-500/20 blur-[120px]" />

      {/* Header */}
      <div className="relative z-10 mb-10">
        <h1 className="text-4xl md:text-6xl font-extrabold bg-gradient-to-r from-cyan-400 via-sky-400 to-purple-400 bg-clip-text text-transparent">
          Crypto Lead Extraction
        </h1>
        <p className="text-slate-400 mt-3 text-lg">
          Multi-Platform Category-Driven Enrichment Dashboard
        </p>
      </div>

      {/* Control Panel */}
      <div className="relative z-10 bg-white/5 border border-white/10 backdrop-blur-xl rounded-2xl p-6 md:p-8 shadow-2xl">
        <h2 className="text-2xl font-bold mb-6">Configure Extraction</h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Platform Name */}
          <div>
            <label className="block text-slate-400 text-sm mb-2">
              Platform Name
            </label>
            <select
              value={platformName}
              onChange={(e) => setPlatformName(e.target.value)}
              disabled={loading}
              className="w-full bg-slate-900/70 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-cyan-400/50 disabled:opacity-50"
            >
              {PLATFORM_OPTIONS.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </div>

          {/* Category URL */}
          <div>
            <label className="block text-slate-400 text-sm mb-2">
              Platform Category URL
            </label>
            <div className="flex gap-3">
              <input
                type="text"
                value={platformUrl}
                onChange={(e) => {
                  setPlatformUrl(e.target.value)
                  if (urlError) setUrlError("")
                }}
                placeholder="https://coinmarketcap.com/cryptocurrency-category/"
                disabled={loading}
                className="flex-1 bg-slate-900/70 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-slate-600 focus:outline-none focus:border-cyan-400/50 disabled:opacity-50"
              />
              <button
                onClick={fetchCategories}
                disabled={loading || loadingCategories}
                className="bg-sky-500 hover:bg-sky-400 text-white font-semibold px-5 py-3 rounded-xl transition disabled:opacity-60 whitespace-nowrap"
              >
                {loadingCategories ? "Loading..." : "Fetch Categories"}
              </button>
            </div>
            {urlError && (
              <p className="text-rose-400 text-sm mt-2">{urlError}</p>
            )}
          </div>

          {/* Category dropdown */}
          <div>
            <label className="block text-slate-400 text-sm mb-2">
              Category{" "}
              {categories.length > 0 && (
                <span className="text-slate-600">
                  ({categories.length} found)
                </span>
              )}
            </label>
            <select
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
              disabled={loading || categories.length === 0}
              className="w-full bg-slate-900/70 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-cyan-400/50 disabled:opacity-50"
            >
              {categories.length === 0 ? (
                <option value="">Fetch categories first</option>
              ) : (
                categories.map((c) => (
                  <option key={c.url} value={c.url}>
                    {c.name}
                  </option>
                ))
              )}
            </select>
          </div>

          {/* Top N */}
          <div>
            <label className="block text-slate-400 text-sm mb-2">
              Number of Projects
            </label>
            <div className="flex gap-3">
              <select
                value={topNOption}
                onChange={(e) => setTopNOption(e.target.value)}
                disabled={loading}
                className="flex-1 bg-slate-900/70 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-cyan-400/50 disabled:opacity-50"
              >
                {TOP_N_OPTIONS.map((n) => (
                  <option key={n} value={String(n)}>
                    Top {n}
                  </option>
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
                  className="w-32 bg-slate-900/70 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-slate-600 focus:outline-none focus:border-cyan-400/50 disabled:opacity-50"
                />
              )}
            </div>
          </div>
        </div>

        <button
          onClick={startExtraction}
          disabled={loading || categories.length === 0}
          className="mt-8 w-full md:w-auto bg-gradient-to-r from-cyan-400 to-purple-500 hover:opacity-90 text-black font-bold px-8 py-3 rounded-xl shadow-lg transition disabled:opacity-50"
        >
          {loading ? "Running Extraction..." : "Start Extraction"}
        </button>
      </div>

      {/* Stats */}
      <div className="relative z-10 grid grid-cols-2 md:grid-cols-4 gap-6 mt-10">
        <StatCard
          title="Processed"
          value={leads.length}
          accent="text-cyan-400"
        />
        <StatCard
          title="Emails Found"
          value={countWith("Official Email ID")}
          accent="text-emerald-400"
        />
        <StatCard
          title="LinkedIn Found"
          value={countWith("LinkedIn URLs")}
          accent="text-blue-400"
        />
        <StatCard
          title="Telegram Found"
          value={countWith("Telegram URLs")}
          accent="text-purple-400"
        />
      </div>

      {/* Live Logs */}
      <div className="relative z-10 mt-10 bg-white/5 border border-white/10 backdrop-blur-xl rounded-2xl p-6 shadow-2xl">
        <h2 className="text-2xl font-bold mb-6">Live Progress</h2>
        <div className="bg-black/40 rounded-xl p-4 h-[280px] overflow-y-auto space-y-1">
          {logs.length === 0 ? (
            <p className="text-slate-600 font-mono text-sm">
              Logs will appear here once extraction starts.
            </p>
          ) : (
            logs.map((log, index) => (
              <div
                key={index}
                className="text-green-400 font-mono text-sm break-all"
              >
                {log.message}
              </div>
            ))
          )}
        </div>
      </div>

      {/* Results */}
      <div className="relative z-10 mt-10 bg-white/5 border border-white/10 backdrop-blur-xl rounded-2xl p-6 shadow-2xl">
        <div className="flex flex-col md:flex-row justify-between md:items-center gap-4 mb-6">
          <h2 className="text-2xl font-bold">
            Extracted Leads{" "}
            <span className="text-slate-500 text-lg">({leads.length})</span>
          </h2>
          <div className="flex gap-3">
            <a
              href={`${API_BASE}/download/csv`}
              className="bg-emerald-500 hover:bg-emerald-400 text-black font-semibold px-5 py-2.5 rounded-xl transition"
            >
              Download CSV
            </a>
            <a
              href={`${API_BASE}/download/xlsx`}
              className="bg-indigo-500 hover:bg-indigo-400 text-white font-semibold px-5 py-2.5 rounded-xl transition"
            >
              Download XLSX
            </a>
          </div>
        </div>

        <div className="overflow-x-auto rounded-xl border border-white/5">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-900/80 text-slate-400">
              <tr>
                <th className="px-4 py-3">Project</th>
                <th className="px-4 py-3">Website</th>
                <th className="px-4 py-3">Email</th>
                <th className="px-4 py-3">LinkedIn</th>
                <th className="px-4 py-3">Telegram</th>
                <th className="px-4 py-3">Twitter</th>
              </tr>
            </thead>
            <tbody>
              {leads.length === 0 ? (
                <tr>
                  <td
                    colSpan={6}
                    className="px-4 py-8 text-center text-slate-600"
                  >
                    No leads yet. Run an extraction to populate this table.
                  </td>
                </tr>
              ) : (
                leads.map((lead, index) => (
                  <tr
                    key={index}
                    className="border-t border-white/5 hover:bg-white/5"
                  >
                    <td className="px-4 py-3 font-semibold text-cyan-400">
                      {lead["Project Name"]}
                    </td>
                    <td className="px-4 py-3 break-all">
                      <Cell value={lead["Official Website URL"]} link />
                    </td>
                    <td className="px-4 py-3 break-all">
                      {lead["Official Email ID"] &&
                      lead["Official Email ID"] !== "N/A"
                        ? lead["Official Email ID"]
                        : "—"}
                    </td>
                    <td className="px-4 py-3 break-all">
                      <Cell value={lead["LinkedIn URLs"]} link />
                    </td>
                    <td className="px-4 py-3 break-all">
                      <Cell value={lead["Telegram URLs"]} link />
                    </td>
                    <td className="px-4 py-3 break-all">
                      <Cell value={lead["Twitter URLs"]} link />
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function Cell({ value, link }) {
  if (!value || value === "N/A") {
    return <span className="text-slate-600">—</span>
  }
  // Fields may hold several "; "-joined URLs; show the first as a link.
  const first = String(value).split(";")[0].trim()
  if (link && /^https?:\/\//.test(first)) {
    return (
      <a
        href={first}
        target="_blank"
        rel="noreferrer"
        className="text-sky-400 hover:underline"
      >
        {first}
      </a>
    )
  }
  return <span>{value}</span>
}

export default App
