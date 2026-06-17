export default function Slide1Title() {
  return (
    <div className="relative w-screen h-screen overflow-hidden" style={{ background: "#0C0F1A", fontFamily: "Inter, system-ui, sans-serif" }}>

      {/* Grid texture */}
      <div className="absolute inset-0" style={{
        backgroundImage: "linear-gradient(rgba(79,127,255,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(79,127,255,0.06) 1px, transparent 1px)",
        backgroundSize: "6vw 6vw"
      }} />

      {/* Glow orbs */}
      <div className="absolute" style={{
        width: "55vw", height: "55vw", borderRadius: "50%",
        background: "radial-gradient(circle, rgba(79,127,255,0.18) 0%, transparent 70%)",
        top: "-15vw", right: "-10vw"
      }} />
      <div className="absolute" style={{
        width: "35vw", height: "35vw", borderRadius: "50%",
        background: "radial-gradient(circle, rgba(124,107,240,0.15) 0%, transparent 70%)",
        bottom: "-10vw", left: "-5vw"
      }} />

      {/* Top bar */}
      <div className="absolute top-0 left-0 right-0 flex items-center justify-between" style={{ padding: "3vh 5vw" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.8vw" }}>
          <div style={{
            width: "2.2vw", height: "2.2vw", borderRadius: "0.4vw",
            background: "linear-gradient(135deg, #4F7FFF, #7C6BF0)",
            display: "flex", alignItems: "center", justifyContent: "center"
          }}>
            <svg width="60%" height="60%" viewBox="0 0 16 16" fill="none">
              <path d="M8 2L14 12H2L8 2Z" fill="white" opacity="0.9"/>
            </svg>
          </div>
          <span style={{ color: "#8892B0", fontSize: "1.1vw", fontWeight: 500, letterSpacing: "0.05em" }}>123inkt</span>
        </div>
        <span style={{ color: "#8892B0", fontSize: "1vw", fontWeight: 400 }}>Vertrouwelijk — Management</span>
      </div>

      {/* Main content */}
      <div className="absolute inset-0 flex flex-col justify-center" style={{ padding: "0 8vw" }}>
        <div style={{ maxWidth: "65vw" }}>
          <div style={{
            display: "inline-block",
            background: "rgba(79,127,255,0.12)",
            border: "1px solid rgba(79,127,255,0.3)",
            borderRadius: "2vw",
            padding: "0.5vh 1.4vw",
            marginBottom: "2.5vh"
          }}>
            <span style={{ color: "#4F7FFF", fontSize: "1.1vw", fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase" }}>Strategische Presentatie 2026</span>
          </div>

          <h1 style={{
            fontSize: "6.5vw",
            fontWeight: 800,
            lineHeight: 1.05,
            letterSpacing: "-0.02em",
            color: "#F0F4FF",
            marginBottom: "3vh",
            textWrap: "balance"
          }}>
            AI Pricing<br />
            <span style={{ background: "linear-gradient(90deg, #4F7FFF, #7C6BF0)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
              Decision Engine
            </span>
          </h1>

          <p style={{
            fontSize: "1.8vw",
            color: "#8892B0",
            fontWeight: 400,
            lineHeight: 1.55,
            maxWidth: "46vw",
            marginBottom: "5vh"
          }}>
            Geautomatiseerde prijsoptimalisatie voor 26.000+ SKU's — hogere marges, minder handwerk, volledige controle.
          </p>

          <div style={{ display: "flex", gap: "3vw" }}>
            <div>
              <div style={{ fontSize: "3vw", fontWeight: 800, color: "#4F7FFF", lineHeight: 1 }}>+4.2%</div>
              <div style={{ fontSize: "1vw", color: "#8892B0", marginTop: "0.4vh", fontWeight: 500 }}>Brutomarge uplift</div>
            </div>
            <div style={{ width: "1px", background: "rgba(79,127,255,0.2)" }} />
            <div>
              <div style={{ fontSize: "3vw", fontWeight: 800, color: "#7C6BF0", lineHeight: 1 }}>8</div>
              <div style={{ fontSize: "1vw", color: "#8892B0", marginTop: "0.4vh", fontWeight: 500 }}>Prijsstrategieën</div>
            </div>
            <div style={{ width: "1px", background: "rgba(79,127,255,0.2)" }} />
            <div>
              <div style={{ fontSize: "3vw", fontWeight: 800, color: "#4F7FFF", lineHeight: 1 }}>15</div>
              <div style={{ fontSize: "1vw", color: "#8892B0", marginTop: "0.4vh", fontWeight: 500 }}>Dashboard modules</div>
            </div>
          </div>
        </div>
      </div>

      {/* Right side decorative panel */}
      <div className="absolute right-0 top-0 bottom-0 flex items-center justify-center" style={{ width: "28vw" }}>
        <div style={{
          width: "20vw", height: "20vw",
          border: "1px solid rgba(79,127,255,0.2)",
          borderRadius: "50%",
          position: "relative",
          display: "flex", alignItems: "center", justifyContent: "center"
        }}>
          <div style={{
            width: "14vw", height: "14vw",
            border: "1px solid rgba(124,107,240,0.25)",
            borderRadius: "50%",
            position: "absolute",
            display: "flex", alignItems: "center", justifyContent: "center"
          }}>
            <div style={{
              width: "8vw", height: "8vw",
              background: "linear-gradient(135deg, rgba(79,127,255,0.2), rgba(124,107,240,0.2))",
              borderRadius: "50%",
              border: "1px solid rgba(79,127,255,0.4)",
              display: "flex", alignItems: "center", justifyContent: "center"
            }}>
              <svg width="3vw" height="3vw" viewBox="0 0 32 32" fill="none">
                <path d="M16 4L28 28H4L16 4Z" fill="#4F7FFF" opacity="0.9"/>
                <path d="M16 10L24 26H8L16 10Z" fill="#7C6BF0" opacity="0.7"/>
              </svg>
            </div>
          </div>
          {/* Orbit dots */}
          <div style={{ position: "absolute", top: "0.5vw", left: "50%", transform: "translateX(-50%)", width: "0.6vw", height: "0.6vw", borderRadius: "50%", background: "#4F7FFF" }} />
          <div style={{ position: "absolute", bottom: "0.5vw", left: "50%", transform: "translateX(-50%)", width: "0.6vw", height: "0.6vw", borderRadius: "50%", background: "#7C6BF0" }} />
          <div style={{ position: "absolute", left: "0.5vw", top: "50%", transform: "translateY(-50%)", width: "0.6vw", height: "0.6vw", borderRadius: "50%", background: "#4F7FFF", opacity: 0.5 }} />
          <div style={{ position: "absolute", right: "0.5vw", top: "50%", transform: "translateY(-50%)", width: "0.6vw", height: "0.6vw", borderRadius: "50%", background: "#7C6BF0", opacity: 0.5 }} />
        </div>
      </div>

      {/* Bottom line */}
      <div className="absolute bottom-0 left-0 right-0" style={{ height: "0.4vh", background: "linear-gradient(90deg, transparent, #4F7FFF, #7C6BF0, transparent)" }} />
    </div>
  );
}
