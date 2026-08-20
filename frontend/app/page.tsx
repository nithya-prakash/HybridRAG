import { HealthStatus } from "@/components/HealthStatus";

export default function HomePage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Welcome</h1>
        <p className="mt-1 text-slate-400">
          Ask questions over your own documents, with answers grounded in citations
          from your uploads.
        </p>
      </div>
      <HealthStatus />
    </div>
  );
}
