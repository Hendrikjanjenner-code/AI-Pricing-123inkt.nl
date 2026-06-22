export default function Slide3KostenOverzicht() {
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
          De totale pilotinvestering bedraagt €850 eenmalig en €4.500 per maand
        </h2>
      </div>

      {/* Two-column layout: summary left, chart right */}
      <div className="absolute" style={{ top: "32vh", left: "6vw", right: "6vw", display: "flex", gap: "4vw", alignItems: "flex-start" }}>

        {/* Left: summary numbers */}
        <div style={{ width: "28vw" }}>
          <div style={{ background: "#141828", border: "1px solid rgba(79,127,255,0.2)", borderRadius: "0.5vw", padding: "3vh 2.5vw", marginBottom: "2.5vh" }}>
            <div style={{ fontSize: "1vw", fontWeight: 700, color: "#4F7FFF", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: "1.5vh" }}>Eenmalige kosten (pilot)</div>
            <div style={{ fontSize: "3.8vw", fontWeight: 700, color: "#F0F4FF", lineHeight: 1 }}>€850</div>
            <div style={{ fontSize: "1.5vw", color: "#8892B0", marginTop: "1vh" }}>Data-onboarding, kalibratie & training</div>
          </div>
          <div style={{ background: "#141828", border: "1px solid rgba(124,107,240,0.2)", borderRadius: "0.5vw", padding: "3vh 2.5vw", marginBottom: "2.5vh" }}>
            <div style={{ fontSize: "1vw", fontWeight: 700, color: "#7C6BF0", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: "1.5vh" }}>Doorlopende kosten</div>
            <div style={{ fontSize: "3.8vw", fontWeight: 700, color: "#F0F4FF", lineHeight: 1 }}>€4.500<span style={{ fontSize: "1.8vw", color: "#8892B0" }}>/mnd</span></div>
            <div style={{ fontSize: "1.5vw", color: "#8892B0", marginTop: "1vh" }}>Infra, licenties & beheer</div>
          </div>
          <div style={{ background: "rgba(79,127,255,0.08)", border: "1px solid rgba(79,127,255,0.25)", borderRadius: "0.5vw", padding: "2.5vh 2.5vw" }}>
            <div style={{ fontSize: "1vw", fontWeight: 700, color: "#4F7FFF", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: "1vh" }}>Totaal 12-weekse pilot</div>
            <div style={{ fontSize: "3.2vw", fontWeight: 700, color: "#4F7FFF", lineHeight: 1 }}>€14.350</div>
            <div style={{ fontSize: "1.5vw", color: "#8892B0", marginTop: "0.8vh" }}>Eenmalig + 3× maandkosten</div>
          </div>
        </div>

        {/* Right: SVG horizontal bar chart */}
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: "1.2vw", fontWeight: 700, color: "#8892B0", marginBottom: "2.5vh", letterSpacing: "0.05em", textTransform: "uppercase" }}>Uitsplitsing eenmalige kosten</div>

          {/* Bar: Model-kalibratie — 47.1% */}
          <div style={{ marginBottom: "2.2vh" }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.6vh" }}>
              <span style={{ fontSize: "1.7vw", color: "#F0F4FF" }}>Model-kalibratie & acceptatietest</span>
              <span style={{ fontSize: "1.7vw", color: "#4F7FFF", fontWeight: 700 }}>€400</span>
            </div>
            <div style={{ height: "0.8vh", background: "#141828", borderRadius: "0.4vh", overflow: "hidden" }}>
              <div style={{ width: "47.1%", height: "100%", background: "#4F7FFF", borderRadius: "0.4vh" }} />
            </div>
          </div>

          {/* Bar: Data-onboarding — 29.4% */}
          <div style={{ marginBottom: "2.2vh" }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.6vh" }}>
              <span style={{ fontSize: "1.7vw", color: "#F0F4FF" }}>Data-onboarding via CSV-uploadportal</span>
              <span style={{ fontSize: "1.7vw", color: "#4F7FFF", fontWeight: 700 }}>€250</span>
            </div>
            <div style={{ height: "0.8vh", background: "#141828", borderRadius: "0.4vh", overflow: "hidden" }}>
              <div style={{ width: "29.4%", height: "100%", background: "#4F7FFF", borderRadius: "0.4vh" }} />
            </div>
          </div>

          {/* Bar: Gebruikerstraining — 23.5% */}
          <div style={{ marginBottom: "2.2vh" }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.6vh" }}>
              <span style={{ fontSize: "1.7vw", color: "#F0F4FF" }}>Gebruikerstraining & documentatie</span>
              <span style={{ fontSize: "1.7vw", color: "#7C6BF0", fontWeight: 700 }}>€200</span>
            </div>
            <div style={{ height: "0.8vh", background: "#141828", borderRadius: "0.4vh", overflow: "hidden" }}>
              <div style={{ width: "23.5%", height: "100%", background: "#7C6BF0", borderRadius: "0.4vh" }} />
            </div>
          </div>
        </div>
      </div>

      <div className="absolute bottom-0 left-0 right-0" style={{ height: "0.15vh", background: "rgba(79,127,255,0.2)" }} />
      <div className="absolute bottom-0 left-0 right-0 flex items-end justify-between" style={{ padding: "0 6vw 2.5vh" }}>
        <span style={{ color: "#8892B0", fontSize: "1vw", opacity: 0.6 }}>Vertrouwelijk — 123inkt</span>
        <span style={{ color: "#8892B0", fontSize: "1vw", opacity: 0.6 }}>3 / 9</span>
      </div>
    </div>
  );
}
