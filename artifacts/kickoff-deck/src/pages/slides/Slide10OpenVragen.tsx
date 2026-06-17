export default function Slide10OpenVragen() {
  return (
    <div className="relative w-screen h-screen overflow-hidden" style={{ background: "#0C0F1A", fontFamily: "Inter, system-ui, sans-serif" }}>
      <div className="absolute inset-0" style={{ backgroundImage: "linear-gradient(rgba(79,127,255,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(79,127,255,0.05) 1px, transparent 1px)", backgroundSize: "6vw 6vw" }} />
      <div className="absolute" style={{ width: "40vw", height: "40vw", borderRadius: "50%", background: "radial-gradient(circle, rgba(79,127,255,0.08) 0%, transparent 70%)", top: "-10vw", right: "-8vw" }} />

      <div className="absolute" style={{ top: "3.5vh", left: "5vw", color: "#4F7FFF", fontSize: "0.9vw", fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase" }}>09 — Belangrijkste open vragen</div>
      <div className="absolute bottom-0 left-0 right-0" style={{ height: "0.3vh", background: "linear-gradient(90deg, transparent, #4F7FFF, #7C6BF0, transparent)" }} />

      <div className="absolute inset-0 flex flex-col" style={{ padding: "8.5vh 5vw 6.5vh 5vw" }}>
        <h2 style={{ fontSize: "3.2vw", fontWeight: 800, color: "#F0F4FF", marginBottom: "3.5vh", letterSpacing: "-0.02em", lineHeight: 1.1 }}>
          Discussiepunten voor de kick-off
        </h2>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "1.5vw" }}>

          <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(79,127,255,0.2)", borderRadius: "0.8vw", padding: "2vh 1.6vw" }}>
            <div style={{ fontSize: "0.8vw", color: "#4F7FFF", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: "1.2vh" }}>Scope</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.8vh" }}>
              <div style={{ display: "flex", gap: "0.5vw", alignItems: "flex-start" }}>
                <div style={{ width: "0.35vw", height: "0.35vw", borderRadius: "50%", background: "#8892B0", marginTop: "0.6vh", flexShrink: 0 }} />
                <span style={{ fontSize: "0.88vw", color: "#8892B0", lineHeight: 1.5 }}>Alleen Nederland?</span>
              </div>
              <div style={{ display: "flex", gap: "0.5vw", alignItems: "flex-start" }}>
                <div style={{ width: "0.35vw", height: "0.35vw", borderRadius: "50%", background: "#8892B0", marginTop: "0.6vh", flexShrink: 0 }} />
                <span style={{ fontSize: "0.88vw", color: "#8892B0", lineHeight: 1.5 }}>Partnershops meenemen?</span>
              </div>
              <div style={{ display: "flex", gap: "0.5vw", alignItems: "flex-start" }}>
                <div style={{ width: "0.35vw", height: "0.35vw", borderRadius: "50%", background: "#8892B0", marginTop: "0.6vh", flexShrink: 0 }} />
                <span style={{ fontSize: "0.88vw", color: "#8892B0", lineHeight: 1.5 }}>Belgie in scope?</span>
              </div>
            </div>
          </div>

          <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(124,107,240,0.2)", borderRadius: "0.8vw", padding: "2vh 1.6vw" }}>
            <div style={{ fontSize: "0.8vw", color: "#7C6BF0", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: "1.2vh" }}>Concurrentie</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.8vh" }}>
              <div style={{ display: "flex", gap: "0.5vw", alignItems: "flex-start" }}>
                <div style={{ width: "0.35vw", height: "0.35vw", borderRadius: "50%", background: "#8892B0", marginTop: "0.6vh", flexShrink: 0 }} />
                <span style={{ fontSize: "0.88vw", color: "#8892B0", lineHeight: 1.5 }}>Wat definieert een concurrent?</span>
              </div>
              <div style={{ display: "flex", gap: "0.5vw", alignItems: "flex-start" }}>
                <div style={{ width: "0.35vw", height: "0.35vw", borderRadius: "50%", background: "#8892B0", marginTop: "0.6vh", flexShrink: 0 }} />
                <span style={{ fontSize: "0.88vw", color: "#8892B0", lineHeight: 1.5 }}>Hoe bepalen we relevantie?</span>
              </div>
            </div>
          </div>

          <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(79,127,255,0.2)", borderRadius: "0.8vw", padding: "2vh 1.6vw" }}>
            <div style={{ fontSize: "0.8vw", color: "#4F7FFF", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: "1.2vh" }}>Huismerk</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.8vh" }}>
              <div style={{ display: "flex", gap: "0.5vw", alignItems: "flex-start" }}>
                <div style={{ width: "0.35vw", height: "0.35vw", borderRadius: "50%", background: "#8892B0", marginTop: "0.6vh", flexShrink: 0 }} />
                <span style={{ fontSize: "0.88vw", color: "#8892B0", lineHeight: 1.5 }}>Wanneer sturen we actief op substitutie?</span>
              </div>
              <div style={{ display: "flex", gap: "0.5vw", alignItems: "flex-start" }}>
                <div style={{ width: "0.35vw", height: "0.35vw", borderRadius: "50%", background: "#8892B0", marginTop: "0.6vh", flexShrink: 0 }} />
                <span style={{ fontSize: "0.88vw", color: "#8892B0", lineHeight: 1.5 }}>Wanneer beschermen we OEM-positie?</span>
              </div>
            </div>
          </div>

          <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(124,107,240,0.2)", borderRadius: "0.8vw", padding: "2vh 1.6vw" }}>
            <div style={{ fontSize: "0.8vw", color: "#7C6BF0", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: "1.2vh" }}>Forecasting</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.8vh" }}>
              <div style={{ display: "flex", gap: "0.5vw", alignItems: "flex-start" }}>
                <div style={{ width: "0.35vw", height: "0.35vw", borderRadius: "50%", background: "#8892B0", marginTop: "0.6vh", flexShrink: 0 }} />
                <span style={{ fontSize: "0.88vw", color: "#8892B0", lineHeight: 1.5 }}>Welke data missen we nog?</span>
              </div>
            </div>
          </div>

          <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(79,127,255,0.2)", borderRadius: "0.8vw", padding: "2vh 1.6vw" }}>
            <div style={{ fontSize: "0.8vw", color: "#4F7FFF", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: "1.2vh" }}>Traffic</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.8vh" }}>
              <div style={{ display: "flex", gap: "0.5vw", alignItems: "flex-start" }}>
                <div style={{ width: "0.35vw", height: "0.35vw", borderRadius: "50%", background: "#8892B0", marginTop: "0.6vh", flexShrink: 0 }} />
                <span style={{ fontSize: "0.88vw", color: "#8892B0", lineHeight: 1.5 }}>Welke producten zijn trafficdrivers?</span>
              </div>
              <div style={{ display: "flex", gap: "0.5vw", alignItems: "flex-start" }}>
                <div style={{ width: "0.35vw", height: "0.35vw", borderRadius: "50%", background: "#8892B0", marginTop: "0.6vh", flexShrink: 0 }} />
                <span style={{ fontSize: "0.88vw", color: "#8892B0", lineHeight: 1.5 }}>Hoe meten we zoekvolume per SKU?</span>
              </div>
            </div>
          </div>

          <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(124,107,240,0.2)", borderRadius: "0.8vw", padding: "2vh 1.6vw" }}>
            <div style={{ fontSize: "0.8vw", color: "#7C6BF0", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: "1.2vh" }}>Governance</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.8vh" }}>
              <div style={{ display: "flex", gap: "0.5vw", alignItems: "flex-start" }}>
                <div style={{ width: "0.35vw", height: "0.35vw", borderRadius: "50%", background: "#8892B0", marginTop: "0.6vh", flexShrink: 0 }} />
                <span style={{ fontSize: "0.88vw", color: "#8892B0", lineHeight: 1.5 }}>Welke beslissingen mogen automatisch?</span>
              </div>
              <div style={{ display: "flex", gap: "0.5vw", alignItems: "flex-start" }}>
                <div style={{ width: "0.35vw", height: "0.35vw", borderRadius: "50%", background: "#8892B0", marginTop: "0.6vh", flexShrink: 0 }} />
                <span style={{ fontSize: "0.88vw", color: "#8892B0", lineHeight: 1.5 }}>Welke vereisen menselijke goedkeuring?</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
