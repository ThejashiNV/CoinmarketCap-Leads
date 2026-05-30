import {
  Activity,
  Mail,
  Linkedin,
  Send,
  Database,
  Play,
} from "lucide-react"

const leads = [
  {
    project: "Bitcoin",
    email: "info@bitcoin.org",
    source: "Website",
    status: "Completed",
  },
  {
    project: "Ethereum",
    email: "contact@ethereum.org",
    source: "Website",
    status: "Completed",
  },
  {
    project: "Solana",
    email: "hello@solana.org",
    source: "LinkedIn",
    status: "Running",
  },
]

function StatCard({ title, value, icon }) {
  return (
    <div className="backdrop-blur-xl bg-white/5 border border-white/10 rounded-2xl p-6 shadow-2xl hover:scale-105 transition duration-300">

      <div className="flex justify-between items-center">

        <div>
          <p className="text-slate-400 text-sm">
            {title}
          </p>

          <h2 className="text-4xl font-bold mt-3 text-white">
            {value}
          </h2>
        </div>

        <div className="text-cyan-400">
          {icon}
        </div>

      </div>

    </div>
  )
}

export default function Dashboard() {
  return (
    <div className="relative z-10 px-10 py-8">

      {/* Navbar */}
      <div className="flex justify-between items-center mb-10">

        <div>
          <h1 className="text-5xl font-extrabold text-white">
            Crypto Leads Dashboard
          </h1>

          <p className="text-slate-400 mt-2">
            AI Powered CoinMarketCap Extraction System
          </p>
        </div>

        <button className="flex items-center gap-2 bg-cyan-500 hover:bg-cyan-400 text-black font-bold px-6 py-3 rounded-xl shadow-lg transition duration-300">

          <Play size={18} />

          Start Extraction

        </button>

      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">

        <StatCard
          title="Projects"
          value="124"
          icon={<Database size={38} />}
        />

        <StatCard
          title="Emails"
          value="89"
          icon={<Mail size={38} />}
        />

        <StatCard
          title="LinkedIn"
          value="72"
          icon={<Linkedin size={38} />}
        />

        <StatCard
          title="Telegram"
          value="64"
          icon={<Send size={38} />}
        />

      </div>

      {/* Live Status */}
      <div className="mt-10 backdrop-blur-xl bg-white/5 border border-white/10 rounded-2xl p-6 shadow-2xl">

        <div className="flex justify-between items-center mb-6">

          <h2 className="text-2xl font-bold text-white">
            Live Extraction Status
          </h2>

          <div className="flex items-center gap-2 text-green-400">
            <Activity size={18} />
            Running
          </div>

        </div>

        <div className="space-y-4">

          {leads.map((lead, index) => (

            <div
              key={index}
              className="bg-slate-900/60 border border-white/5 rounded-xl p-5 flex justify-between items-center hover:bg-slate-800/70 transition"
            >

              <div>
                <h3 className="text-white font-semibold text-lg">
                  {lead.project}
                </h3>

                <p className="text-slate-400">
                  {lead.email}
                </p>
              </div>

              <div className="text-right">

                <p className="text-cyan-400 font-semibold">
                  {lead.source}
                </p>

                <p className="text-green-400 text-sm">
                  {lead.status}
                </p>

              </div>

            </div>

          ))}

        </div>

      </div>

    </div>
  )
}