export default function Slide1Title() {
  return (
    <div className="relative w-screen h-screen overflow-hidden" style={{ background: "#0C0F1A", fontFamily: "Inter, system-ui, sans-serif" }}>

      {/* Subtle grid texture */}
      <div className="absolute inset-0" style={{
        backgroundImage: "linear-gradient(rgba(79,127,255,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(79,127,255,0.05) 1px, transparent 1px)",
        backgroundSize: "6vw 6vw"
      }} />

      {/* Top bar */}
      <div className="absolute top-0 left-0 right-0 flex items-center justify-between" style={{ padding: "3.5vh 6vw" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.8vw" }}>
          <div style={{
            width: "2vw", height: "2vw", borderRadius: "0.35vw",
            background: "linear-gradient(135deg, #4F7FFF, #7C6BF0)",
            display: "flex", alignItems: "center", justifyContent: "center"
          }}>
            <svg width="55%" height="55%" viewBox="0 0 16 16" fill="none">
              <path d="M8 2L14 12H2L8 2Z" fill="white" opacity="0.9"/>
            </svg>
          </div>
          <span style={{ color: "#8892B0", fontSize: "1.1vw", fontWeight: 400, letterSpacing: "0.04em" }}>123inkt</span>
        </div>
        <span style={{ color: "#8892B0", fontSize: "1vw", fontWeight: 400, letterSpacing: "0.03em" }}>Vertrouwelijk — Directie</span>
      </div>

      {/* Main content */}
      <div className="absolute inset-0 flex flex-col justify-center" style={{ padding: "0 6vw" }}>
        <div style={{ maxWidth: "62vw" }}>

          <div style={{ marginBottom: "2.5vh" }}>
            <span style={{
              display: "inline-block",
              background: "rgba(79,127,255,0.1)",
              border: "1px solid rgba(79,127,255,0.25)",
              borderRadius: "0.3vw",
              padding: "0.5vh 1.2vw",
              color: "#4F7FFF",
              fontSize: "1.1vw",
              fontWeight: 700,
              letterSpacing: "0.1em",
              textTransform: "uppercase"
            }}>Budgetvoorstel — AI Pricing Pilot 2026</span>
          </div>

          <h1 style={{
            fontSize: "5.8vw",
            fontWeight: 700,
            lineHeight: 1.08,
            letterSpacing: "-0.02em",
            color: "#F0F4FF",
            marginBottom: "3.5vh",
            textWrap: "balance"
          }}>
            Kostenraming
            <span style={{ display: "block", color: "#4F7FFF" }}>AI Pricing Pilot</span>
          </h1>

          <p style={{
            fontSize: "2vw",
            color: "#8892B0",
            fontWeight: 400,
            lineHeight: 1.5,
            marginBottom: "5vh"
          }}>Aanvraag pilotbudget voor productievalidatie van de AI-pricing engine — 500 SKU's, 12 weken.</p>

          <div style={{ display: "flex", gap: "4vw", alignItems: "flex-start" }}>
            <div>
              <div style={{ fontSize: "2.6vw", fontWeight: 700, color: "#4F7FFF", lineHeight: 1 }}>€87.500</div>
              <div style={{ fontSize: "1vw", color: "#8892B0", marginTop: "0.5vh" }}>Eenmalige investering</div>
            </div>
            <div style={{ width: "1px", background: "rgba(79,127,255,0.2)", alignSelf: "stretch" }} />
            <div>
              <div style={{ fontSize: "2.6vw", fontWeight: 700, color: "#7C6BF0", lineHeight: 1 }}>€6.200/mnd</div>
              <div style={{ fontSize: "1vw", color: "#8892B0", marginTop: "0.5vh" }}>Doorlopende kosten</div>
            </div>
            <div style={{ width: "1px", background: "rgba(79,127,255,0.2)", alignSelf: "stretch" }} />
            <div>
              <div style={{ fontSize: "2.6vw", fontWeight: 700, color: "#4F7FFF", lineHeight: 1 }}>12 weken</div>
              <div style={{ fontSize: "1vw", color: "#8892B0", marginTop: "0.5vh" }}>Pilotduur</div>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom accent line */}
      <div className="absolute bottom-0 left-0 right-0" style={{ height: "0.4vh", background: "linear-gradient(90deg, transparent, #4F7FFF, #7C6BF0, transparent)" }} />

      {/* Footer */}
      <div className="absolute bottom-0 left-0 right-0 flex items-end justify-between" style={{ padding: "0 6vw 2.5vh" }}>
        <span style={{ color: "#8892B0", fontSize: "1vw", opacity: 0.6 }}>Juni 2026</span>
      </div>
    </div>
  );
}
