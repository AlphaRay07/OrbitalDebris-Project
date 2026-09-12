import { useEffect, useState } from "react";
import { getStatus } from "./api";

export default function Status() {
    const [status, setStatus] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        const fetchStatus = () => {
            getStatus()
                .then((data) => {
                    setStatus(data);
                    setLoading(false);
                })
                .catch((err) => {
                    setError(err.message);
                    setLoading(false);
                });
        };

        fetchStatus();
        const interval = setInterval(fetchStatus, 3000);
        return () => clearInterval(interval);
    }, []);


    if (loading) {
        return <div className="p-3 bg-[#0E141C] text-[#6B7A8C] font-mono text-sm border-b border-[#1E2833]">Loading telemetry status...</div>;
    }

    if (error) {
        return <div className="p-3 bg-[#0E141C] text-[#E5484D] font-mono text-sm border-b border-[#1E2833]">Status Error: {error}</div>;
    }

    const { catalog_objects, median_tle_age_hours, counts, demo_mode } = status || {};

    return (
        <div className="w-full bg-[#0E141C] border-b border-[#1E2833] px-4 py-2 flex items-center justify-between text-xs font-mono text-[#C8D4E0]">
            <div className="flex items-center gap-6">
                <div className="flex items-center gap-2">
                    <span className="text-[#6B7A8C] font-semibold">CATALOG OBJECTS:</span>
                    <span className="text-[#C8D4E0] font-bold">{catalog_objects?.toLocaleString() ?? "—"}</span>
                </div>

                <div className="flex items-center gap-2">
                    <span className="text-[#6B7A8C] font-semibold">MEDIAN TLE AGE:</span>
                    <span className="text-[#C8D4E0] font-bold">{median_tle_age_hours?.toFixed(1) ?? "—"}h</span>
                </div>
            </div>

            <div className="flex items-center gap-3">
                <span className="px-2 py-0.5 rounded bg-red-950/80 text-[#E5484D] border border-red-800/50 font-bold">
                    RED: {counts?.red ?? 0}
                </span>
                <span className="px-2 py-0.5 rounded bg-amber-950/80 text-[#E8A33D] border border-amber-800/50 font-bold">
                    AMBER: {counts?.amber ?? 0}
                </span>
                <span className="px-2 py-0.5 rounded bg-emerald-950/80 text-[#3DD68C] border border-emerald-800/50 font-bold">
                    GREEN: {counts?.green ?? 0}
                </span>

                {demo_mode && (
                    <span className="ml-2 px-2 py-0.5 rounded bg-indigo-950 text-indigo-400 border border-indigo-700/50 text-[10px] font-bold uppercase tracking-wider">
                        DEMO MODE
                    </span>
                )}
            </div>
        </div>
    );
}


