export default function Slide6Explainability() {
  return (
    <div className="relative w-screen h-screen overflow-hidden" style={{ background: "#0C0F1A", fontFamily: "Inter, system-ui, sans-serif" }}>

      {/* Grid texture */}
      <div className="absolute inset-0" style={{
        backgroundImage: "linear-gradient(rgba(79,127,255,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(79,127,255,0.05) 1px, transparent 1px)",
        backgroundSize: "6vw 6vw"
      }} />

      {/* Glow */}
      <div className="absolute" style={{
        width: "45vw", height: "45vw", borderRadius: "50%",
        background: "radial-gradient(circle, rgba(79,127,255,0.12) 0%, transparent 70%)",
        top: "-15vw", right: "-10vw"
      }} />

      {/* Slide label */}
      <div className="absolute" style={{ top: "4vh", left: "5vw", color: "#4F7FFF", fontSize: "0.9vw", fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase" }}>05 — Explainability</div>

      {/* Bottom line */}
      <div className="absolute bottom-0 left-0 right-0" style={{ height: "0.3vh", background: "linear-gradient(90deg, transparent, #4F7FFF, #7C6BF0, transparent)" }} />

      <div className="absolute inset-0 flex" style={{ padding: "9vh 5vw 8vh 5vw", gap: "5vw" }}>

        {/* Left */}
        <div style={{ flex: "0 0 40vw", display: "flex", flexDirection: "column", justifyContent: "center" }}>
          <h2 style={{ fontSize: "3.8vw", fontWeight: 800, color: "#F0F4FF", marginBottom: "3vh", letterSpacing: "-0.02em", lineHeight: 1.1, textWrap: "balance" }}>
            Elk advies volledig uitlegbaar
          </h2>
          <p style={{ fontSize: "1.15vw", color: "#8892B0", lineHeight: 1.7, marginBottom: "4vh" }}>
            Analisten en management zien exact welke factoren elke prijsaanbeveling bepalen. Geen black box — volledig transparant, auditeerbaar en uitlegbaar aan stakeholders.
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: "2vh" }}>
            <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(79,127,255,0.2)", borderRadius: "0.8vw", padding: "2vh 1.8vw", display: "flex", alignItems: "center", gap: "1.2vw" }}>
              <div style={{ width: "2.2vw", height: "2.2vw", borderRadius: "0.5vw", background: "rgba(79,127,255,0.15)", border: "1px solid rgba(79,127,255,0.3)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                <svg width="50%" height="50%" viewBox="0 0 24 24" fill="none"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="#4F7FFF" strokeWidth="2" strokeLinecap="round"/></svg>
              </div>
              <div>
                <div style={{ fontSize: "1vw", fontWeight: 600, color: "#F0F4FF" }}>Factor-breakdown per SKU</div>
                <div style={{ fontSize: "0.85vw", color: "#8892B0" }}>Marge, concurrentie, voorraad, seizoen, elasticiteit gewogen</div>
              </div>
            </div>

            <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(124,107,240,0.2)", borderRadius: "0.8vw", padding: "2vh 1.8vw", display: "flex", alignItems: "center", gap: "1.2vw" }}>
              <div style={{ width: "2.2vw", height: "2.2vw", borderRadius: "0.5vw", background: "rgba(124,107,240,0.15)", border: "1px solid rgba(124,107,240,0.3)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                <svg width="50%" height="50%" viewBox="0 0 24 24" fill="none"><path d="M9 19V6l12-3v13" stroke="#7C6BF0" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/><circle cx="6" cy="19" r="3" stroke="#7C6BF0" strokeWidth="2"/><circle cx="18" cy="16" r="3" stroke="#7C6BF0" strokeWidth="2"/></svg>
              </div>
              <div>
                <div style={{ fontSize: "1vw", fontWeight: 600, color: "#F0F4FF" }}>Confidence score 0-100%</div>
                <div style={{ fontSize: "0.85vw", color: "#8892B0" }}>Waarschuwing bij lage zekerheid, automatisch geflagged</div>
              </div>
            </div>

            <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(79,127,255,0.2)", borderRadius: "0.8vw", padding: "2vh 1.8vw", display: "flex", alignItems: "center", gap: "1.2vw" }}>
              <div style={{ width: "2.2vw", height: "2.2vw", borderRadius: "0.5vw", background: "rgba(79,127,255,0.15)", border: "1px solid rgba(79,127,255,0.3)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                <svg width="50%" height="50%" viewBox="0 0 24 24" fill="none"><rect x="5" y="2" width="14" height="20" rx="2" stroke="#4F7FFF" strokeWidth="2"/><path d="M9 7h6M9 11h6M9 15h4" stroke="#4F7FFF" strokeWidth="2" strokeLinecap="round"/></svg>
              </div>
              <div>
                <div style={{ fontSize: "1vw", fontWeight: 600, color: "#F0F4FF" }}>Volledige audittrail</div>
                <div style={{ fontSize: "0.85vw", color: "#8892B0" }}>Wie heeft wat goedgekeurd, wanneer, met welke reden</div>
              </div>
            </div>
          </div>
        </div>

        {/* Right: mock factor visualization */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center" }}>
          <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(79,127,255,0.2)", borderRadius: "1vw", padding: "3vh 2.5vw" }}>
            <div style={{ fontSize: "0.85vw", color: "#8892B0", marginBottom: "0.5vh", fontWeight: 500 }}>SKU-aanbeveling detail</div>
            <div style={{ fontSize: "1.2vw", fontWeight: 700, color: "#F0F4FF", marginBottom: "0.3vh" }}>HP 302XL Zwart — EUR 14,99 → 15,49</div>
            <div style={{ display: "flex", gap: "1vw", marginBottom: "2.5vh" }}>
              <span style={{ background: "rgba(79,127,255,0.15)", border: "1px solid rgba(79,127,255,0.3)", borderRadius: "0.4vw", padding: "0.2vh 0.8vw", fontSize: "0.8vw", color: "#4F7FFF", fontWeight: 600 }}>COMPETITOR_INDEX</span>
              <span style={{ background: "rgba(79,127,255,0.1)", border: "1px solid rgba(79,127,255,0.2)", borderRadius: "0.4vw", padding: "0.2vh 0.8vw", fontSize: "0.8vw", color: "#8892B0" }}>Confidence: 82%</span>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "1.8vh" }}>
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.6vh" }}>
                  <span style={{ fontSize: "0.9vw", color: "#8892B0" }}>Concurrentiepositie</span>
                  <span style={{ fontSize: "0.9vw", color: "#4F7FFF", fontWeight: 600 }}>+38</span>
                </div>
                <div style={{ height: "0.7vh", background: "rgba(79,127,255,0.15)", borderRadius: "1px", overflow: "hidden" }}>
                  <div style={{ width: "76%", height: "100%", background: "#4F7FFF", borderRadius: "1px" }} />
                </div>
              </div>
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.6vh" }}>
                  <span style={{ fontSize: "0.9vw", color: "#8892B0" }}>Margedoelstelling</span>
                  <span style={{ fontSize: "0.9vw", color: "#7C6BF0", fontWeight: 600 }}>+22</span>
                </div>
                <div style={{ height: "0.7vh", background: "rgba(124,107,240,0.15)", borderRadius: "1px", overflow: "hidden" }}>
                  <div style={{ width: "44%", height: "100%", background: "#7C6BF0", borderRadius: "1px" }} />
                </div>
              </div>
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.6vh" }}>
                  <span style={{ fontSize: "0.9vw", color: "#8892B0" }}>Seizoenseffect</span>
                  <span style={{ fontSize: "0.9vw", color: "#4F7FFF", fontWeight: 600 }}>+12</span>
                </div>
                <div style={{ height: "0.7vh", background: "rgba(79,127,255,0.15)", borderRadius: "1px", overflow: "hidden" }}>
                  <div style={{ width: "24%", height: "100%", background: "#4F7FFF", opacity: 0.7, borderRadius: "1px" }} />
                </div>
              </div>
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.6vh" }}>
                  <span style={{ fontSize: "0.9vw", color: "#8892B0" }}>Voorraadstatus</span>
                  <span style={{ fontSize: "0.9vw", color: "#7C6BF0", fontWeight: 600 }}>+8</span>
                </div>
                <div style={{ height: "0.7vh", background: "rgba(124,107,240,0.15)", borderRadius: "1px", overflow: "hidden" }}>
                  <div style={{ width: "16%", height: "100%", background: "#7C6BF0", opacity: 0.7, borderRadius: "1px" }} />
                </div>
              </div>
            </div>

            <div style={{ marginTop: "2.5vh", padding: "1.5vh 1.2vw", background: "rgba(79,127,255,0.08)", border: "1px solid rgba(79,127,255,0.15)", borderRadius: "0.6vw" }}>
              <div style={{ fontSize: "0.85vw", color: "#8892B0", lineHeight: 1.5 }}>
                <span style={{ color: "#F0F4FF", fontWeight: 500 }}>Reden: </span>Concurrent Bol.com verlaagde prijs naar EUR 14,79. Concurrentie-index stijgt naar 101%. Marge boven minimumdrempel. Aanbeveling: +EUR 0,50 herstel.
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
