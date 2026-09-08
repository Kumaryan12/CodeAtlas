import { ApiStatus } from "@/components/api-status";

export default function Workspace() {
  return <div className="app-shell">
    <header className="topbar">
      <a href="/" className="brand"><span className="brand-mark">⌘</span>CodeAtlas</a>
      <span className="divider">/</span><span className="text-sm text-zinc-400">Personal workspace</span>
      <span className="milestone">MILESTONE 0</span>
    </header>
    <div className="body-grid">
      <aside className="sidebar">
        <p className="eyebrow">WORKSPACE</p>
        <div className="nav-current"><span>▣</span> Repositories <span className="count">0</span></div>
        <div className="sidebar-note"><span className="small-mark">⌘</span><p>Your code.<br/>The bigger picture.</p><small>Codebase intelligence starts<br/>with understanding the source.</small></div>
        <ApiStatus />
      </aside>
      <main id="main-content">
        <div className="page-heading"><div><p className="eyebrow">YOUR ENGINEERING WORKSPACE</p><h1>Repositories</h1><p className="muted">A map for every codebase. A starting point for every question.</p></div><span className="badge">Foundation preview</span></div>
        <section className="empty-state" aria-labelledby="empty-title">
          <div className="map-art" aria-hidden="true"><span className="map-node left">{ "{ }" }</span><span className="map-line"/><span className="map-node center">⌘</span><span className="map-line"/><span className="map-node right">{ "</>" }</span></div>
          <p className="eyebrow accent">EVERY CONNECTION STARTS SOMEWHERE</p>
          <h2 id="empty-title">Get to know your codebase.</h2>
          <p className="empty-copy">Explore the files, symbols, and relationships behind your software.<br className="desktop-break"/> Your first repository will live here.</p>
          <div className="coming-soon"><span>＋</span> Repository import arrives in Milestone 1</div>
          <p className="security-note">Read the source. Understand the system. Stay in control.</p>
        </section>
        <section className="roadmap" aria-label="Development roadmap">
          <article><span className="step">01 / NEXT</span><h3>Explore the source</h3><p>Import a public repository, browse its files, and inspect extracted symbols.</p></article>
          <article><span className="step">02 / PLANNED</span><h3>Connect the dots</h3><p>Trace imports and discover how modules fit together in an architecture graph.</p></article>
          <article><span className="step">03 / PLANNED</span><h3>Ask with context</h3><p>Get answers grounded in your code, with references to the exact source.</p></article>
        </section>
        <footer><span><span className="dot online"/> Workspace foundation ready</span><span>No repositories indexed</span></footer>
      </main>
    </div>
  </div>;
}
