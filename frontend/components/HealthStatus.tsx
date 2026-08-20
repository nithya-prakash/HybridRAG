"use client";

import { useEffect, useState } from "react";
import { fetchHealth, type HealthResponse } from "@/lib/api";

type State =
  | { status: "loading" }
  | { status: "success"; data: HealthResponse }
  | { status: "error"; message: string };

export function HealthStatus() {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;

    fetchHealth()
      .then((data) => {
        if (!cancelled) setState({ status: "success", data });
      })
      .catch((err: Error) => {
        if (!cancelled) setState({ status: "error", message: err.message });
      });

    return () => {
      cancelled = true;
    };
  }, []);

  if (state.status === "loading") {
    return <p className="text-slate-400">Checking backend health…</p>;
  }

  if (state.status === "error") {
    return (
      <div className="rounded-lg border border-red-800 bg-red-950/40 p-4 text-red-300">
        <p className="font-medium">Backend unreachable</p>
        <p className="text-sm text-red-400">{state.message}</p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-emerald-800 bg-emerald-950/40 p-4 text-emerald-300">
      <p className="font-medium">Backend is healthy ✓</p>
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm text-emerald-400">
        <dt className="text-emerald-500">status</dt>
        <dd>{state.data.status}</dd>
        <dt className="text-emerald-500">app_name</dt>
        <dd>{state.data.app_name}</dd>
        <dt className="text-emerald-500">environment</dt>
        <dd>{state.data.environment}</dd>
        <dt className="text-emerald-500">version</dt>
        <dd>{state.data.version}</dd>
      </dl>
    </div>
  );
}
