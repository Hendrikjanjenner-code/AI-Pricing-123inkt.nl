export default function Slide01Introductie() {
  return (
    <div className="relative w-screen h-screen overflow-hidden" style={{ background: "#0C0F1A", fontFamily: "Inter, system-ui, sans-serif" }}>

      {/* Grid */}
      <div className="absolute inset-0" style={{ backgroundImage: "linear-gradient(rgba(79,127,255,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(79,127,255,0.06) 1px, transparent 1px)", backgroundSize: "6vw 6vw" }} />

      {/* Glow orbs */}
      <div className="absolute" style={{ width: "55vw", height: "55vw", borderRadius: "50%", background: "radial-gradient(circle, rgba(79,127,255,0.16) 0%, transparent 70%)", top: "-18vw", right: "-12vw" }} />
      <div className="absolute" style={{ width: "30vw", height: "30vw", borderRadius: "50%", background: "radial-gradient(circle, rgba(124,107,240,0.12) 0%, transparent 70%)", bottom: "-8vw", left: "-5vw" }} />

      {/* Top bar */}
      <div className="absolute top-0 left-0 right-0 flex items-center justify-between" style={{ padding: "2.5vh 5vw" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.8vw" }}>
          <div style={{ width: "2.2vw", height: "2.2vw", borderRadius: "0.4vw", background: "linear-gradient(135deg, #4F7FFF, #7C6BF0)", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <svg width="60%" height="60%" viewBox="0 0 16 16" fill="none"><path d="M8 2L14 12H2L8 2Z" fill="white" opacity="0.9"/></svg>
          </div>
          <span style={{ color: "#8892B0", fontSize: "1.1vw", fontWeight: 500 }}>123inkt</span>
        </div>
        <span style={{ color: "#8892B0", fontSize: "1vw" }}>Kick-off &amp; Brainstorm Meeting</span>
      </div>

      {/* MERGER BANNER — prominente boodschap */}
      <div className="absolute" style={{ top: "11vh", left: "5vw", right: "5vw" }}>
        <div style={{ background: "linear-gradient(90deg, rgba(79,127,255,0.18), rgba(124,107,240,0.18))", border: "1px solid rgba(79,127,255,0.45)", borderRadius: "0.8vw", padding: "1.4vh 2vw", display: "flex", alignItems: "center", gap: "1.5vw" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.8vw", flexShrink: 0 }}>
            <div style={{ background: "rgba(79,127,255,0.2)", border: "1px solid #4F7FFF", borderRadius: "0.5vw", padding: "0.5vh 1vw" }}>
              <span style={{ fontSize: "0.85vw", fontWeight: 700, color: "#4F7FFF", letterSpacing: "0.05em" }}>AI PRICING</span>
            </div>
            <span style={{ fontSize: "1.6vw", color: "#8892B0", fontWeight: 300 }}>+</span>
            <div style={{ background: "rgba(124,107,240,0.2)", border: "1px solid #7C6BF0", borderRadius: "0.5vw", padding: "0.5vh 1vw" }}>
              <span style={{ fontSize: "0.85vw", fontWeight: 700, color: "#7C6BF0", letterSpacing: "0.05em" }}>CONCURRENTIE ANALYSE</span>
            </div>
            <span style={{ fontSize: "2vw", color: "#4F7FFF", fontWeight: 700 }}>&#8594;</span>
            <div style={{ background: "linear-gradient(135deg, rgba(79,127,255,0.25), rgba(124,107,240,0.25))", border: "1px solid rgba(79,127,255,0.5)", borderRadius: "0.5vw", padding: "0.5vh 1.2vw" }}>
              <span style={{ fontSize: "0.85vw", fontWeight: 800, color: "#F0F4FF", letterSpacing: "0.05em" }}>1 GEINTEGREERD PLATFORM</span>
            </div>
          </div>
          <div style={{ width: "1px", height: "3vh", background: "rgba(79,127,255,0.3)", flexShrink: 0 }} />
          <span style={{ fontSize: "0.9vw", color: "#8892B0", lineHeight: 1.5 }}>Twee projectplannen samengevoegd tot een platform — doordat AI beide disciplines op dezelfde data en infrastructuur laat draaien.</span>
        </div>
      </div>

      {/* Main content */}
      <div className="absolute inset-0 flex flex-col justify-center" style={{ padding: "0 5vw", paddingTop: "20vh" }}>
        <div style={{ maxWidth: "60vw" }}>
          <h1 style={{ fontSize: "5.5vw", fontWeight: 900, lineHeight: 1.05, letterSpacing: "-0.02em", color: "#F0F4FF", marginBottom: "2.5vh" }}>
            AI Pricing &amp;<br />
            <span style={{ background: "linear-gradient(90deg, #4F7FFF, #7C6BF0)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>Commercial Intelligence</span>
          </h1>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "1.5vw", marginBottom: "3vh" }}>
            <div style={{ display: "flex", alignItems: "flex-start", gap: "0.6vw" }}>
              <div style={{ width: "0.5vw", height: "0.5vw", borderRadius: "50%", background: "#4F7FFF", marginTop: "0.8vh", flexShrink: 0 }} />
              <span style={{ fontSize: "1vw", color: "#8892B0", lineHeight: 1.5 }}>Slimmere pricingbeslissingen</span>
            </div>
            <div style={{ display: "flex", alignItems: "flex-start", gap: "0.6vw" }}>
              <div style={{ width: "0.5vw", height: "0.5vw", borderRadius: "50%", background: "#7C6BF0", marginTop: "0.8vh", flexShrink: 0 }} />
              <span style={{ fontSize: "1vw", color: "#8892B0", lineHeight: 1.5 }}>Meer grip op concurrentie</span>
            </div>
            <div style={{ display: "flex", alignItems: "flex-start", gap: "0.6vw" }}>
              <div style={{ width: "0.5vw", height: "0.5vw", borderRadius: "50%", background: "#4F7FFF", marginTop: "0.8vh", flexShrink: 0 }} />
              <span style={{ fontSize: "1vw", color: "#8892B0", lineHeight: 1.5 }}>Inzicht in huismerkpotentie</span>
            </div>
            <div style={{ display: "flex", alignItems: "flex-start", gap: "0.6vw" }}>
              <div style={{ width: "0.5vw", height: "0.5vw", borderRadius: "50%", background: "#7C6BF0", marginTop: "0.8vh", flexShrink: 0 }} />
              <span style={{ fontSize: "1vw", color: "#8892B0", lineHeight: 1.5 }}>Hogere portfoliomarge</span>
            </div>
            <div style={{ display: "flex", alignItems: "flex-start", gap: "0.6vw" }}>
              <div style={{ width: "0.5vw", height: "0.5vw", borderRadius: "50%", background: "#4F7FFF", marginTop: "0.8vh", flexShrink: 0 }} />
              <span style={{ fontSize: "1vw", color: "#8892B0", lineHeight: 1.5 }}>Minder handmatig werk</span>
            </div>
            <div style={{ display: "flex", alignItems: "flex-start", gap: "0.6vw" }}>
              <div style={{ width: "0.5vw", height: "0.5vw", borderRadius: "50%", background: "#7C6BF0", marginTop: "0.8vh", flexShrink: 0 }} />
              <span style={{ fontSize: "1vw", color: "#8892B0", lineHeight: 1.5 }}>Onderbouwde besluitvorming</span>
            </div>
          </div>

          <div style={{ background: "rgba(79,127,255,0.08)", border: "1px solid rgba(79,127,255,0.2)", borderRadius: "0.8vw", padding: "1.5vh 1.8vw", display: "flex", alignItems: "center", gap: "0.8vw" }}>
            <div style={{ width: "0.3vw", height: "3.5vh", background: "#4F7FFF", borderRadius: "1px", flexShrink: 0 }} />
            <span style={{ fontSize: "1.05vw", color: "#F0F4FF", fontWeight: 500 }}>Belangrijk uitgangspunt: <span style={{ color: "#8892B0", fontWeight: 400 }}>AI ondersteunt de pricing specialist. AI vervangt de pricing specialist niet.</span></span>
          </div>
        </div>
      </div>

      {/* Bottom line */}
      <div className="absolute bottom-0 left-0 right-0" style={{ height: "0.4vh", background: "linear-gradient(90deg, transparent, #4F7FFF, #7C6BF0, transparent)" }} />
    </div>
  );
}
