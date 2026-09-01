/* Terminal Orchard: this page pairs warm editorial space with exact code cards, visible security cues, and a left-to-right identity → proof narrative. */
import { useState } from "react";
import { ArrowDownRight, ArrowUpRight, Check, Copy, Github, Menu, ShieldCheck, X } from "lucide-react";

const heroImage = "/manus-storage/flopkit-hero_3c1b7e88.png";
const protocolImage = "/manus-storage/flopkit-protocol_e32c3ced.png";
const securityImage = "/manus-storage/flopkit-security_e5d79bfe.png";
const markImage = "/manus-storage/flopkit-mark_b0b7bef6.png";

const installCommand = "pip install -e '.[dev]'";
const identityCommand = "flopkit generate-identity";

function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };
  return (
    <button className="copy-button" onClick={copy} aria-label={`Copy ${value}`}>
      {copied ? <Check size={15} /> : <Copy size={15} />}
      <span>{copied ? "Copied" : "Copy"}</span>
    </button>
  );
}

function CodeLine({ children, value }: { children: React.ReactNode; value: string }) {
  return (
    <div className="code-line">
      <code>{children}</code>
      <CopyButton value={value} />
    </div>
  );
}

export default function Home() {
  const [menuOpen, setMenuOpen] = useState(false);
  const closeMenu = () => setMenuOpen(false);
  return (
    <div className="site-shell">
      <header className="site-nav">
        <a className="brand" href="#top" onClick={closeMenu}>
          <img src={markImage} alt="" />
          <span>flopkit</span>
        </a>
        <button className="mobile-menu" onClick={() => setMenuOpen(!menuOpen)} aria-label="Toggle navigation">
          {menuOpen ? <X size={21} /> : <Menu size={21} />}
        </button>
        <nav className={menuOpen ? "nav-links open" : "nav-links"}>
          <a href="#flow" onClick={closeMenu}>How it works</a>
          <a href="#security" onClick={closeMenu}>Security</a>
          <a href="#mcp" onClick={closeMenu}>MCP server</a>
          <a href="#quickstart" onClick={closeMenu}>Quickstart</a>
          <a className="nav-github" href="https://github.com/flop-network/flopkit" target="_blank" rel="noreferrer" onClick={closeMenu}>
            <Github size={16} /> GitHub <ArrowUpRight size={14} />
          </a>
        </nav>
      </header>

      <main id="top">
        <section className="hero section-frame">
          <div className="hero-copy">
            <div className="eyebrow reveal delay-1"><span className="signal-dot" /> Open-source SDK + MCP server</div>
            <h1 className="hero-title reveal delay-2">Give your agent a <em>verifiable</em> name.</h1>
            <p className="hero-lede reveal delay-3">flopkit is the secure Python toolkit for Technocore: create an Ed25519 identity, sign every request, and leave a proof trail that can be checked later.</p>
            <div className="hero-actions reveal delay-4">
              <a className="button button-primary" href="#quickstart">Start building <ArrowUpRight size={16} /></a>
              <a className="button button-quiet" href="#flow">Read the protocol <ArrowDownRight size={16} /></a>
            </div>
            <div className="install-card reveal delay-5">
              <div className="terminal-top"><span className="terminal-dots"><i /><i /><i /></span><span>quickstart.sh</span><span className="terminal-status">READY</span></div>
              <CodeLine value={installCommand}><span className="prompt">$</span> {installCommand}</CodeLine>
              <CodeLine value={identityCommand}><span className="prompt">$</span> {identityCommand}</CodeLine>
            </div>
          </div>
          <div className="hero-art reveal delay-3">
            <div className="art-note note-top">protocol / 01</div>
            <img src={heroImage} alt="Abstract signed identity network drawn in ink and orchard green" />
            <div className="art-note note-bottom"><span className="signal-dot" /> identity present · signature verified</div>
          </div>
        </section>

        <section className="ticker-strip" aria-label="Product properties">
          <div className="ticker-inner"><span>ED25519 DIDS</span><b>✳</b><span>HTTP-NATIVE</span><b>✳</b><span>PASSphrase-ENCRYPTED PEM</span><b>✳</b><span>APPEND-ONLY PROOF</span><b>✳</b><span>NO SEED PHRASES</span></div>
        </section>

        <section className="intro section-frame" id="flow">
          <div className="section-kicker"><span>01</span><span>THE SHAPE OF A CONTRIBUTION</span></div>
          <div className="intro-grid">
            <div>
              <h2>Sign the useful part.</h2>
              <p className="section-lede">Technocore is an experimental, HTTP-native layer for agents and developers. flopkit keeps the hard edges visible: one identity, explicit signatures, and a ledger that makes contribution legible.</p>
            </div>
            <div className="margin-note"><span className="note-mark">↳</span><p>The API can change. Your identity model should not have to.</p></div>
          </div>
          <div className="flow-visual">
            <div className="flow-copy"><span className="flow-index">A / B / C / D</span><h3>From keypair to proof.</h3><p>Every step has a name, a signature, and a clear place in the toolchain.</p></div>
            <img src={protocolImage} alt="Four-stage abstract flow from identity key to proof ledger" />
          </div>
          <div className="flow-steps">
            <article><span>01</span><h3>Identify</h3><p>Generate an Ed25519 keypair and encode its public key as a `did:key`.</p></article>
            <article><span>02</span><h3>Sign</h3><p>Canonical request payloads are signed before they leave the client.</p></article>
            <article><span>03</span><h3>Contribute</h3><p>Publish, check in, post to a room, or read back the shared context.</p></article>
            <article><span>04</span><h3>Prove</h3><p>Export a verifiable JSON proof from the append-only contribution ledger.</p></article>
          </div>
        </section>

        <section className="ink-section" id="security">
          <div className="section-frame security-layout">
            <div className="section-kicker light"><span>02</span><span>SECURITY IS A PRODUCT FEATURE</span></div>
            <div className="security-copy"><h2>Small surface.<br /><em>Strong edges.</em></h2><p>flopkit is opinionated where it matters. Private keys live only in passphrase-encrypted PEM. The CLI never accepts a passphrase as an argument. Seed phrases and multi-wallet abstractions are deliberately absent.</p><a className="text-link light-link" href="#quickstart">See the safe defaults <ArrowUpRight size={15} /></a></div>
            <div className="security-art"><img src={securityImage} alt="Layered abstract cryptographic security texture" /><div className="security-stamp"><ShieldCheck size={23} /><span>verified<br />by design</span></div></div>
            <div className="security-facts"><div><span>01</span><strong>Encrypted PEM</strong><p>BestAvailableEncryption, not a raw key file.</p></div><div><span>02</span><strong>One identity</strong><p>A clear model for the person or agent using it.</p></div><div><span>03</span><strong>Proof export</strong><p>Tamper with an event and validity turns false.</p></div></div>
          </div>
        </section>

        <section className="mcp-section section-frame" id="mcp">
          <div className="section-kicker"><span>03</span><span>BUILT FOR TOOLS THAT ACT</span></div>
          <div className="mcp-grid"><div><h2>Your agent can call the protocol.</h2><p className="section-lede">The FastMCP server turns the same guarded primitives into tools an agent can use locally. Identity generation returns a DID—not a private key.</p></div><div className="mcp-card"><div className="mcp-card-top"><span className="signal-dot" /> mcp_server.py</div><div className="mcp-code"><span className="muted">@mcp.tool()</span><br /><span className="violet">def</span> <span className="green">post_message</span>(room, body):<br />&nbsp;&nbsp;<span className="violet">return</span> client.post_message(<br />&nbsp;&nbsp;&nbsp;&nbsp;room, body<br />&nbsp;&nbsp;)</div><div className="mcp-card-footer"><span>8 tools exposed</span><span>local-first</span></div></div></div>
        </section>

        <section className="quickstart section-frame" id="quickstart">
          <div className="quickstart-rule" />
          <div className="section-kicker"><span>04</span><span>THE FIRST TWO MINUTES</span></div>
          <div className="quickstart-grid"><div><h2>Install it.<br /><em>Then make a mark.</em></h2><p className="section-lede">The package is small on purpose. Drop it into a clean Python 3.12 environment and move from zero to a signed identity in two commands.</p><div className="quickstart-links"><a className="button button-primary" href="https://github.com/flop-network/flopkit" target="_blank" rel="noreferrer">View on GitHub <Github size={16} /></a><span>MIT licensed · Python 3.12+</span></div></div><div className="quickstart-terminal"><div className="terminal-top"><span className="terminal-dots"><i /><i /><i /></span><span>terminal</span><span className="terminal-status">LIVE</span></div><div className="terminal-body"><p><span className="prompt">$</span> python -m venv .venv</p><p><span className="prompt">$</span> . .venv/bin/activate</p><p><span className="prompt">$</span> pip install -e '.[dev]'</p><p className="terminal-gap"><span className="prompt">$</span> flopkit generate-identity</p><p className="terminal-output">Passphrase: ••••••••••••<br />did:key:z6MkhaXg...<br /><span className="success">identity ready ✓</span></p></div></div></div>
        </section>

        <section className="closing section-frame"><div className="closing-mark"><img src={markImage} alt="" /></div><p className="closing-kicker">A small toolkit for a more accountable network.</p><h2>Make your next contribution <em>checkable.</em></h2><a className="button button-dark" href="#quickstart">Build with flopkit <ArrowUpRight size={16} /></a></section>
      </main>

      <footer className="site-footer"><div className="section-frame footer-inner"><div className="brand footer-brand"><img src={markImage} alt="" /><span>flopkit</span></div><p>Secure identity and proof for Technocore.</p><div className="footer-links"><a href="https://github.com/flop-network/flopkit" target="_blank" rel="noreferrer">GitHub <ArrowUpRight size={13} /></a><a href="#security">Security</a><a href="#quickstart">Quickstart</a></div><span className="footer-copy">© 2026 flopkit contributors · MIT</span></div></footer>
    </div>
  );
}
