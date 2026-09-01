# flopkit website design brief

## Three stylistic approaches

### Theme Name: Terminal Orchard
Very Brief Intro: A warm, editorial developer tool site with paper-like surfaces, signal green, and a tactile terminal rhythm. It makes cryptography feel approachable without losing rigor.
Probability: 0.07

### Theme Name: Signal Loom
Very Brief Intro: A dark, instrument-panel aesthetic where identity, signatures, and network calls become a woven field of luminous traces. The mood is precise, nocturnal, and systems-oriented.
Probability: 0.04

### Theme Name: Civic Protocol
Very Brief Intro: A restrained Swiss-inspired documentation site with cobalt ink, off-white paper, and red annotation marks. It treats open-source infrastructure as public craft.
Probability: 0.08

## Chosen approach: Terminal Orchard

### Design Movement
Contemporary technical editorial, blending terminal culture with Swiss editorial hierarchy and the tactile calm of a well-made field notebook.

### Core Principles
1. Make the security model visible rather than ornamental.
2. Pair a warm, human surface with exact monospace utility details.
3. Use asymmetry and editorial pacing instead of a centered marketing template.
4. Turn the onboarding flow into a visual narrative: identity → sign → publish → prove.

### Color Philosophy
The foundation is warm parchment (#F4F0E7), not stark white, so the product feels grounded and readable. Deep ink (#17231D) carries the primary text. The signature color is orchard green (#A9E65B): it signals liveness and verification without falling into neon-cyberpunk excess. Rust orange (#C9653D) is reserved for warnings, annotations, and the few moments where the site needs to say “pay attention.”

### Layout Paradigm
A left-anchored editorial rail with offset content blocks, thin ruled dividers, and wide breathing room. The hero uses a two-column split: copy and install CTA on the left, a hand-built protocol diagram on the right. Sections alternate between full-bleed ink panels and parchment content to create a deliberate scroll rhythm.

### Signature Elements
1. Orchard glyph: a simple three-node mark suggesting a key, a leaf, and a signed message.
2. “Protocol notes” annotations in rust, like margin marks in a field guide.
3. Tactile terminal cards with a green cursor and tiny status labels.

### Interaction Philosophy
Interactions should feel like a tool acknowledging the developer: copy buttons confirm quietly, nav links scroll with intent, and code cards expose the next step without modal friction. Buttons compress on press, and hover states brighten the orchard green rather than changing shape.

### Animation
Use 180–240ms ease-out transitions for hover, focus, and reveal states. On load, stagger hero eyebrow, headline, body, and terminal card by 45ms. The protocol diagram draws in with opacity and a short translateY, never scale from zero. Respect reduced-motion preferences.

### Typography System
Headings use Fraunces 700 for a human, editorial voice. Body uses IBM Plex Sans for clean technical readability. Code and labels use IBM Plex Mono. The hierarchy is intentionally contrastive: oversized serif headlines, compact sans explanations, and small mono metadata.

### Brand Essence
The secure, open-source control plane for agents that need to identify, sign, and contribute to Technocore. Personality: exacting, generous, grounded.

### Brand Voice
Headlines are direct and slightly poetic; CTAs are active and specific; microcopy explains what is protected. Avoid generic filler.
Example lines: “Give your agent a verifiable name.” “Sign the useful part.”

### Wordmark & Logo
The wordmark is lowercase `flopkit` set in a custom-feeling serif/sans pairing. The mark is a bold three-node orchard glyph with one leaf-like terminal, used independently in the nav and as a favicon.

### Signature Brand Color
Orchard green — #A9E65B.

## Content architecture

The first release will be a single-page product site with anchored sections for Overview, Security, Flow, MCP, and Quickstart. A sticky header, responsive mobile rail, interactive copy buttons, and a visible “Read the docs” link make the page useful as both a landing page and a lightweight product guide.
