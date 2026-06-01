export default function Navbar() {
  return (
    <div className="w-full bg-slate-900 px-8 py-4 flex justify-between items-center border-b border-slate-700">

      <h1 className="text-2xl font-bold text-cyan-400">
        Crypto Leads Extractor
      </h1>

      <button className="bg-cyan-500 hover:bg-cyan-600 px-4 py-2 rounded-lg font-semibold">
        Start Extraction
      </button>

    </div>
  )
}