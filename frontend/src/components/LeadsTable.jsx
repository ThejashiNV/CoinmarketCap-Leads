const sampleData = [
  {
    name: "Bitcoin",
    email: "info@bitcoin.org",
    source: "Website",
  },
  {
    name: "Ethereum",
    email: "contact@ethereum.org",
    source: "Website",
  },
]

export default function LeadsTable() {
  return (
    <div className="bg-slate-800 p-6 rounded-xl border border-slate-700 mt-6 overflow-auto">

      <h2 className="text-xl font-bold mb-4 text-cyan-400">
        Extracted Leads
      </h2>

      <table className="w-full">

        <thead>
          <tr className="border-b border-slate-700 text-left">
            <th className="py-3">Project</th>
            <th>Email</th>
            <th>Source</th>
          </tr>
        </thead>

        <tbody>
          {sampleData.map((item, index) => (
            <tr
              key={index}
              className="border-b border-slate-700"
            >
              <td className="py-3">
                {item.name}
              </td>

              <td>
                {item.email}
              </td>

              <td>
                {item.source}
              </td>
            </tr>
          ))}
        </tbody>

      </table>

    </div>
  )
}