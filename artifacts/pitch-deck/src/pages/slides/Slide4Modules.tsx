export default function Slide4Modules() {
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
        top: "-10vw", left: "-10vw"
      }} />

      {/* Slide label */}
      <div className="absolute" style={{ top: "4vh", left: "5vw", color: "#4F7FFF", fontSize: "0.9vw", fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase" }}>03 — Platform Modules</div>

      {/* Bottom line */}
      <div className="absolute bottom-0 left-0 right-0" style={{ height: "0.3vh", background: "linear-gradient(90deg, transparent, #4F7FFF, #7C6BF0, transparent)" }} />

      <div className="absolute inset-0 flex flex-col" style={{ padding: "9vh 5vw 8vh 5vw" }}>

        <h2 style={{ fontSize: "3.6vw", fontWeight: 800, color: "#F0F4FF", marginBottom: "4.5vh", letterSpacing: "-0.02em", lineHeight: 1.1 }}>
          Tien geintegreerde modules
        </h2>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr 1fr", gap: "1.2vw", flex: 1 }}>

          <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(79,127,255,0.2)", borderRadius: "0.8vw", padding: "2.2vh 1.4vw" }}>
            <div style={{ fontSize: "1.6vw", marginBottom: "1.2vh" }}>
              <svg width="1.6vw" height="1.6vw" viewBox="0 0 24 24" fill="none"><path d="M3 12h4l3-9 4 18 3-9h4" stroke="#4F7FFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
            </div>
            <div style={{ fontSize: "0.95vw", fontWeight: 700, color: "#F0F4FF", marginBottom: "0.6vh" }}>Dashboard</div>
            <div style={{ fontSize: "0.8vw", color: "#8892B0", lineHeight: 1.5 }}>KPI-overzicht, margegrafieken, real-time status</div>
          </div>

          <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(124,107,240,0.2)", borderRadius: "0.8vw", padding: "2.2vh 1.4vw" }}>
            <div style={{ fontSize: "1.6vw", marginBottom: "1.2vh" }}>
              <svg width="1.6vw" height="1.6vw" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" stroke="#7C6BF0" strokeWidth="2"/><path d="M9 12l2 2 4-4" stroke="#7C6BF0" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
            </div>
            <div style={{ fontSize: "0.95vw", fontWeight: 700, color: "#F0F4FF", marginBottom: "0.6vh" }}>Aanbevelingen</div>
            <div style={{ fontSize: "0.8vw", color: "#8892B0", lineHeight: 1.5 }}>Filteren, bulk-goedkeuren, detail-view per SKU</div>
          </div>

          <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(79,127,255,0.2)", borderRadius: "0.8vw", padding: "2.2vh 1.4vw" }}>
            <div style={{ fontSize: "1.6vw", marginBottom: "1.2vh" }}>
              <svg width="1.6vw" height="1.6vw" viewBox="0 0 24 24" fill="none"><rect x="3" y="3" width="18" height="18" rx="2" stroke="#4F7FFF" strokeWidth="2"/><path d="M8 12h8M12 8v8" stroke="#4F7FFF" strokeWidth="2" strokeLinecap="round"/></svg>
            </div>
            <div style={{ fontSize: "0.95vw", fontWeight: 700, color: "#F0F4FF", marginBottom: "0.6vh" }}>SKU-beheer</div>
            <div style={{ fontSize: "0.8vw", color: "#8892B0", lineHeight: 1.5 }}>Productcatalogus, prijshistorie, deep-dive analyse</div>
          </div>

          <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(124,107,240,0.2)", borderRadius: "0.8vw", padding: "2.2vh 1.4vw" }}>
            <div style={{ fontSize: "1.6vw", marginBottom: "1.2vh" }}>
              <svg width="1.6vw" height="1.6vw" viewBox="0 0 24 24" fill="none"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="#7C6BF0" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
            </div>
            <div style={{ fontSize: "0.95vw", fontWeight: 700, color: "#F0F4FF", marginBottom: "0.6vh" }}>Categoriestrategie</div>
            <div style={{ fontSize: "0.8vw", color: "#8892B0", lineHeight: 1.5 }}>8 strategieen configureerbaar per categorie</div>
          </div>

          <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(79,127,255,0.2)", borderRadius: "0.8vw", padding: "2.2vh 1.4vw" }}>
            <div style={{ fontSize: "1.6vw", marginBottom: "1.2vh" }}>
              <svg width="1.6vw" height="1.6vw" viewBox="0 0 24 24" fill="none"><path d="M17 20H7a2 2 0 01-2-2V6a2 2 0 012-2h7l5 5v9a2 2 0 01-2 2z" stroke="#4F7FFF" strokeWidth="2"/><path d="M17 9h-5V4" stroke="#4F7FFF" strokeWidth="2"/></svg>
            </div>
            <div style={{ fontSize: "0.95vw", fontWeight: 700, color: "#F0F4FF", marginBottom: "0.6vh" }}>Data-upload</div>
            <div style={{ fontSize: "0.8vw", color: "#8892B0", lineHeight: 1.5 }}>8 CSV-types, validatie, importhistorie</div>
          </div>

          <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(124,107,240,0.2)", borderRadius: "0.8vw", padding: "2.2vh 1.4vw" }}>
            <div style={{ fontSize: "1.6vw", marginBottom: "1.2vh" }}>
              <svg width="1.6vw" height="1.6vw" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" stroke="#7C6BF0" strokeWidth="2"/><path d="M12 7v5" stroke="#7C6BF0" strokeWidth="2" strokeLinecap="round"/><circle cx="12" cy="16" r="1" fill="#7C6BF0"/></svg>
            </div>
            <div style={{ fontSize: "0.95vw", fontWeight: 700, color: "#F0F4FF", marginBottom: "0.6vh" }}>Datakwaliteit</div>
            <div style={{ fontSize: "0.8vw", color: "#8892B0", lineHeight: 1.5 }}>Kwaliteitsscore, issues-overzicht, alerts</div>
          </div>

          <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(79,127,255,0.2)", borderRadius: "0.8vw", padding: "2.2vh 1.4vw" }}>
            <div style={{ fontSize: "1.6vw", marginBottom: "1.2vh" }}>
              <svg width="1.6vw" height="1.6vw" viewBox="0 0 24 24" fill="none"><path d="M21 21l-6-6m2-5A7 7 0 113 10a7 7 0 0114 0z" stroke="#4F7FFF" strokeWidth="2" strokeLinecap="round"/></svg>
            </div>
            <div style={{ fontSize: "0.95vw", fontWeight: 700, color: "#F0F4FF", marginBottom: "0.6vh" }}>Concurrentie</div>
            <div style={{ fontSize: "0.8vw", color: "#8892B0", lineHeight: 1.5 }}>PCIS-scores, prijsindex, concurrentanalyse</div>
          </div>

          <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(124,107,240,0.2)", borderRadius: "0.8vw", padding: "2.2vh 1.4vw" }}>
            <div style={{ fontSize: "1.6vw", marginBottom: "1.2vh" }}>
              <svg width="1.6vw" height="1.6vw" viewBox="0 0 24 24" fill="none"><path d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" stroke="#7C6BF0" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
            </div>
            <div style={{ fontSize: "0.95vw", fontWeight: 700, color: "#F0F4FF", marginBottom: "0.6vh" }}>A/B-testen</div>
            <div style={{ fontSize: "0.8vw", color: "#8892B0", lineHeight: 1.5 }}>AI vs. controle, statistische significantie</div>
          </div>

          <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(79,127,255,0.2)", borderRadius: "0.8vw", padding: "2.2vh 1.4vw" }}>
            <div style={{ fontSize: "1.6vw", marginBottom: "1.2vh" }}>
              <svg width="1.6vw" height="1.6vw" viewBox="0 0 24 24" fill="none"><rect x="2" y="3" width="20" height="14" rx="2" stroke="#4F7FFF" strokeWidth="2"/><path d="M8 21h8M12 17v4" stroke="#4F7FFF" strokeWidth="2" strokeLinecap="round"/></svg>
            </div>
            <div style={{ fontSize: "0.95vw", fontWeight: 700, color: "#F0F4FF", marginBottom: "0.6vh" }}>Modelgezondheid</div>
            <div style={{ fontSize: "0.8vw", color: "#8892B0", lineHeight: 1.5 }}>Laatste run, nieuwe run triggeren, accuracy</div>
          </div>

          <div style={{ background: "rgba(79,127,255,0.1)", border: "1px solid rgba(79,127,255,0.35)", borderRadius: "0.8vw", padding: "2.2vh 1.4vw" }}>
            <div style={{ fontSize: "1.6vw", marginBottom: "1.2vh" }}>
              <svg width="1.6vw" height="1.6vw" viewBox="0 0 24 24" fill="none"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" stroke="#4F7FFF" strokeWidth="2" strokeLinejoin="round"/></svg>
            </div>
            <div style={{ fontSize: "0.95vw", fontWeight: 700, color: "#4F7FFF", marginBottom: "0.6vh" }}>Explainability</div>
            <div style={{ fontSize: "0.8vw", color: "#8892B0", lineHeight: 1.5 }}>Uitleg per aanbeveling, factoren, audittrail</div>
          </div>
        </div>
      </div>
    </div>
  );
}
