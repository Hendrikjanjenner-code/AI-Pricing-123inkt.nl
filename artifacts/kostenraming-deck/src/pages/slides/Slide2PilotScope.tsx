export default function Slide2PilotScope() {
  return (
    <div className="relative w-screen h-screen overflow-hidden" style={{ background: "#0C0F1A", fontFamily: "Inter, system-ui, sans-serif" }}>

      {/* Subtle grid */}
      <div className="absolute inset-0" style={{
        backgroundImage: "linear-gradient(rgba(79,127,255,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(79,127,255,0.04) 1px, transparent 1px)",
        backgroundSize: "6vw 6vw"
      }} />

      {/* Top logo */}
      <div className="absolute top-0 left-0 right-0 flex items-center justify-between" style={{ padding: "3vh 6vw" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.7vw" }}>
          <div style={{
            width: "1.6vw", height: "1.6vw", borderRadius: "0.3vw",
            background: "linear-gradient(135deg, #4F7FFF, #7C6BF0)"
          }} />
          <span style={{ color: "#8892B0", fontSize: "1vw", fontWeight: 400 }}>123inkt</span>
        </div>
        <span style={{ color: "#8892B0", fontSize: "0.95vw" }}>Vertrouwelijk — Directie</span>
      </div>

      {/* Action title */}
      <div className="absolute" style={{ top: "12vh", left: "6vw", right: "6vw" }}>
        <div style={{ width: "3.5vw", height: "0.35vh", background: "#4F7FFF", marginBottom: "1.8vh" }} />
        <h2 style={{
          fontSize: "3.2vw",
          fontWeight: 700,
          color: "#F0F4FF",
          lineHeight: 1.2,
          textWrap: "balance",
          maxWidth: "78vw"
        }}>
          De pilot omvat 500 SKU's over 12 weken, verdeeld over drie productcategorieën
        </h2>
      </div>

      {/* Three columns */}
      <div className="absolute" style={{ top: "32vh", left: "6vw", right: "6vw", display: "flex", gap: "3vw" }}>

        <div style={{ flex: 1, background: "#141828", border: "1px solid rgba(79,127,255,0.15)", borderRadius: "0.5vw", padding: "3.5vh 2.5vw" }}>
          <div style={{ fontSize: "1vw", fontWeight: 700, color: "#4F7FFF", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: "2vh" }}>Pilotscope</div>
          <div style={{ fontSize: "2.8vw", fontWeight: 700, color: "#F0F4FF", lineHeight: 1, marginBottom: "1.5vh" }}>500 SKU's</div>
          <div style={{ fontSize: "2.6vw", fontWeight: 700, color: "#8892B0", lineHeight: 1, marginBottom: "2.5vh" }}>3 categorieën</div>
          <div style={{ fontSize: "1.6vw", color: "#8892B0", lineHeight: 1.5 }}>
            Inkten & toners (200),
            papier (150) en
            kantoorartikelen (150)
          </div>
        </div>

        <div style={{ flex: 1, background: "#141828", border: "1px solid rgba(79,127,255,0.15)", borderRadius: "0.5vw", padding: "3.5vh 2.5vw" }}>
          <div style={{ fontSize: "1vw", fontWeight: 700, color: "#4F7FFF", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: "2vh" }}>Doelstelling</div>
          <div style={{ fontSize: "1.9vw", color: "#F0F4FF", lineHeight: 1.5, marginBottom: "1.5vh" }}>
            Valideer dat het AI-model op productiedata meetbare margeverbeteringen realiseert.
          </div>
          <div style={{ fontSize: "1.7vw", color: "#8892B0", lineHeight: 1.5 }}>
            Minimale drempel: +2% bruto marge op pilotSKU's t.o.v. baseline.
          </div>
        </div>

        <div style={{ flex: 1, background: "#141828", border: "1px solid rgba(79,127,255,0.15)", borderRadius: "0.5vw", padding: "3.5vh 2.5vw" }}>
          <div style={{ fontSize: "1vw", fontWeight: 700, color: "#4F7FFF", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: "2vh" }}>Succescriteria</div>
          <div style={{ fontSize: "1.9vw", color: "#F0F4FF", lineHeight: 1.6 }}>
            +2% margeverbete­ring
          </div>
          <div style={{ fontSize: "1.9vw", color: "#F0F4FF", lineHeight: 1.6 }}>
            95% aanbevelingen op tijd
          </div>
          <div style={{ fontSize: "1.9vw", color: "#F0F4FF", lineHeight: 1.6 }}>
            Nul prijs­fouten door safety rules
          </div>
          <div style={{ fontSize: "1.9vw", color: "#F0F4FF", lineHeight: 1.6 }}>
            Go/no-go besluit week 12
          </div>
        </div>
      </div>

      {/* Footer divider */}
      <div className="absolute bottom-0 left-0 right-0" style={{ height: "0.15vh", background: "rgba(79,127,255,0.2)" }} />
      <div className="absolute bottom-0 left-0 right-0 flex items-end justify-between" style={{ padding: "0 6vw 2.5vh" }}>
        <span style={{ color: "#8892B0", fontSize: "1vw", opacity: 0.6 }}>Vertrouwelijk — 123inkt</span>
        <span style={{ color: "#8892B0", fontSize: "1vw", opacity: 0.6 }}>2 / 9</span>
      </div>
    </div>
  );
}
