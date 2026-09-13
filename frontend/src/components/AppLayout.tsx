import { Outlet } from "react-router-dom";
import { Navbar } from "@/components/Navbar";
import { GradientWave } from "@/components/ui/gradient-wave";

export function AppLayout() {
  return (
    <div className="min-h-screen bg-[#f4f9fd] text-slate-900 flex flex-col relative overflow-x-hidden selection:bg-sky-600 selection:text-white">
      {/* Light Blue WebGL Dynamic Gradient Wave Background */}
      <div className="fixed inset-0 z-0 pointer-events-none opacity-65">
        <GradientWave
          colors={["#7dd3fc", "#ffffff", "#bae6fd", "#ffffff", "#7dd3fc", "#ffffff"]}
          noiseSpeed={0.00001}
          noiseFrequency={[0.0001, 0.0008]}
          shadowPower={5}
          deform={{ incline: 0.4, noiseAmp: 200, noiseFlow: 3.5 }}
        />
        {/* Subtle translucent glass overlay for crisp text readability */}
        <div className="absolute inset-0 bg-white/50 backdrop-blur-[1px]" />
      </div>

      {/* Transparent Circular Floating Navigation Bar */}
      <Navbar />

      {/* Main Content Area */}
      <main id="main" className="relative z-10 flex-1 pt-28 pb-20 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto w-full">
        <Outlet />
      </main>

      {/* Institutional Footer (Light Blue Theme) */}
      <footer className="relative z-10 border-t border-slate-200/80 bg-white/80 backdrop-blur-md py-6 text-center text-sm text-slate-600">
        <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-emerald-600"></span>
            <span className="font-bold text-slate-900">Shram Drishti &middot; National Career Service</span>
            <span>&mdash; Labour Code Inspection and Compliance System</span>
          </div>
          <div className="flex items-center gap-6 text-slate-600 font-medium">
            <span>Ministry of Labour &amp; Employment</span>
            <span>Government of India</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
