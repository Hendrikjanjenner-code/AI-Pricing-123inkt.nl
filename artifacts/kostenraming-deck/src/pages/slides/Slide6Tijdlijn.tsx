export default function Slide6Tijdlijn() {
  return (
    <div className="relative w-screen h-screen overflow-hidden" style={{ background: "#0C0F1A", fontFamily: "Inter, system-ui, sans-serif" }}>

      <div className="absolute inset-0" style={{
        backgroundImage: "linear-gradient(rgba(79,127,255,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(79,127,255,0.04) 1px, transparent 1px)",
        backgroundSize: "6vw 6vw"
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
        <h2 style={{ fontSize: "3.2vw", fontWeight: 700, color: "#F0F4FF", lineHeight: 1.2, textWrap: "balance", maxWidth: "78vw" }}>
          De pilot doorloopt drie fasen van week 1 tot week 12 — go/no-go na fase 3
        </h2>
      </div>

      {/* Timeline bar */}
      <div className="absolute" style={{ top: "31vh", left: "6vw", right: "6vw" }}>

        {/* Week markers */}
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.8vh" }}>
          <span style={{ fontSize: "1.2vw", color: "#8892B0" }}>Week 1</span>
          <span style={{ fontSize: "1.2vw", color: "#8892B0" }}>Week 4</span>
          <span style={{ fontSize: "1.2vw", color: "#8892B0" }}>Week 8</span>
          <span style={{ fontSize: "1.2vw", color: "#8892B0" }}>Week 12</span>
        </div>

        {/* Timeline track */}
        <div style={{ position: "relative", height: "1.5vh", background: "#141828", borderRadius: "0.75vh", overflow: "hidden", marginBottom: "4vh" }}>
          <div style={{ position: "absolute", left: 0, width: "33.3%", height: "100%", background: "#4F7FFF" }} />
          <div style={{ position: "absolute", left: "33.3%", width: "33.3%", height: "100%", background: "#7C6BF0" }} />
          <div style={{ position: "absolute", left: "66.6%", width: "33.4%", height: "100%", background: "linear-gradient(90deg, #4F7FFF, #7C6BF0)" }} />
        </div>

        {/* Three phase cards */}
        <div style={{ display: "flex", gap: "2vw" }}>

          <div style={{ flex: 1, background: "#141828", border: "1px solid rgba(79,127,255,0.25)", borderTop: "3px solid #4F7FFF", borderRadius: "0 0 0.5vw 0.5vw", padding: "2.5vh 2vw" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "1.5vh" }}>
              <span style={{ fontSize: "1.2vw", fontWeight: 700, color: "#4F7FFF", letterSpacing: "0.1em", textTransform: "uppercase" }}>Fase 1</span>
              <span style={{ fontSize: "1.2vw", color: "#8892B0" }}>Weken 1–4</span>
            </div>
            <div style={{ fontSize: "1.9vw", fontWeight: 700, color: "#F0F4FF", marginBottom: "1.5vh" }}>Setup & data-koppeling</div>
            <div style={{ fontSize: "1.6vw", color: "#8892B0", lineHeight: 1.55 }}>
              Productiedata aansluiten op pipeline
            </div>
            <div style={{ fontSize: "1.6vw", color: "#8892B0", lineHeight: 1.55 }}>
              AWS-omgeving inrichten
            </div>
            <div style={{ fontSize: "1.6vw", color: "#8892B0", lineHeight: 1.55 }}>
              Model fijnafstellen op historische data
            </div>
            <div style={{ fontSize: "1.6vw", color: "#8892B0", lineHeight: 1.55 }}>
              Acceptatietest safety rules
            </div>
            <div style={{ marginTop: "2vh", padding: "1vh 1.2vw", background: "rgba(79,127,255,0.1)", borderRadius: "0.3vw" }}>
              <span style={{ fontSize: "1.4vw", color: "#4F7FFF" }}>Mijlpaal: Go-live 500 SKU's</span>
            </div>
          </div>

          <div style={{ flex: 1, background: "#141828", border: "1px solid rgba(124,107,240,0.25)", borderTop: "3px solid #7C6BF0", borderRadius: "0 0 0.5vw 0.5vw", padding: "2.5vh 2vw" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "1.5vh" }}>
              <span style={{ fontSize: "1.2vw", fontWeight: 700, color: "#7C6BF0", letterSpacing: "0.1em", textTransform: "uppercase" }}>Fase 2</span>
              <span style={{ fontSize: "1.2vw", color: "#8892B0" }}>Weken 5–8</span>
            </div>
            <div style={{ fontSize: "1.9vw", fontWeight: 700, color: "#F0F4FF", marginBottom: "1.5vh" }}>Pilotdraaien & monitoren</div>
            <div style={{ fontSize: "1.6vw", color: "#8892B0", lineHeight: 1.55 }}>
              Dagelijkse aanbevelingscyclus actief
            </div>
            <div style={{ fontSize: "1.6vw", color: "#8892B0", lineHeight: 1.55 }}>
              Pricing-team beoordeelt handmatig
            </div>
            <div style={{ fontSize: "1.6vw", color: "#8892B0", lineHeight: 1.55 }}>
              Wekelijkse KPI-rapportage directie
            </div>
            <div style={{ fontSize: "1.6vw", color: "#8892B0", lineHeight: 1.55 }}>
              A/B-test baseline vs. AI vastleggen
            </div>
            <div style={{ marginTop: "2vh", padding: "1vh 1.2vw", background: "rgba(124,107,240,0.1)", borderRadius: "0.3vw" }}>
              <span style={{ fontSize: "1.4vw", color: "#7C6BF0" }}>Mijlpaal: eerste margemeting</span>
            </div>
          </div>

          <div style={{ flex: 1, background: "#141828", border: "1px solid rgba(79,127,255,0.25)", borderTop: "3px solid #4F7FFF", borderRadius: "0 0 0.5vw 0.5vw", padding: "2.5vh 2vw" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "1.5vh" }}>
              <span style={{ fontSize: "1.2vw", fontWeight: 700, color: "#4F7FFF", letterSpacing: "0.1em", textTransform: "uppercase" }}>Fase 3</span>
              <span style={{ fontSize: "1.2vw", color: "#8892B0" }}>Weken 9–12</span>
            </div>
            <div style={{ fontSize: "1.9vw", fontWeight: 700, color: "#F0F4FF", marginBottom: "1.5vh" }}>Evaluatie & beslissing</div>
            <div style={{ fontSize: "1.6vw", color: "#8892B0", lineHeight: 1.55 }}>
              Eindmeting marge-uplift & volume
            </div>
            <div style={{ fontSize: "1.6vw", color: "#8892B0", lineHeight: 1.55 }}>
              Technische post-mortem analyse
            </div>
            <div style={{ fontSize: "1.6vw", color: "#8892B0", lineHeight: 1.55 }}>
              Kostenprognose volledige uitrol
            </div>
            <div style={{ fontSize: "1.6vw", color: "#8892B0", lineHeight: 1.55 }}>
              Directiepresentatie resultaten
            </div>
            <div style={{ marginTop: "2vh", padding: "1vh 1.2vw", background: "rgba(79,127,255,0.1)", borderRadius: "0.3vw" }}>
              <span style={{ fontSize: "1.4vw", color: "#4F7FFF", fontWeight: 700 }}>Mijlpaal: go/no-go besluit</span>
            </div>
          </div>
        </div>
      </div>

      <div className="absolute bottom-0 left-0 right-0" style={{ height: "0.15vh", background: "rgba(79,127,255,0.2)" }} />
      <div className="absolute bottom-0 left-0 right-0 flex items-end justify-between" style={{ padding: "0 6vw 2.5vh" }}>
        <span style={{ color: "#8892B0", fontSize: "1vw", opacity: 0.6 }}>Vertrouwelijk — 123inkt</span>
        <span style={{ color: "#8892B0", fontSize: "1vw", opacity: 0.6 }}>6 / 9</span>
      </div>
    </div>
  );
}
