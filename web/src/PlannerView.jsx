import { useEffect, useState } from "react";
import { createPlan, getPlan, runCascadeCheck } from "./api";

export default function PlannerView({ cdmId = "CDM-0001", onClose }) {
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedCandidateId, setSelectedCandidateId] = useState(null);

  useEffect(() => {
    if (!cdmId) return;
    let isMounted = true;
    let interval = null;

    setLoading(true);
    setError(null);
    setPlan(null);
    setSelectedCandidateId(null);

    const show = (data, selectRecommended) => {
      if (!isMounted) return;
      setPlan(data);
      if (data && data.recommended_id && selectRecommended) {
        setSelectedCandidateId(data.recommended_id);
      }
      setLoading(false);
    };

    const poll = () => {
      if (!isMounted) return;
      interval = setInterval(() => {
        getPlan(cdmId).then((data) => show(data, false)).catch(() => {});
      }, 3000);
    };

    // GET only reads a stored plan - the solver runs on POST. Without the
    // POST fallback this 404s for every conjunction that has never been
    // planned, which is all of them except the CDM-0001 fixture.
    getPlan(cdmId)
      .then((data) => {
        show(data, true);
        poll();
      })
      .catch(() =>
        createPlan(cdmId)
          .then((data) => {
            show(data, true);
            // Cascade re-screening runs in the background and rewrites the
            // stored plan, so poll for cascade_check leaving PENDING.
            runCascadeCheck(cdmId).catch(() => {});
            poll();
          })
          .catch((err) => {
            if (!isMounted) return;
            setError(err.message);
            setLoading(false);
          })
      );

    return () => {
      isMounted = false;
      if (interval) clearInterval(interval);
    };
  }, [cdmId]);

  if (loading) {
    return (
      <div className="w-full h-full bg-[#0E141C] p-6 text-[#6B7A8C] font-mono text-xs flex flex-col justify-center items-center">
        <div className="animate-spin w-8 h-8 border-2 border-emerald-500 border-t-transparent rounded-full mb-3" />
        Generating avoidance maneuver options...
      </div>
    );
  }

  if (error || !plan) {
    return (
      <div className="w-full h-full bg-[#0E141C] p-6 text-[#E5484D] font-mono text-xs">
        Error loading maneuver plan: {error || "No plan data"}
      </div>
    );
  }

  const {
    cdm_id,
    target_pc,
    recommended_id,
    rejected_ids = [],
    rejection_reason,
    candidates = [],
    propellant_estimate_g,
    notes,
  } = plan;

  const selectedCandidate =
    candidates.find((c) => c.id === selectedCandidateId) ||
    candidates.find((c) => c.id === recommended_id) ||
    candidates[0];

  const rejectedDetail = candidates.find(
    (c) => rejected_ids.includes(c.id) && c.cascade_detail
  );

  // Pareto Chart Math Calculations
  const chartWidth = 560;
  const chartHeight = 220;
  const padding = 45;

  const dvValues = candidates.map((c) => c.delta_v_mms);
  const minDv = Math.min(...dvValues, 0.5);
  const maxDv = Math.max(...dvValues, 25);

  const pcValues = candidates.map((c) => c.new_pc);
  const minPc = Math.min(...pcValues, 1e-8);
  const maxPc = Math.max(...pcValues, 0.0005);

  const getX = (dv) => {
    return padding + ((dv - minDv) / (maxDv - minDv)) * (chartWidth - padding * 2);
  };

  const getY = (pc) => {
    const minLog = Math.log10(minPc);
    const maxLog = Math.log10(maxPc);
    const valLog = Math.log10(Math.max(pc, 1e-9));
    const ratio = (valLog - minLog) / (maxLog - minLog);
    return chartHeight - padding - ratio * (chartHeight - padding * 2);
  };

  const targetPcY = getY(target_pc);

  return (
    <div className="w-full h-full bg-[#0E141C] border-l border-[#1E2833] flex flex-col font-mono text-xs text-[#C8D4E0] shadow-2xl z-30 overflow-hidden">
      {/* Top Header Bar */}
      <div className="p-3 border-b border-[#1E2833] bg-[#070A0F]/80 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="px-2 py-0.5 rounded bg-emerald-950 text-[#3DD68C] border border-emerald-800/50 font-bold text-[11px]">
            OPTIMAL PLANNER
          </span>
          <span className="font-bold text-white text-sm">AVOIDANCE MANEUVER ({cdm_id})</span>
        </div>

        {onClose && (
          <button
            onClick={onClose}
            className="w-6 h-6 rounded bg-[#1E2833] hover:bg-[#283545] text-[#C8D4E0] flex items-center justify-center font-bold text-sm cursor-pointer"
          >
            ✕
          </button>
        )}
      </div>

      {/* Main Content Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* PROMINENT CASCADE REJECTION BANNER (The Demo's Key Moment) */}
        {rejection_reason && (
          <div className="p-3 bg-red-950/80 border border-red-800/80 rounded-lg text-red-200 flex flex-col gap-1 shadow-lg">
            <div className="flex items-center justify-between text-xs font-bold text-[#E5484D]">
              <span className="flex items-center gap-1.5 uppercase">
                <span className="w-2.5 h-2.5 rounded-full bg-[#E5484D] animate-ping" />
                ⚠️ CASCADE CHECK FAILURE
              </span>
              <span className="px-1.5 py-0.5 rounded bg-red-900 border border-red-700 text-[10px] text-white">
                {rejected_ids.join(", ") || "CANDIDATE"} REJECTED
              </span>
            </div>
            <div className="text-xs font-semibold text-white mt-1">
              "{rejection_reason}"
            </div>
            {rejectedDetail && (
              <div className="text-[10px] text-red-300/80">
                Note: Candidate {rejectedDetail.id} meets target P<sub>c</sub>, but the
                resulting orbital shift causes a secondary conjunction with{" "}
                {rejectedDetail.cascade_detail.new_conjunction_with} at{" "}
                {rejectedDetail.cascade_detail.miss_distance_km} km on{" "}
                {rejectedDetail.cascade_detail.tca}.
              </div>
            )}
          </div>
        )}

        {/* Pareto Scatter Chart (Delta-V vs New Pc) */}
        <div className="p-3 bg-[#070A0F] border border-[#1E2833] rounded-lg flex flex-col gap-2">
          <div className="flex items-center justify-between text-[10px] text-[#6B7A8C] font-bold uppercase tracking-wider">
            <span>PARETO TRADE-OFF: ∆V (mm/s) VS RESULTING P<sub>c</sub></span>
            <span className="text-[#3DD68C]">TARGET THRESHOLD: {target_pc}</span>
          </div>

          {/* Color Legend & Naming Convention Key */}
          <div className="flex flex-wrap items-center justify-between gap-2 p-2 bg-[#0E141C] border border-[#1E2833]/70 rounded text-[10px]">
            <div className="text-gray-400">
              <span className="text-white font-bold">MNV</span> = Maneuver Option
            </div>
            <div className="flex items-center gap-3 flex-wrap">
              <div className="flex items-center gap-1">
                <span className="w-2.5 h-2.5 rounded-full bg-[#3DD68C] inline-block border border-white" />
                <span className="text-[#3DD68C] font-bold">Optimal / Recommended</span>
              </div>
              <div className="flex items-center gap-1">
                <span className="w-2.5 h-2.5 rounded-full bg-[#E5484D] inline-block" />
                <span className="text-[#E5484D]">Rejected (Cascade Fail)</span>
              </div>
              <div className="flex items-center gap-1">
                <span className="w-2.5 h-2.5 rounded-full bg-[#E8A33D] inline-block" />
                <span className="text-[#E8A33D]">Feasible</span>
              </div>
              <div className="flex items-center gap-1">
                <span className="w-2.5 h-2.5 rounded-full bg-[#6B7A8C] inline-block" />
                <span className="text-[#6B7A8C]">Infeasible (High Pc)</span>
              </div>
            </div>
          </div>

          <div className="relative w-full overflow-x-auto">
            <svg viewBox={`0 0 ${chartWidth} ${chartHeight}`} className="w-full h-auto">
              {/* Target threshold line */}
              <line
                x1={padding}
                y1={targetPcY}
                x2={chartWidth - padding}
                y2={targetPcY}
                stroke="#3DD68C"
                strokeDasharray="4 4"
                strokeWidth="1.5"
              />
              <text
                x={chartWidth - padding - 65}
                y={targetPcY - 5}
                fill="#3DD68C"
                fontSize="9"
                fontWeight="bold"
              >
                TARGET P<sub>c</sub> {target_pc}
              </text>

              {/* Axes */}
              <line
                x1={padding}
                y1={chartHeight - padding}
                x2={chartWidth - padding}
                y2={chartHeight - padding}
                stroke="#1E2833"
                strokeWidth="1.5"
              />
              <line
                x1={padding}
                y1={padding}
                x2={padding}
                y2={chartHeight - padding}
                stroke="#1E2833"
                strokeWidth="1.5"
              />

              {/* Axis Labels */}
              <text x={chartWidth / 2} y={chartHeight - 8} fill="#6B7A8C" fontSize="9" textAnchor="middle">
                BURN DELTA-V ∆V (mm/s)
              </text>
              <text
                x={12}
                y={chartHeight / 2}
                fill="#6B7A8C"
                fontSize="9"
                textAnchor="middle"
                transform={`rotate(-90 12 ${chartHeight / 2})`}
              >
                NEW P<sub>c</sub> (LOG SCALE)
              </text>

              {/* Scatter Points */}
              {candidates.map((c) => {
                const cx = getX(c.delta_v_mms);
                const cy = getY(c.new_pc);
                const isRecommended = c.id === recommended_id;
                const isRejected = rejected_ids.includes(c.id);
                const isSelected = c.id === selectedCandidate?.id;

                let fill = "#6B7A8C";
                if (isRecommended) fill = "#3DD68C";
                else if (isRejected) fill = "#E5484D";
                else if (c.feasible) fill = "#E8A33D";

                return (
                  <g
                    key={c.id}
                    onClick={() => setSelectedCandidateId(c.id)}
                    className="cursor-pointer"
                  >
                    {/* Ring selection highlight */}
                    {isSelected && (
                      <circle
                        cx={cx}
                        cy={cy}
                        r={isRecommended ? "14" : "10"}
                        fill="none"
                        stroke="#FFFFFF"
                        strokeWidth="2"
                      />
                    )}

                    {/* Candidate Node Circle */}
                    <circle
                      cx={cx}
                      cy={cy}
                      r={isRecommended ? "9" : "6"}
                      fill={fill}
                      stroke="#FFFFFF"
                      strokeWidth={isRecommended ? "2" : "1"}
                    />

                    {/* Candidate Label (Rendered cleanly for recommended/selected/rejected/key candidates to prevent overlap) */}
                    {(isRecommended || isRejected || isSelected || ["MNV-001", "MNV-012", "MNV-024", "MNV-048", "MNV-096"].includes(c.id)) && (
                      <text
                        x={cx}
                        y={cy - 12}
                        fill={isRejected ? "#E5484D" : isRecommended ? "#3DD68C" : "#C8D4E0"}
                        fontSize="9"
                        fontWeight={isRecommended ? "bold" : "normal"}
                        textAnchor="middle"
                        style={{ textDecoration: isRejected ? "line-through" : "none" }}
                      >
                        {c.id}
                      </text>
                    )}
                  </g>
                );
              })}

            </svg>
          </div>
        </div>

        {/* Selected Candidate Telemetry Card */}
        {selectedCandidate && (
          <div className="p-3 bg-[#070A0F] border border-[#1E2833] rounded-lg space-y-3">
            <div className="flex items-center justify-between border-b border-[#1E2833] pb-2">
              <div className="flex items-center gap-2">
                <span className="font-bold text-white text-sm">{selectedCandidate.id}</span>
                {selectedCandidate.id === recommended_id && (
                  <span className="px-1.5 py-0.5 rounded bg-emerald-950 text-[#3DD68C] border border-emerald-800/50 text-[10px] font-bold">
                    RECOMMENDED
                  </span>
                )}
                {rejected_ids.includes(selectedCandidate.id) && (
                  <span className="px-1.5 py-0.5 rounded bg-red-950 text-[#E5484D] border border-red-800/50 text-[10px] font-bold">
                    CASCADE FAIL
                  </span>
                )}
              </div>
              <span className="text-[10px] text-[#6B7A8C]">
                FEASIBLE: <b className={selectedCandidate.feasible ? "text-emerald-400" : "text-red-400"}>{selectedCandidate.feasible ? "YES" : "NO"}</b>
              </span>
            </div>

            {/* Metric Grid */}
            <div className="grid grid-cols-3 gap-2 text-center text-[11px]">
              <div className="p-2 bg-[#1E2833]/40 rounded border border-[#1E2833]">
                <div className="text-[9px] text-[#6B7A8C]">DELTA-V ∆V</div>
                <div className="font-bold text-white text-xs">{selectedCandidate.delta_v_mms} mm/s</div>
              </div>
              <div className="p-2 bg-[#1E2833]/40 rounded border border-[#1E2833]">
                <div className="text-[9px] text-[#6B7A8C]">NEW MISS DIST</div>
                <div className="font-bold text-white text-xs">{selectedCandidate.new_miss_distance_km} km</div>
              </div>
              <div className="p-2 bg-[#1E2833]/40 rounded border border-[#1E2833]">
                <div className="text-[9px] text-[#6B7A8C]">NEW P<sub>c</sub></div>
                <div className="font-bold text-[#3DD68C] text-xs">
                  {selectedCandidate.new_pc < 0.0001
                    ? selectedCandidate.new_pc.toExponential(2)
                    : selectedCandidate.new_pc}
                </div>
              </div>
            </div>

            {/* Additional Telemetry Details */}
            <div className="grid grid-cols-2 gap-2 text-[10px] text-[#6B7A8C] pt-1">
              <div>
                DIRECTION: <span className="text-[#C8D4E0] font-bold">{selectedCandidate.direction}</span>
              </div>
              <div>
                LEAD ORBITS: <span className="text-[#C8D4E0] font-bold">{selectedCandidate.lead_orbits} orbits</span>
              </div>
              <div className="col-span-2 truncate">
                BURN EPOCH: <span className="text-[#C8D4E0] font-bold">{new Date(selectedCandidate.burn_epoch).toUTCString()}</span>
              </div>
            </div>

            {/* Propellant Cost & Notes */}
            <div className="pt-2 border-t border-[#1E2833] flex items-center justify-between text-[10px]">
              <span className="text-[#6B7A8C]">ESTIMATED PROPELLANT COST:</span>
              <span className="text-[#E8A33D] font-bold text-xs">{propellant_estimate_g} g</span>
            </div>
          </div>
        )}

        {/* Candidate Maneuvers Comparison Table */}
        <div className="p-3 bg-[#070A0F] border border-[#1E2833] rounded-lg space-y-2">
          <div className="text-[10px] text-[#6B7A8C] font-bold uppercase tracking-wider">
            ALL CANDIDATE MANEUVERS ({candidates.length})
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-[11px] font-mono border-collapse">
              <thead>
                <tr className="border-b border-[#1E2833] text-[#6B7A8C]">
                  <th className="py-1 px-1.5">ID</th>
                  <th className="py-1 px-1.5">∆V (mm/s)</th>
                  <th className="py-1 px-1.5">NEW P<sub>c</sub></th>
                  <th className="py-1 px-1.5">MISS (km)</th>
                  <th className="py-1 px-1.5">CASCADE</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1E2833]/40">
                {candidates.map((c) => {
                  const isRec = c.id === recommended_id;
                  const isRej = rejected_ids.includes(c.id);
                  const isSel = c.id === selectedCandidate?.id;

                  return (
                    <tr
                      key={c.id}
                      onClick={() => setSelectedCandidateId(c.id)}
                      className={`cursor-pointer transition-colors ${
                        isSel ? "bg-[#1E2833] text-white font-bold" : "hover:bg-[#1E2833]/40 text-[#C8D4E0]"
                      }`}
                    >
                      <td className="py-1.5 px-1.5 flex items-center gap-1">
                        <span style={{ textDecoration: isRej ? "line-through" : "none" }}>{c.id}</span>
                        {isRec && <span className="text-[#3DD68C] text-[9px]">★</span>}
                      </td>
                      <td className="py-1.5 px-1.5">{c.delta_v_mms}</td>
                      <td className="py-1.5 px-1.5">
                        {c.new_pc < 0.0001 ? c.new_pc.toExponential(2) : c.new_pc}
                      </td>
                      <td className="py-1.5 px-1.5">{c.new_miss_distance_km}</td>
                      <td className="py-1.5 px-1.5 font-bold">
                        <span className={c.cascade_check === "FAIL" ? "text-red-400" : "text-emerald-400"}>
                          {c.cascade_check}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
