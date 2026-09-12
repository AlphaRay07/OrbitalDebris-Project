import { useEffect, useState } from "react";
import { getLedger } from "./api";

export default function LedgerTable({ onClose }) {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchLedgerData = () => {
    setLoading(true);
    getLedger()
      .then((data) => {
        setEntries(Array.isArray(data) ? data : []);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchLedgerData();
    const interval = setInterval(fetchLedgerData, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="w-full h-full bg-[#0E141C] border-l border-[#1E2833] flex flex-col font-mono text-xs text-[#C8D4E0] shadow-2xl z-30 overflow-hidden">
      {/* Top Header Bar */}
      <div className="p-3 border-b border-[#1E2833] bg-[#070A0F]/80 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="px-2 py-0.5 rounded bg-blue-950 text-blue-400 border border-blue-800/50 font-bold text-[11px]">
            IMMUTABLE LEDGER
          </span>
          <span className="font-bold text-white text-sm">BURN INTENT HASH CHAIN</span>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={fetchLedgerData}
            className="px-2 py-1 rounded bg-[#1E2833] hover:bg-[#283545] text-xs text-gray-300 font-semibold cursor-pointer"
          >
            ↻ REFRESH
          </button>
          {onClose && (
            <button
              onClick={onClose}
              className="w-6 h-6 rounded bg-[#1E2833] hover:bg-[#283545] text-[#C8D4E0] flex items-center justify-center font-bold text-sm cursor-pointer"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Main Table Body */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Banner Explaining Cryptographic Hash Chain Link */}
        <div className="p-3 bg-[#070A0F] border border-[#1E2833] rounded-lg text-xs text-gray-400 flex flex-col gap-1 shadow-md">
          <div className="text-white font-bold flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
            MULTI-OPERATOR MANEUVER INTENT COORDINATION
          </div>
          <div>
            Every published avoidance burn intent is cryptographically chained (`prev_hash` 🔗 `entry_hash`) to ensure multi-satellite operator transparency and prevent conflicting collision maneuvers.
          </div>
        </div>

        {loading && entries.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            Fetching cryptographic ledger entries...
          </div>
        ) : error ? (
          <div className="p-4 bg-red-950/60 border border-red-800 rounded text-red-300">
            Error loading ledger: {error}
          </div>
        ) : entries.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            No burn intents published to ledger yet.
          </div>
        ) : (
          <div className="overflow-x-auto border border-[#1E2833] rounded-lg">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-[#070A0F] border-b border-[#1E2833] text-[10px] text-[#6B7A8C] uppercase tracking-wider">
                  <th className="p-2.5">SEQ</th>
                  <th className="p-2.5">PREV HASH</th>
                  <th className="p-2.5">ENTRY HASH</th>
                  <th className="p-2.5">CDM ID</th>
                  <th className="p-2.5">OBJECT</th>
                  <th className="p-2.5">OPERATOR</th>
                  <th className="p-2.5 text-right">∆V (mm/s)</th>
                  <th className="p-2.5 text-right">BURN EPOCH</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1E2833]/60 bg-[#0E141C]">
                {entries.map((item, idx) => {
                  const prevRow = idx > 0 ? entries[idx - 1] : null;
                  const isChainValid = prevRow ? item.prev_hash === prevRow.entry_hash : item.prev_hash === "00000000";

                  return (
                    <tr key={item.seq || idx} className="hover:bg-[#1E2833]/40 transition-colors">
                      <td className="p-2.5 text-gray-400 font-bold">#{item.seq}</td>

                      {/* Visual Prev Hash Link */}
                      <td className="p-2.5 font-mono text-[11px]">
                        <span className="px-1.5 py-0.5 rounded bg-[#070A0F] border border-[#1E2833] text-gray-400">
                          {item.prev_hash}
                        </span>
                      </td>

                      {/* Entry Hash */}
                      <td className="p-2.5 font-mono text-[11px]">
                        <span className="px-1.5 py-0.5 rounded bg-blue-950/80 border border-blue-800 text-blue-300 font-bold">
                          {item.entry_hash}
                        </span>
                        {isChainValid && (
                          <span className="ml-1 text-[#3DD68C] text-[10px]" title="Chain Verified">🔗</span>
                        )}
                      </td>

                      <td className="p-2.5 font-bold text-white">{item.cdm_id}</td>
                      <td className="p-2.5 text-gray-300 font-semibold">{item.object}</td>
                      <td className="p-2.5">
                        <span className="px-1.5 py-0.5 rounded bg-purple-950 text-purple-300 border border-purple-800/50 font-bold text-[10px]">
                          {item.operator}
                        </span>
                      </td>
                      <td className="p-2.5 text-right font-bold text-[#3DD68C]">
                        {item.delta_v_mms ? item.delta_v_mms.toFixed(1) : "0.0"} mm/s
                      </td>
                      <td className="p-2.5 text-right text-gray-400 text-[10px]">
                        {item.burn_epoch ? item.burn_epoch.replace("T", " ").replace("Z", "") : "-"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
