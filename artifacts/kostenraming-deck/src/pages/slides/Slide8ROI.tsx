export default function Slide8ROI() {
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
          Volledige uitrol levert naar verwachting meer dan €2,7M extra bruto marge per jaar
        </h2>
      </div>

      {/* Two columns */}
      <div className="absolute" style={{ top: "31vh", left: "6vw", right: "6vw", display: "flex", gap: "4vw" }}>

        {/* Left: cost vs. benefit breakdown */}
        <div style={{ flex: 1 }}>

          <div style={{ fontSize: "1.2vw", fontWeight: 700, color: "#8892B0", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: "2vh" }}>Investering (jaar 1)</div>

          <div style={{ marginBottom: "1.5vh" }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.5vh" }}>
              <span style={{ fontSize: "1.7vw", color: "#8892B0" }}>Eenmalige pilotkosten</span>
              <span style={{ fontSize: "1.7vw", color: "#F0F4FF", fontWeight: 700 }}>€850</span>
            </div>
            <div style={{ height: "0.6vh", background: "#141828", borderRadius: "0.3vh", overflow: "hidden" }}>
              <div style={{ width: "2%", height: "100%", background: "#4F7FFF" }} />
            </div>
          </div>

          <div style={{ marginBottom: "3vh" }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.5vh" }}>
              <span style={{ fontSize: "1.7vw", color: "#8892B0" }}>Doorlopende kosten (12 mnd)</span>
              <span style={{ fontSize: "1.7vw", color: "#F0F4FF", fontWeight: 700 }}>€54.000</span>
            </div>
            <div style={{ height: "0.6vh", background: "#141828", borderRadius: "0.3vh", overflow: "hidden" }}>
              <div style={{ width: "98%", height: "100%", background: "#7C6BF0" }} />
            </div>
          </div>

          <div style={{ display: "flex", justifyContent: "space-between", padding: "1.5vh 0", borderTop: "1px solid rgba(79,127,255,0.3)", marginBottom: "3.5vh" }}>
            <span style={{ fontSize: "1.9vw", color: "#F0F4FF", fontWeight: 700 }}>Totaal jaar 1</span>
            <span style={{ fontSize: "2vw", color: "#4F7FFF", fontWeight: 700 }}>€54.850</span>
          </div>

          <div style={{ fontSize: "1.2vw", fontWeight: 700, color: "#8892B0", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: "2vh" }}>Verwachte jaarlijkse baten (uitrol)</div>

          <div style={{ marginBottom: "1.5vh" }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.5vh" }}>
              <span style={{ fontSize: "1.7vw", color: "#8892B0" }}>Bruto marge-uplift +4.2%¹</span>
              <span style={{ fontSize: "1.7vw", color: "#22C55E", fontWeight: 700 }}>€2.520.000</span>
            </div>
            <div style={{ height: "0.6vh", background: "#141828", borderRadius: "0.3vh", overflow: "hidden" }}>
              <div style={{ width: "100%", height: "100%", background: "#22C55E" }} />
            </div>
          </div>

          <div style={{ marginBottom: "3vh" }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.5vh" }}>
              <span style={{ fontSize: "1.7vw", color: "#8892B0" }}>FTE-besparing pricing team²</span>
              <span style={{ fontSize: "1.7vw", color: "#22C55E", fontWeight: 700 }}>€195.000</span>
            </div>
            <div style={{ height: "0.6vh", background: "#141828", borderRadius: "0.3vh", overflow: "hidden" }}>
              <div style={{ width: "7.8%", height: "100%", background: "#22C55E", opacity: 0.7 }} />
            </div>
          </div>

          <div style={{ display: "flex", justifyContent: "space-between", padding: "1.5vh 0", borderTop: "1px solid rgba(34,197,94,0.3)" }}>
            <span style={{ fontSize: "1.9vw", color: "#F0F4FF", fontWeight: 700 }}>Totaal baten/jaar</span>
            <span style={{ fontSize: "2vw", color: "#22C55E", fontWeight: 700 }}>€2.715.000</span>
          </div>
        </div>

        {/* Right: summary metrics */}
        <div style={{ width: "30vw", display: "flex", flexDirection: "column", gap: "2vh" }}>

          <div style={{ background: "rgba(34,197,94,0.08)", border: "1px solid rgba(34,197,94,0.25)", borderRadius: "0.5vw", padding: "3vh 2.5vw" }}>
            <div style={{ fontSize: "1vw", fontWeight: 700, color: "#22C55E", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: "1.5vh" }}>Terugverdientijd</div>
            <div style={{ fontSize: "5vw", fontWeight: 700, color: "#22C55E", lineHeight: 1 }}>&lt; 1</div>
            <div style={{ fontSize: "1.5vw", color: "#8892B0", marginTop: "0.5vh" }}>maand na volledige uitrol</div>
          </div>

          <div style={{ background: "#141828", border: "1px solid rgba(79,127,255,0.2)", borderRadius: "0.5vw", padding: "2.5vh 2.5vw" }}>
            <div style={{ fontSize: "1vw", fontWeight: 700, color: "#4F7FFF", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: "1vh" }}>ROI jaar 1 (post-uitrol)</div>
            <div style={{ fontSize: "3.8vw", fontWeight: 700, color: "#4F7FFF", lineHeight: 1 }}>49×</div>
            <div style={{ fontSize: "1.4vw", color: "#8892B0", marginTop: "0.5vh" }}>op totale jaarkosten €54.850</div>
          </div>

          <div style={{ background: "#141828", border: "1px solid rgba(79,127,255,0.15)", borderRadius: "0.5vw", padding: "2vh 2vw" }}>
            <div style={{ fontSize: "1.4vw", color: "#8892B0", lineHeight: 1.6 }}>
              ¹ 4,2% uplift op €60M inktomzet/jaar — aanname op basis van A/B-test in dev (26 SKU's)
            </div>
            <div style={{ fontSize: "1.4vw", color: "#8892B0", lineHeight: 1.6, marginTop: "0.8vh" }}>
              ² 3 FTE × €65.000 pricing analysts gedeeltelijk vrijgespeeld
            </div>
          </div>
        </div>
      </div>

      <div className="absolute bottom-0 left-0 right-0" style={{ height: "0.15vh", background: "rgba(79,127,255,0.2)" }} />
      <div className="absolute bottom-0 left-0 right-0 flex items-end justify-between" style={{ padding: "0 6vw 2.5vh" }}>
        <span style={{ color: "#8892B0", fontSize: "1vw", opacity: 0.6 }}>Vertrouwelijk — 123inkt</span>
        <span style={{ color: "#8892B0", fontSize: "1vw", opacity: 0.6 }}>8 / 9</span>
      </div>
    </div>
  );
}
