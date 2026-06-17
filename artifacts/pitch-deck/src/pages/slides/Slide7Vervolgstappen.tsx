export default function Slide7Vervolgstappen() {
  return (
    <div className="relative w-screen h-screen overflow-hidden" style={{ background: "#0C0F1A", fontFamily: "Inter, system-ui, sans-serif" }}>

      {/* Grid texture */}
      <div className="absolute inset-0" style={{
        backgroundImage: "linear-gradient(rgba(79,127,255,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(79,127,255,0.05) 1px, transparent 1px)",
        backgroundSize: "6vw 6vw"
      }} />

      {/* Glow */}
      <div className="absolute" style={{
        width: "40vw", height: "40vw", borderRadius: "50%",
        background: "radial-gradient(circle, rgba(79,127,255,0.1) 0%, transparent 70%)",
        bottom: "-15vw", right: "-5vw"
      }} />

      {/* Slide label */}
      <div className="absolute" style={{ top: "4vh", left: "5vw", color: "#4F7FFF", fontSize: "0.9vw", fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase" }}>06 — Vervolgstappen</div>

      {/* Bottom line */}
      <div className="absolute bottom-0 left-0 right-0" style={{ height: "0.3vh", background: "linear-gradient(90deg, transparent, #4F7FFF, #7C6BF0, transparent)" }} />

      <div className="absolute inset-0 flex flex-col" style={{ padding: "9vh 5vw 8vh 5vw" }}>

        <h2 style={{ fontSize: "3.8vw", fontWeight: 800, color: "#F0F4FF", marginBottom: "5vh", letterSpacing: "-0.02em", lineHeight: 1.1 }}>
          Roadmap naar volledige uitrol
        </h2>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "2.5vw", flex: 1 }}>

          {/* Phase 1 */}
          <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(79,127,255,0.35)", borderRadius: "1vw", padding: "3.5vh 2.2vw", position: "relative" }}>
            <div style={{ position: "absolute", top: "-1.5vh", left: "2vw" }}>
              <span style={{ background: "linear-gradient(135deg, #4F7FFF, #7C6BF0)", borderRadius: "2vw", padding: "0.4vh 1.2vw", fontSize: "0.8vw", fontWeight: 700, color: "white" }}>Nu actief</span>
            </div>
            <div style={{ fontSize: "2vw", fontWeight: 900, color: "#4F7FFF", marginBottom: "0.5vh", marginTop: "1.5vh" }}>Fase 1</div>
            <div style={{ fontSize: "1.2vw", fontWeight: 700, color: "#F0F4FF", marginBottom: "2vh" }}>Pilot — 9 categorieen</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "1.2vh" }}>
              <div style={{ display: "flex", gap: "0.8vw", alignItems: "flex-start" }}>
                <div style={{ width: "0.4vw", height: "0.4vw", borderRadius: "50%", background: "#4F7FFF", marginTop: "0.6vh", flexShrink: 0 }} />
                <span style={{ fontSize: "0.95vw", color: "#8892B0", lineHeight: 1.5 }}>26 SKU's volledig operationeel</span>
              </div>
              <div style={{ display: "flex", gap: "0.8vw", alignItems: "flex-start" }}>
                <div style={{ width: "0.4vw", height: "0.4vw", borderRadius: "50%", background: "#4F7FFF", marginTop: "0.6vh", flexShrink: 0 }} />
                <span style={{ fontSize: "0.95vw", color: "#8892B0", lineHeight: 1.5 }}>PriceShape-koppeling actief</span>
              </div>
              <div style={{ display: "flex", gap: "0.8vw", alignItems: "flex-start" }}>
                <div style={{ width: "0.4vw", height: "0.4vw", borderRadius: "50%", background: "#4F7FFF", marginTop: "0.6vh", flexShrink: 0 }} />
                <span style={{ fontSize: "0.95vw", color: "#8892B0", lineHeight: 1.5 }}>A/B-test gestart en meetbaar</span>
              </div>
              <div style={{ display: "flex", gap: "0.8vw", alignItems: "flex-start" }}>
                <div style={{ width: "0.4vw", height: "0.4vw", borderRadius: "50%", background: "#4F7FFF", marginTop: "0.6vh", flexShrink: 0 }} />
                <span style={{ fontSize: "0.95vw", color: "#8892B0", lineHeight: 1.5 }}>4 gebruikersrollen ingericht</span>
              </div>
            </div>
          </div>

          {/* Phase 2 */}
          <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(124,107,240,0.25)", borderRadius: "1vw", padding: "3.5vh 2.2vw" }}>
            <div style={{ fontSize: "2vw", fontWeight: 900, color: "#7C6BF0", marginBottom: "0.5vh" }}>Fase 2</div>
            <div style={{ fontSize: "1.2vw", fontWeight: 700, color: "#F0F4FF", marginBottom: "0.5vh" }}>Schaalvergroting</div>
            <div style={{ fontSize: "0.85vw", color: "#8892B0", marginBottom: "2vh" }}>Q3 2026</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "1.2vh" }}>
              <div style={{ display: "flex", gap: "0.8vw", alignItems: "flex-start" }}>
                <div style={{ width: "0.4vw", height: "0.4vw", borderRadius: "50%", background: "#7C6BF0", marginTop: "0.6vh", flexShrink: 0 }} />
                <span style={{ fontSize: "0.95vw", color: "#8892B0", lineHeight: 1.5 }}>Uitbreiding naar 500+ SKU's</span>
              </div>
              <div style={{ display: "flex", gap: "0.8vw", alignItems: "flex-start" }}>
                <div style={{ width: "0.4vw", height: "0.4vw", borderRadius: "50%", background: "#7C6BF0", marginTop: "0.6vh", flexShrink: 0 }} />
                <span style={{ fontSize: "0.95vw", color: "#8892B0", lineHeight: 1.5 }}>Automatische retraining maandelijks</span>
              </div>
              <div style={{ display: "flex", gap: "0.8vw", alignItems: "flex-start" }}>
                <div style={{ width: "0.4vw", height: "0.4vw", borderRadius: "50%", background: "#7C6BF0", marginTop: "0.6vh", flexShrink: 0 }} />
                <span style={{ fontSize: "0.95vw", color: "#8892B0", lineHeight: 1.5 }}>Bulk-goedkeuring geoptimaliseerd</span>
              </div>
              <div style={{ display: "flex", gap: "0.8vw", alignItems: "flex-start" }}>
                <div style={{ width: "0.4vw", height: "0.4vw", borderRadius: "50%", background: "#7C6BF0", marginTop: "0.6vh", flexShrink: 0 }} />
                <span style={{ fontSize: "0.95vw", color: "#8892B0", lineHeight: 1.5 }}>Externe datakoppelingen uitgebreid</span>
              </div>
            </div>
          </div>

          {/* Phase 3 */}
          <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(79,127,255,0.2)", borderRadius: "1vw", padding: "3.5vh 2.2vw" }}>
            <div style={{ fontSize: "2vw", fontWeight: 900, color: "#4F7FFF", marginBottom: "0.5vh" }}>Fase 3</div>
            <div style={{ fontSize: "1.2vw", fontWeight: 700, color: "#F0F4FF", marginBottom: "0.5vh" }}>Volledige uitrol</div>
            <div style={{ fontSize: "0.85vw", color: "#8892B0", marginBottom: "2vh" }}>Q1 2027</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "1.2vh" }}>
              <div style={{ display: "flex", gap: "0.8vw", alignItems: "flex-start" }}>
                <div style={{ width: "0.4vw", height: "0.4vw", borderRadius: "50%", background: "#4F7FFF", marginTop: "0.6vh", flexShrink: 0 }} />
                <span style={{ fontSize: "0.95vw", color: "#8892B0", lineHeight: 1.5 }}>Alle 26.000+ SKU's onder AI</span>
              </div>
              <div style={{ display: "flex", gap: "0.8vw", alignItems: "flex-start" }}>
                <div style={{ width: "0.4vw", height: "0.4vw", borderRadius: "50%", background: "#4F7FFF", marginTop: "0.6vh", flexShrink: 0 }} />
                <span style={{ fontSize: "0.95vw", color: "#8892B0", lineHeight: 1.5 }}>Realtime prijsreactie (&lt;15 min)</span>
              </div>
              <div style={{ display: "flex", gap: "0.8vw", alignItems: "flex-start" }}>
                <div style={{ width: "0.4vw", height: "0.4vw", borderRadius: "50%", background: "#4F7FFF", marginTop: "0.6vh", flexShrink: 0 }} />
                <span style={{ fontSize: "0.95vw", color: "#8892B0", lineHeight: 1.5 }}>Vraagprognose geintegreerd</span>
              </div>
              <div style={{ display: "flex", gap: "0.8vw", alignItems: "flex-start" }}>
                <div style={{ width: "0.4vw", height: "0.4vw", borderRadius: "50%", background: "#4F7FFF", marginTop: "0.6vh", flexShrink: 0 }} />
                <span style={{ fontSize: "0.95vw", color: "#8892B0", lineHeight: 1.5 }}>B2B-kanaal volledig ondersteund</span>
              </div>
            </div>
          </div>
        </div>

        <div style={{ marginTop: "4vh", padding: "2vh 2.5vw", background: "rgba(79,127,255,0.08)", border: "1px solid rgba(79,127,255,0.15)", borderRadius: "0.8vw", display: "flex", alignItems: "center", gap: "1vw" }}>
          <div style={{ width: "0.3vw", height: "3.5vh", background: "#4F7FFF", borderRadius: "1px", flexShrink: 0 }} />
          <p style={{ fontSize: "1.05vw", color: "#8892B0", margin: 0 }}>
            <span style={{ color: "#F0F4FF", fontWeight: 600 }}>Directe actiepunten:</span> Besluit over productiedeployment, budget Q3 vrijgeven, datakoppeling live-omgeving goedkeuren.
          </p>
        </div>
      </div>
    </div>
  );
}
