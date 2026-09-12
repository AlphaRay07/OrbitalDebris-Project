import { useEffect, useState } from "react";
import { getConjunctions } from "./api";

export default function Threats({ selectedId, onSelectThreat }) {
  const [conjunctions, setConjunctions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    getConjunctions()
      .then((data) => {
        setConjunctions(data || []);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="w-80 h-full bg-[#0E141C] border-r border-[#1E2833] p-4 text-[#6B7A8C] font-mono text-xs">
        Loading conjunction threats...
      </div>
    );
  }

  if (error) {
    return (
      <div className="w-80 h-full bg-[#0E141C] border-r border-[#1E2833] p-4 text-[#E5484D] font-mono text-xs">
        Error loading threats: {error}
      </div>
    );
  }

  return (
    <div className="w-80 h-full bg-[#0E141C] border-r border-[#1E2833] flex flex-col font-mono text-xs">
      {/* Header */}
      <div className="p-3 border-b border-[#1E2833] flex items-center justify-between bg-[#070A0F]/50">
        <span className="font-bold text-[#C8D4E0] tracking-wider uppercase text-[11px]">
          ACTIVE CONJUNCTIONS ({conjunctions.length})
        </span>
        <span className="text-[10px] text-[#6B7A8C]">SORTED BY RISK</span>
      </div>

      {/* Threat List */}
      <div className="flex-1 overflow-y-auto divide-y divide-[#1E2833]">
        {conjunctions.map((c) => {
          const isSelected = selectedId === c.id;
          const isRed = c.risk === "RED";
          const isAmber = c.risk === "AMBER";

          return (
            <div
              key={c.id}
              onClick={() => onSelectThreat && onSelectThreat(c.id, c)}
              className={`p-3 cursor-pointer transition-colors relative ${

                isSelected
                  ? "bg-[#1E2833] text-white"
                  : "hover:bg-[#1E2833]/50 text-[#C8D4E0]"
              }`}
            >
              {/* Top row: Risk badge + Object Name + SIM tag */}
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-2">
                  <span
                    className={`px-1.5 py-0.5 rounded text-[10px] font-bold border ${
                      isRed
                        ? "bg-red-950 text-[#E5484D] border-red-800/50"
                        : isAmber
                        ? "bg-amber-950 text-[#E8A33D] border-amber-800/50"
                        : "bg-emerald-950 text-[#3DD68C] border-emerald-800/50"
                    }`}
                  >
                    {c.risk}
                  </span>
                  {c.simulated && (
                    <span className="px-1 py-0.5 rounded bg-blue-950 text-blue-400 border border-blue-800/50 text-[9px] font-bold">
                      SIM
                    </span>
                  )}
                </div>
                <span className="text-[10px] text-[#6B7A8C] font-semibold">{c.id}</span>
              </div>

              {/* Secondary Object Name */}
              <div className="font-bold text-xs truncate text-[#C8D4E0] mb-1">
                {c.secondary.name}
              </div>

              {/* Metrics Grid */}
              <div className="grid grid-cols-2 gap-2 text-[10px] text-[#6B7A8C] mt-2 pt-2 border-t border-[#1E2833]/40">
                <div>
                  MISS DIST:{" "}
                  <span className="text-[#C8D4E0] font-bold">
                    {c.miss_distance_km} km
                  </span>
                </div>
                <div>
                  P<sub>c</sub>:{" "}
                  <span className="text-[#C8D4E0] font-bold">
                    {c.pc < 0.0001 ? c.pc.toExponential(2) : c.pc}
                  </span>
                </div>
                <div className="col-span-2 truncate">
                  TCA:{" "}
                  <span className="text-[#C8D4E0] font-bold">
                    {new Date(c.tca).toUTCString().replace("GMT", "UTC")}
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
