import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { IS_DEMO } from "../../lib/ctx";
import { initials } from "../../lib/format";
import { Logo } from "../../ui/kit";

export default function PublicLayout({ company, slug, children }: { company?: string; slug?: string; children: ReactNode }) {
  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      {IS_DEMO && <div className="demo-band">Vue candidat (démo) · <Link to="/">revenir à l'espace entreprise</Link></div>}
      <header className="public-head">
        <div>
          {company ? <span className="row" style={{ color: "var(--ink)", gap: 12 }}><span className="logo-co">{initials(company)}</span><span className="strong" style={{ fontSize: 16 }}>{company}</span></span> : <span />}
        </div>
      </header>
      <main className="public-main" style={{ flex: 1 }}>{children}</main>
      <footer className="public-foot">
        {slug && <><Link to={`/confidentialite/${slug}`}>Vos données personnelles</Link> · </>}
        <span className="row" style={{ display: "inline-flex", gap: 6 }}>Recrutement avec <Logo size={16} /> WayLoop</span>
      </footer>
    </div>
  );
}
