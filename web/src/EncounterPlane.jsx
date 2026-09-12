export default function EncounterPlane({ data }) {
  if (!data) {
    return (
      <div className="text-[#6B7A8C] text-xs font-mono p-4">
        No encounter plane data available.
      </div>
    );
  }

  const {
    miss_x_m = 0,
    miss_y_m = 0,
    sigma_major_m = 300,
    sigma_minor_m = 100,
    rotation_deg = 0,
    hbr_m = 5.5,
  } = data;

  const missDistance = Math.round(
    Math.sqrt(miss_x_m * miss_x_m + miss_y_m * miss_y_m)
  );

  // SVG viewBox setup (-500 to 500 space)
  const viewBoxSize = 1000;
  const half = viewBoxSize / 2;

  return (
    <div className="flex flex-col gap-2 font-mono text-xs">
      <div className="text-[10px] text-[#6B7A8C] font-bold uppercase tracking-wider">
        ENCOUNTER PLANE (B-PLANE PROJECTION)
      </div>

      <div className="relative w-full aspect-square bg-[#070A0F] border border-[#1E2833] rounded-lg p-2 flex items-center justify-center overflow-hidden">
        <svg
          viewBox={`-${half} -${half} ${viewBoxSize} ${viewBoxSize}`}
          className="w-full h-full"
        >
          {/* Grid Lines */}
          <line
            x1={-half}
            y1={0}
            x2={half}
            y2={0}
            stroke="#1E2833"
            strokeDasharray="4 4"
            strokeWidth="1.5"
          />
          <line
            x1={0}
            y1={-half}
            x2={0}
            y2={half}
            stroke="#1E2833"
            strokeDasharray="4 4"
            strokeWidth="1.5"
          />

          {/* Concentric Reference Circles */}
          <circle cx="0" cy="0" r="200" fill="none" stroke="#1E2833" strokeWidth="1" />
          <circle cx="0" cy="0" r="400" fill="none" stroke="#1E2833" strokeWidth="1" />

          {/* 3-Sigma Error Ellipse (Fainter) */}
          <g transform={`rotate(${rotation_deg})`}>
            <ellipse
              cx="0"
              cy="0"
              rx={sigma_major_m * 3}
              ry={sigma_minor_m * 3}
              fill="rgba(229, 72, 77, 0.08)"
              stroke="#E5484D"
              strokeWidth="1"
              strokeDasharray="6 4"
              opacity="0.5"
            />
            {/* 1-Sigma Error Ellipse */}
            <ellipse
              cx="0"
              cy="0"
              rx={sigma_major_m}
              ry={sigma_minor_m}
              fill="rgba(229, 72, 77, 0.25)"
              stroke="#E5484D"
              strokeWidth="2"
            />
          </g>

          {/* Combined Hard-Body Radius (HBR) at Origin */}
          <circle
            cx="0"
            cy="0"
            r={Math.max(hbr_m * 4, 12)}
            fill="#3DD68C"
            stroke="#FFFFFF"
            strokeWidth="2"
          />
          <text
            x="0"
            y="28"
            fill="#3DD68C"
            fontSize="18"
            fontWeight="bold"
            textAnchor="middle"
          >
            PRIMARY
          </text>

          {/* Miss Vector Line from Origin to (miss_x_m, miss_y_m) */}
          <line
            x1="0"
            y1="0"
            x2={miss_x_m}
            y2={-miss_y_m}
            stroke="#E8A33D"
            strokeWidth="2.5"
            strokeDasharray="5 3"
          />

          {/* Secondary Object Point at Miss Location */}
          <circle
            cx={miss_x_m}
            cy={-miss_y_m}
            r="10"
            fill="#E5484D"
            stroke="#FFFFFF"
            strokeWidth="2"
          />

          {/* Distance Text Label */}
          <text
            x={miss_x_m + 15}
            y={-miss_y_m - 10}
            fill="#E8A33D"
            fontSize="20"
            fontWeight="bold"
          >
            MISS: {missDistance}m
          </text>
        </svg>

        {/* Legend Overlay */}
        <div className="absolute bottom-2 right-2 bg-[#0E141C]/90 p-1.5 rounded border border-[#1E2833] text-[9px] text-[#6B7A8C] flex flex-col gap-1">
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-[#3DD68C]" />
            <span>Primary (ISS)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-[#E5484D]" />
            <span>Secondary (Debris)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-1.5 bg-red-900/60 border border-red-500 rounded-sm" />
            <span>1σ / 3σ Covariance</span>
          </div>
        </div>
      </div>
    </div>
  );
}
