export default function Slide4EenmaligeKosten() {
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
          Eenmalige kosten van €80.500 dekken scraping-configuratie, data-ontsluiting en modelsetup
        </h2>
      </div>

      {/* Table */}
      <div className="absolute" style={{ top: "31vh", left: "6vw", right: "6vw" }}>

        {/* Header row */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "3fr 4fr 1.5fr",
          padding: "1.2vh 2vw",
          background: "#141828",
          borderRadius: "0.4vw 0.4vw 0 0",
          borderBottom: "1px solid rgba(79,127,255,0.3)"
        }}>
          <span style={{ fontSize: "1.3vw", fontWeight: 700, color: "#8892B0", letterSpacing: "0.05em", textTransform: "uppercase" }}>Kostenpost</span>
          <span style={{ fontSize: "1.3vw", fontWeight: 700, color: "#8892B0", letterSpacing: "0.05em", textTransform: "uppercase" }}>Omschrijving</span>
          <span style={{ fontSize: "1.3vw", fontWeight: 700, color: "#8892B0", letterSpacing: "0.05em", textTransform: "uppercase", textAlign: "right" }}>Bedrag</span>
        </div>

        {/* Row 1 */}
        <div style={{ display: "grid", gridTemplateColumns: "3fr 4fr 1.5fr", padding: "1.5vh 2vw", background: "#0F1422", borderBottom: "1px solid rgba(79,127,255,0.1)" }}>
          <span style={{ fontSize: "1.7vw", color: "#F0F4FF" }}>Data-ontsluiting & ETL</span>
          <span style={{ fontSize: "1.6vw", color: "#8892B0" }}>2 FTE × 4 weken × €1.250/dag</span>
          <span style={{ fontSize: "1.7vw", color: "#F0F4FF", textAlign: "right", fontWeight: 700 }}>€40.000</span>
        </div>

        {/* Row 2 */}
        <div style={{ display: "grid", gridTemplateColumns: "3fr 4fr 1.5fr", padding: "1.5vh 2vw", background: "#0C0F1A", borderBottom: "1px solid rgba(79,127,255,0.1)" }}>
          <span style={{ fontSize: "1.7vw", color: "#F0F4FF" }}>Projectmanagement & QA</span>
          <span style={{ fontSize: "1.6vw", color: "#8892B0" }}>1 FTE × 3 weken kick-off & acceptatie</span>
          <span style={{ fontSize: "1.7vw", color: "#F0F4FF", textAlign: "right", fontWeight: 700 }}>€15.000</span>
        </div>

        {/* Row 3 */}
        <div style={{ display: "grid", gridTemplateColumns: "3fr 4fr 1.5fr", padding: "1.5vh 2vw", background: "#0F1422", borderBottom: "1px solid rgba(79,127,255,0.1)" }}>
          <span style={{ fontSize: "1.7vw", color: "#F0F4FF" }}>Scraping-configuratie & validatie</span>
          <span style={{ fontSize: "1.6vw", color: "#8892B0" }}>CSS-selectors instellen, proxy-config & data-validatie</span>
          <span style={{ fontSize: "1.7vw", color: "#F0F4FF", textAlign: "right", fontWeight: 700 }}>€5.000</span>
        </div>

        {/* Row 4 */}
        <div style={{ display: "grid", gridTemplateColumns: "3fr 4fr 1.5fr", padding: "1.5vh 2vw", background: "#0C0F1A", borderBottom: "1px solid rgba(79,127,255,0.1)" }}>
          <span style={{ fontSize: "1.7vw", color: "#F0F4FF" }}>ML-model fijnafstelling</span>
          <span style={{ fontSize: "1.6vw", color: "#8892B0" }}>Hyperparameter tuning op productiedata</span>
          <span style={{ fontSize: "1.7vw", color: "#F0F4FF", textAlign: "right", fontWeight: 700 }}>€12.500</span>
        </div>

        {/* Row 5 */}
        <div style={{ display: "grid", gridTemplateColumns: "3fr 4fr 1.5fr", padding: "1.5vh 2vw", background: "#0F1422", borderBottom: "1px solid rgba(79,127,255,0.3)" }}>
          <span style={{ fontSize: "1.7vw", color: "#F0F4FF" }}>Cloud infra setup (AWS)</span>
          <span style={{ fontSize: "1.6vw", color: "#8892B0" }}>VPC, RDS, ECS cluster — eenmalige inrichting</span>
          <span style={{ fontSize: "1.7vw", color: "#F0F4FF", textAlign: "right", fontWeight: 700 }}>€8.000</span>
        </div>

        {/* Total row */}
        <div style={{ display: "grid", gridTemplateColumns: "3fr 4fr 1.5fr", padding: "1.8vh 2vw", background: "#141828", borderRadius: "0 0 0.4vw 0.4vw" }}>
          <span style={{ fontSize: "1.9vw", color: "#F0F4FF", fontWeight: 700 }}>Totaal eenmalig</span>
          <span style={{ fontSize: "1.6vw", color: "#8892B0" }}>Inclusief contingentie 0%</span>
          <span style={{ fontSize: "2vw", color: "#4F7FFF", textAlign: "right", fontWeight: 700 }}>€80.500</span>
        </div>

        <div style={{ fontSize: "1.2vw", color: "#8892B0", marginTop: "1.5vh", opacity: 0.7 }}>
          Bron: externe offertes & interne tariefkaart FTE — ingangsdatum Q3 2026
        </div>
      </div>

      <div className="absolute bottom-0 left-0 right-0" style={{ height: "0.15vh", background: "rgba(79,127,255,0.2)" }} />
      <div className="absolute bottom-0 left-0 right-0 flex items-end justify-between" style={{ padding: "0 6vw 2.5vh" }}>
        <span style={{ color: "#8892B0", fontSize: "1vw", opacity: 0.6 }}>Vertrouwelijk — 123inkt</span>
        <span style={{ color: "#8892B0", fontSize: "1vw", opacity: 0.6 }}>4 / 9</span>
      </div>
    </div>
  );
}
