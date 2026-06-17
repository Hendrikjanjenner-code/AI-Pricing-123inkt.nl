export default function Slide3Oplossing() {
  return (
    <div className="relative w-screen h-screen overflow-hidden" style={{ background: "#0C0F1A", fontFamily: "Inter, system-ui, sans-serif" }}>

      {/* Grid texture */}
      <div className="absolute inset-0" style={{
        backgroundImage: "linear-gradient(rgba(79,127,255,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(79,127,255,0.05) 1px, transparent 1px)",
        backgroundSize: "6vw 6vw"
      }} />

      {/* Glow */}
      <div className="absolute" style={{
        width: "50vw", height: "50vw", borderRadius: "50%",
        background: "radial-gradient(circle, rgba(79,127,255,0.12) 0%, transparent 70%)",
        top: "-20vw", right: "-15vw"
      }} />

      {/* Slide label */}
      <div className="absolute" style={{ top: "4vh", left: "5vw", color: "#4F7FFF", fontSize: "0.9vw", fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase" }}>02 — De Oplossing</div>

      {/* Bottom line */}
      <div className="absolute bottom-0 left-0 right-0" style={{ height: "0.3vh", background: "linear-gradient(90deg, transparent, #4F7FFF, #7C6BF0, transparent)" }} />

      {/* Two-column layout */}
      <div className="absolute inset-0 flex" style={{ padding: "10vh 5vw 8vh 5vw", gap: "5vw" }}>

        {/* Left: text */}
        <div style={{ flex: "0 0 42vw", display: "flex", flexDirection: "column", justifyContent: "center" }}>
          <h2 style={{ fontSize: "4vw", fontWeight: 800, color: "#F0F4FF", marginBottom: "3.5vh", letterSpacing: "-0.02em", lineHeight: 1.1, textWrap: "balance" }}>
            Een AI-cockpit voor elke prijsbeslissing
          </h2>
          <p style={{ fontSize: "1.2vw", color: "#8892B0", lineHeight: 1.7, marginBottom: "4vh" }}>
            Het platform genereert dagelijks aanbevelingen per SKU op basis van 8 geoptimaliseerde strategieen. Analisten keuren goed, verwerpen of overschrijven — het systeem leert en publiceert automatisch naar PriceShape.
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: "2vh" }}>
            <div style={{ display: "flex", alignItems: "flex-start", gap: "1.2vw" }}>
              <div style={{ width: "1.6vw", height: "1.6vw", borderRadius: "50%", background: "rgba(79,127,255,0.2)", border: "1px solid #4F7FFF", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginTop: "0.2vh" }}>
                <div style={{ width: "0.4vw", height: "0.4vw", borderRadius: "50%", background: "#4F7FFF" }} />
              </div>
              <div>
                <div style={{ fontSize: "1.1vw", fontWeight: 600, color: "#F0F4FF", marginBottom: "0.3vh" }}>Dagelijkse AI-run</div>
                <div style={{ fontSize: "0.95vw", color: "#8892B0", lineHeight: 1.5 }}>Prijsmotor draait automatisch elke nacht, genereert aanbevelingen voor alle actieve SKU's.</div>
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "flex-start", gap: "1.2vw" }}>
              <div style={{ width: "1.6vw", height: "1.6vw", borderRadius: "50%", background: "rgba(124,107,240,0.2)", border: "1px solid #7C6BF0", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginTop: "0.2vh" }}>
                <div style={{ width: "0.4vw", height: "0.4vw", borderRadius: "50%", background: "#7C6BF0" }} />
              </div>
              <div>
                <div style={{ fontSize: "1.1vw", fontWeight: 600, color: "#F0F4FF", marginBottom: "0.3vh" }}>Human-in-the-loop</div>
                <div style={{ fontSize: "0.95vw", color: "#8892B0", lineHeight: 1.5 }}>Analisten behouden volledige controle — elk advies is uitlegbaar, auditeerbaar en overschrijfbaar.</div>
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "flex-start", gap: "1.2vw" }}>
              <div style={{ width: "1.6vw", height: "1.6vw", borderRadius: "50%", background: "rgba(79,127,255,0.2)", border: "1px solid #4F7FFF", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginTop: "0.2vh" }}>
                <div style={{ width: "0.4vw", height: "0.4vw", borderRadius: "50%", background: "#4F7FFF" }} />
              </div>
              <div>
                <div style={{ fontSize: "1.1vw", fontWeight: 600, color: "#F0F4FF", marginBottom: "0.3vh" }}>Directe PriceShape-integratie</div>
                <div style={{ fontSize: "0.95vw", color: "#8892B0", lineHeight: 1.5 }}>Goedgekeurde prijzen worden automatisch als CSV geexporteerd en in PriceShape geladen.</div>
              </div>
            </div>
          </div>
        </div>

        {/* Right: flow diagram */}
        <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: "1.2vh" }}>

            {/* Step 1 */}
            <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(79,127,255,0.25)", borderRadius: "0.8vw", padding: "1.8vh 1.8vw", display: "flex", alignItems: "center", gap: "1.2vw" }}>
              <div style={{ width: "2.8vw", height: "2.8vw", borderRadius: "0.6vw", background: "linear-gradient(135deg, #4F7FFF, #7C6BF0)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                <span style={{ color: "white", fontSize: "1vw", fontWeight: 700 }}>1</span>
              </div>
              <div>
                <div style={{ fontSize: "1vw", fontWeight: 600, color: "#F0F4FF" }}>Data-ingest</div>
                <div style={{ fontSize: "0.85vw", color: "#8892B0" }}>Verkoop, voorraad, concurrentprijzen, historische data</div>
              </div>
            </div>

            <div style={{ display: "flex", justifyContent: "center" }}>
              <div style={{ width: "0.2vw", height: "2vh", background: "rgba(79,127,255,0.4)" }} />
            </div>

            {/* Step 2 */}
            <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(79,127,255,0.25)", borderRadius: "0.8vw", padding: "1.8vh 1.8vw", display: "flex", alignItems: "center", gap: "1.2vw" }}>
              <div style={{ width: "2.8vw", height: "2.8vw", borderRadius: "0.6vw", background: "linear-gradient(135deg, #4F7FFF, #7C6BF0)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                <span style={{ color: "white", fontSize: "1vw", fontWeight: 700 }}>2</span>
              </div>
              <div>
                <div style={{ fontSize: "1vw", fontWeight: 600, color: "#F0F4FF" }}>AI-prijsmotor</div>
                <div style={{ fontSize: "0.85vw", color: "#8892B0" }}>8 strategieen, veiligheidsregels, confidence score</div>
              </div>
            </div>

            <div style={{ display: "flex", justifyContent: "center" }}>
              <div style={{ width: "0.2vw", height: "2vh", background: "rgba(79,127,255,0.4)" }} />
            </div>

            {/* Step 3 */}
            <div style={{ background: "rgba(79,127,255,0.1)", border: "1px solid rgba(79,127,255,0.4)", borderRadius: "0.8vw", padding: "1.8vh 1.8vw", display: "flex", alignItems: "center", gap: "1.2vw" }}>
              <div style={{ width: "2.8vw", height: "2.8vw", borderRadius: "0.6vw", background: "linear-gradient(135deg, #4F7FFF, #7C6BF0)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                <span style={{ color: "white", fontSize: "1vw", fontWeight: 700 }}>3</span>
              </div>
              <div>
                <div style={{ fontSize: "1vw", fontWeight: 600, color: "#F0F4FF" }}>Analist-review</div>
                <div style={{ fontSize: "0.85vw", color: "#8892B0" }}>Goedkeuren, verwerpen of overschrijven met uitleg</div>
              </div>
            </div>

            <div style={{ display: "flex", justifyContent: "center" }}>
              <div style={{ width: "0.2vw", height: "2vh", background: "rgba(79,127,255,0.4)" }} />
            </div>

            {/* Step 4 */}
            <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(79,127,255,0.25)", borderRadius: "0.8vw", padding: "1.8vh 1.8vw", display: "flex", alignItems: "center", gap: "1.2vw" }}>
              <div style={{ width: "2.8vw", height: "2.8vw", borderRadius: "0.6vw", background: "linear-gradient(135deg, #4F7FFF, #7C6BF0)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                <span style={{ color: "white", fontSize: "1vw", fontWeight: 700 }}>4</span>
              </div>
              <div>
                <div style={{ fontSize: "1vw", fontWeight: 600, color: "#F0F4FF" }}>Publicatie PriceShape</div>
                <div style={{ fontSize: "0.85vw", color: "#8892B0" }}>CSV-export, live prijzen zichtbaar binnen minuten</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
