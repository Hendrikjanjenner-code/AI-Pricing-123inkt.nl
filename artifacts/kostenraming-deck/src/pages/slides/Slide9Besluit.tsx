export default function Slide9Besluit() {
  return (
    <div className="relative w-screen h-screen overflow-hidden" style={{ background: "#0C0F1A", fontFamily: "Inter, system-ui, sans-serif" }}>

      {/* Grid texture */}
      <div className="absolute inset-0" style={{
        backgroundImage: "linear-gradient(rgba(79,127,255,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(79,127,255,0.05) 1px, transparent 1px)",
        backgroundSize: "6vw 6vw"
      }} />

      {/* Subtle glow */}
      <div className="absolute" style={{
        width: "50vw", height: "50vw", borderRadius: "50%",
        background: "radial-gradient(circle, rgba(79,127,255,0.08) 0%, transparent 70%)",
        top: "-15vw", right: "-5vw"
      }} />

      <div className="absolute top-0 left-0 right-0 flex items-center justify-between" style={{ padding: "3vh 6vw" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.7vw" }}>
          <div style={{ width: "1.6vw", height: "1.6vw", borderRadius: "0.3vw", background: "linear-gradient(135deg, #4F7FFF, #7C6BF0)" }} />
          <span style={{ color: "#8892B0", fontSize: "1vw", fontWeight: 400 }}>123inkt</span>
        </div>
        <span style={{ color: "#8892B0", fontSize: "0.95vw" }}>Vertrouwelijk — Directie</span>
      </div>

      <div className="absolute" style={{ top: "12vh", left: "6vw", right: "6vw" }}>
        <div style={{ width: "3.5vw", height: "0.35vh", background: "#4F7FFF", marginBottom: "1.8vh" }} />
        <h2 style={{ fontSize: "3.2vw", fontWeight: 700, color: "#F0F4FF", lineHeight: 1.2, textWrap: "balance", maxWidth: "72vw" }}>
          Gevraagd besluit: goedkeuring voor pilotbudget van €94.000 voor 12 weken
        </h2>
      </div>

      {/* Two-column layout */}
      <div className="absolute" style={{ top: "33vh", left: "6vw", right: "6vw", display: "flex", gap: "4vw" }}>

        {/* Left: decision summary */}
        <div style={{ flex: 1 }}>

          <div style={{ fontSize: "1.2vw", fontWeight: 700, color: "#8892B0", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: "2vh" }}>Samenvatting besluitpunten</div>

          <div style={{ display: "flex", alignItems: "flex-start", gap: "1.2vw", marginBottom: "2vh" }}>
            <div style={{ width: "0.5vw", height: "0.5vw", borderRadius: "50%", background: "#4F7FFF", marginTop: "1.2vh", flexShrink: 0 }} />
            <div style={{ fontSize: "1.9vw", color: "#F0F4FF", lineHeight: 1.5 }}>
              Eenmalige pilotkosten: <strong style={{ color: "#4F7FFF" }}>€80.500</strong> — setup, scraping-configuratie en data-ontsluiting
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "flex-start", gap: "1.2vw", marginBottom: "2vh" }}>
            <div style={{ width: "0.5vw", height: "0.5vw", borderRadius: "50%", background: "#4F7FFF", marginTop: "1.2vh", flexShrink: 0 }} />
            <div style={{ fontSize: "1.9vw", color: "#F0F4FF", lineHeight: 1.5 }}>
              Drie maanden doorlopende kosten: <strong style={{ color: "#4F7FFF" }}>€13.500</strong> (3 × €4.500)
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "flex-start", gap: "1.2vw", marginBottom: "2vh" }}>
            <div style={{ width: "0.5vw", height: "0.5vw", borderRadius: "50%", background: "#4F7FFF", marginTop: "1.2vh", flexShrink: 0 }} />
            <div style={{ fontSize: "1.9vw", color: "#F0F4FF", lineHeight: 1.5 }}>
              Totaal pilotbudget: <strong style={{ color: "#4F7FFF" }}>€94.000</strong> bruto over 12 weken
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "flex-start", gap: "1.2vw", marginBottom: "2vh" }}>
            <div style={{ width: "0.5vw", height: "0.5vw", borderRadius: "50%", background: "#7C6BF0", marginTop: "1.2vh", flexShrink: 0 }} />
            <div style={{ fontSize: "1.9vw", color: "#F0F4FF", lineHeight: 1.5 }}>
              Go/no-go beslissing na week 8 op basis van tussentijdse KPI-rapportage
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "flex-start", gap: "1.2vw" }}>
            <div style={{ width: "0.5vw", height: "0.5vw", borderRadius: "50%", background: "#7C6BF0", marginTop: "1.2vh", flexShrink: 0 }} />
            <div style={{ fontSize: "1.9vw", color: "#F0F4FF", lineHeight: 1.5 }}>
              Verwacht ROI bij uitrol: <strong style={{ color: "#22C55E" }}>16,8× op jaarbasis</strong> — terugverdientijd 0,9 maanden
            </div>
          </div>
        </div>

        {/* Right: next steps */}
        <div style={{ width: "32vw" }}>

          <div style={{ fontSize: "1.2vw", fontWeight: 700, color: "#8892B0", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: "2vh" }}>Volgende stappen na goedkeuring</div>

          <div style={{ background: "#141828", border: "1px solid rgba(79,127,255,0.2)", borderRadius: "0.5vw", overflow: "hidden" }}>

            <div style={{ display: "flex", alignItems: "center", gap: "1.5vw", padding: "2vh 2vw", borderBottom: "1px solid rgba(79,127,255,0.1)" }}>
              <div style={{ width: "2.5vw", height: "2.5vw", borderRadius: "50%", background: "rgba(79,127,255,0.15)", border: "1px solid rgba(79,127,255,0.4)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                <span style={{ fontSize: "1.4vw", fontWeight: 700, color: "#4F7FFF" }}>1</span>
              </div>
              <div>
                <div style={{ fontSize: "1.7vw", color: "#F0F4FF", fontWeight: 700, lineHeight: 1.2 }}>Week 1: contractering</div>
                <div style={{ fontSize: "1.4vw", color: "#8892B0", marginTop: "0.3vh" }}>AWS-account activering, scraping-infrastructuur opleveren</div>
              </div>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "1.5vw", padding: "2vh 2vw", borderBottom: "1px solid rgba(79,127,255,0.1)" }}>
              <div style={{ width: "2.5vw", height: "2.5vw", borderRadius: "50%", background: "rgba(124,107,240,0.15)", border: "1px solid rgba(124,107,240,0.4)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                <span style={{ fontSize: "1.4vw", fontWeight: 700, color: "#7C6BF0" }}>2</span>
              </div>
              <div>
                <div style={{ fontSize: "1.7vw", color: "#F0F4FF", fontWeight: 700, lineHeight: 1.2 }}>Week 2–4: fase 1 setup</div>
                <div style={{ fontSize: "1.4vw", color: "#8892B0", marginTop: "0.3vh" }}>Data-engineering team aan de slag</div>
              </div>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "1.5vw", padding: "2vh 2vw", borderBottom: "1px solid rgba(79,127,255,0.1)" }}>
              <div style={{ width: "2.5vw", height: "2.5vw", borderRadius: "50%", background: "rgba(79,127,255,0.15)", border: "1px solid rgba(79,127,255,0.4)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                <span style={{ fontSize: "1.4vw", fontWeight: 700, color: "#4F7FFF" }}>3</span>
              </div>
              <div>
                <div style={{ fontSize: "1.7vw", color: "#F0F4FF", fontWeight: 700, lineHeight: 1.2 }}>Week 8: tussenrapportage</div>
                <div style={{ fontSize: "1.4vw", color: "#8892B0", marginTop: "0.3vh" }}>KPI-review aan directie — go/no-go fase 3</div>
              </div>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "1.5vw", padding: "2vh 2vw" }}>
              <div style={{ width: "2.5vw", height: "2.5vw", borderRadius: "50%", background: "rgba(34,197,94,0.12)", border: "1px solid rgba(34,197,94,0.35)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                <span style={{ fontSize: "1.4vw", fontWeight: 700, color: "#22C55E" }}>4</span>
              </div>
              <div>
                <div style={{ fontSize: "1.7vw", color: "#F0F4FF", fontWeight: 700, lineHeight: 1.2 }}>Week 12: eindrapportage</div>
                <div style={{ fontSize: "1.4vw", color: "#8892B0", marginTop: "0.3vh" }}>Besluit volledige uitrol 26.000+ SKU's</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom accent line */}
      <div className="absolute bottom-0 left-0 right-0" style={{ height: "0.4vh", background: "linear-gradient(90deg, transparent, #4F7FFF, #7C6BF0, transparent)" }} />

      <div className="absolute bottom-0 left-0 right-0 flex items-end justify-between" style={{ padding: "0 6vw 2.8vh" }}>
        <span style={{ color: "#8892B0", fontSize: "1vw", opacity: 0.6 }}>Vertrouwelijk — 123inkt</span>
        <span style={{ color: "#8892B0", fontSize: "1vw", opacity: 0.6 }}>9 / 9</span>
      </div>
    </div>
  );
}
