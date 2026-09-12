import { useEffect, useState } from "react";
import { getConjunction } from "./api";
import EncounterPlane from "./EncounterPlane";
import PcChart from "./PcChart";

export default function ThreatDetails({ conjunctionId = "CDM-0001", threatSummary, onClose }) {
  const [details, setDetails] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!conjunctionId) return;
    setLoading(true);
    getConjunction(conjunctionId)
      .then((data) => {
        setDetails(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [conjunctionId]);

  if (loading) {
    return (
      <div className="w-96 h-full bg-[#0E141C] border-l border-[#1E2833] p-4 text-[#6B7A8C] font-mono text-xs z-30 shadow-2xl flex flex-col justify-center items-center">
        <div className="animate-spin w-6 h-6 border-2 border-emerald-500 border-t-transparent rounded-full mb-2" />
        Loading threat telemetry details...
      </div>
    );
  }

  if (error || !details) {
    return (
      <div className="w-96 h-full bg-[#0E141C] border-l border-[#1E2833] p-4 text-[#E5484D] font-mono text-xs z-30 shadow-2xl">
        Error loading details: {error || "No data"}
      </div>
    );
  }

  // Merge threat summary (from conjunctions.json) if available
  const displayId = conjunctionId;
  const secondaryObj = threatSummary?.secondary || details.secondary;
  const primaryObj = threatSummary?.primary || details.primary;
  const riskLevel = threatSummary?.risk || details.risk;
  const missDist = threatSummary?.miss_distance_km ?? details.miss_distance_km;
  const collisionPc = threatSummary?.pc ?? details.pc;
  const isSimulated = threatSummary?.simulated ?? details.simulated;


  const {
    id,
    primary,
    secondary,
    tca,
    miss_distance_km,
    relative_speed_kms,
    pc,
    risk,
    simulated,
    components_m,
    encounter_plane,
    pc_history,
    assumptions,
  } = details;

  const isRed = riskLevel === "RED";
  const isAmber = riskLevel === "AMBER";

  return (
    <div className="w-96 h-full bg-[#0E141C] border-l border-[#1E2833] flex flex-col font-mono text-xs text-[#C8D4E0] shadow-2xl z-30 overflow-hidden">
      {/* Header Bar */}
      <div className="p-3 border-b border-[#1E2833] bg-[#070A0F]/80 flex items-center justify-between">
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
            {riskLevel}
          </span>
          {isSimulated && (
            <span className="px-1 py-0.5 rounded bg-blue-950 text-blue-400 border border-blue-800/50 text-[9px] font-bold">
              SIM
            </span>
          )}
          <span className="font-bold text-[#C8D4E0] text-sm">{displayId}</span>
        </div>

        <button
          onClick={onClose}
          className="w-6 h-6 rounded bg-[#1E2833] hover:bg-[#283545] text-[#C8D4E0] flex items-center justify-center font-bold text-sm cursor-pointer transition-colors"
          title="Close details"
        >
          ✕
        </button>
      </div>

      {/* Details Scroll Area */}
      <div className="flex-1 overflow-y-auto p-3 space-y-4">
        {/* Objects Overview */}
        <div className="grid grid-cols-2 gap-2 p-2 bg-[#070A0F] border border-[#1E2833] rounded-lg">
          {/* Primary */}
          <div className="space-y-1">
            <div className="text-[10px] text-[#3DD68C] font-bold">PRIMARY OBJECT</div>
            <div className="font-bold truncate text-[#C8D4E0]">{primaryObj?.name}</div>
            <div className="text-[10px] text-[#6B7A8C]">NORAD: {primaryObj?.norad_id}</div>
            <div className="text-[10px] text-[#6B7A8C]">OPERATOR: {primaryObj?.operator || "—"}</div>
          </div>

          {/* Secondary */}
          <div className="space-y-1">
            <div className="text-[10px] text-[#E5484D] font-bold">SECONDARY DEBRIS</div>
            <div className="font-bold truncate text-[#C8D4E0]">{secondaryObj?.name}</div>
            <div className="text-[10px] text-[#6B7A8C]">NORAD: {secondaryObj?.norad_id}</div>
            <div className="text-[10px] text-[#6B7A8C]">TYPE: {secondaryObj?.object_type}</div>
          </div>
        </div>

        {/* Telemetry Summary Cards */}
        <div className="grid grid-cols-2 gap-2 text-center">
          <div className="p-2 bg-[#070A0F] border border-[#1E2833] rounded-lg">
            <div className="text-[9px] text-[#6B7A8C] uppercase font-bold">MISS DISTANCE</div>
            <div className="text-sm font-bold text-white">{missDist} km</div>
          </div>
          <div className="p-2 bg-[#070A0F] border border-[#1E2833] rounded-lg">
            <div className="text-[9px] text-[#6B7A8C] uppercase font-bold">PROBABILITY P<sub>c</sub></div>
            <div className="text-sm font-bold text-[#E5484D]">
              {collisionPc < 0.0001 ? collisionPc.toExponential(2) : collisionPc}
            </div>
          </div>
        </div>


        {/* Miss Distance Components (Radial, In-track, Cross-track) */}
        {components_m && (
          <div className="p-2.5 bg-[#070A0F] border border-[#1E2833] rounded-lg space-y-1.5">
            <div className="text-[10px] text-[#6B7A8C] font-bold uppercase tracking-wider">
              MISS VECTOR BREAKDOWN (METRES)
            </div>
            <div className="grid grid-cols-3 gap-2 text-center text-[10px]">
              <div className="bg-[#1E2833]/40 p-1 rounded">
                <div className="text-[#6B7A8C]">RADIAL</div>
                <div className="font-bold text-[#C8D4E0]">{components_m.radial}m</div>
              </div>
              <div className="bg-[#1E2833]/40 p-1 rounded">
                <div className="text-[#6B7A8C]">IN-TRACK</div>
                <div className="font-bold text-[#C8D4E0]">{components_m.in_track}m</div>
              </div>
              <div className="bg-[#1E2833]/40 p-1 rounded">
                <div className="text-[#6B7A8C]">CROSS-TRACK</div>
                <div className="font-bold text-[#C8D4E0]">{components_m.cross_track}m</div>
              </div>
            </div>
          </div>
        )}

        {/* Encounter Plane Projection (B-Plane Plot) */}
        <EncounterPlane data={encounter_plane} />

        {/* Pc History Chart */}
        <PcChart data={pc_history} />

        {/* Assumptions Footnote */}
        {assumptions && (
          <div className="p-2.5 bg-[#070A0F]/60 border border-[#1E2833] rounded-lg text-[10px] text-[#6B7A8C] space-y-1">
            <div className="font-bold text-[#C8D4E0] text-[9px] uppercase">COVARIANCE ASSUMPTIONS</div>
            <div>Source: <span className="text-[#C8D4E0]">{assumptions.covariance_source}</span></div>
            <div>HBR Source: <span className="text-[#C8D4E0]">{assumptions.hbr_source}</span></div>
            <div>Growth Exponent: <span className="text-[#C8D4E0]">{assumptions.growth_exponent}</span></div>
          </div>
        )}
      </div>
    </div>
  );
}
