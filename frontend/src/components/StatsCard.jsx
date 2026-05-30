export default function StatsCard({ title, value }) {
  return (
    <div className="bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-lg">

      <h2 className="text-slate-400 text-sm">
        {title}
      </h2>

      <p className="text-3xl font-bold mt-2 text-cyan-400">
        {value}
      </p>

    </div>
  )
}