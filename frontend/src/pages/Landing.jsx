import { Link } from 'react-router-dom'
import { useState, useEffect } from 'react'
import logo from '../assets/logo.svg'
import './Landing.css'
import { useAuth } from '../context/auth-state'

export default function Landing() {
  const { user } = useAuth()
  const [demoStep, setDemoStep] = useState(0)

  useEffect(() => {
    const timer = setInterval(() => {
      setDemoStep((prev) => (prev + 1) % 4)
    }, 2500)
    return () => clearInterval(timer)
  }, [])

  return (
    <div className="landing-container">
      {/* Navigation */}
      <nav className="startup-nav">
        <div className="nav-brand">
          <img src={logo} alt="The Hub Logo" width="32" height="32" />
          <span>The Hub</span>
        </div>
        <div className="nav-links">
          <a href="#features">Features</a>
          <a href="#architecture">Architecture</a>
          <a href="https://github.com/TadiwanasheZvidzaRodney/the_agent_app_store" target="_blank" rel="noopener noreferrer" className="nav-github-link">GitHub</a>
          <Link to={user ? '/dashboard' : '/login'} className="nav-cta">{user ? 'Go to Dashboard' : 'Sign in'}</Link>
        </div>
      </nav>
      
      {/* Hero Section */}
      <section className="startup-hero">
        <div className="hero-content">
          <div className="hero-badge">✨ Swarm Architecture 2.0</div>
          <h1 className="hero-title">
            The Infinite <span className="text-gradient">AI Swarm</span> Ecosystem
          </h1>
          <p className="hero-subtitle">
            Deploy, discover, and orchestrate millions of intelligent specialists. The Master Orchestrator breaks down tasks and dynamically recruits the perfect team.
          </p>
          
          <div className="swarm-demo-card">
            <div className="demo-header">
              <span className="dot red"></span>
              <span className="dot yellow"></span>
              <span className="dot green"></span>
              <span className="demo-title">Swarm Delegation Protocol</span>
            </div>
            <div className="demo-body">
              <div className={`log-line user ${demoStep >= 0 ? 'visible' : ''}`}>
                <span className="prompt">&gt;</span> Build a fitness app and write the marketing copy.
              </div>
              <div className={`log-line system ${demoStep >= 1 ? 'visible' : ''}`}>
                [Orchestrator] Searching vector DB for experts...
              </div>
              <div className={`log-line success ${demoStep >= 2 ? 'visible' : ''}`}>
                ✔ Found: sys-fitness-coach (0.98), sys-copywriter (0.94)
              </div>
              <div className={`log-line action ${demoStep >= 3 ? 'visible' : ''}`}>
                ⚡ Delegating sub-tasks to swarm...
              </div>
            </div>
          </div>

          <div className="hero-actions">
            <Link to={user ? '/dashboard' : '/login'} className="primary-btn">
              Enter The Hub
            </Link>
            <a href="https://github.com/TadiwanasheZvidzaRodney/the_agent_app_store" target="_blank" rel="noopener noreferrer" className="secondary-btn github-btn">
              ⭐ Star on GitHub
            </a>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section id="features" className="startup-features">
        <div className="section-header">
          <h2>An ecosystem that scales to millions</h2>
          <p>Powered by pgvector and Hierarchical Orchestration.</p>
        </div>
        
        <div className="features-grid">
          <div className="feature-card glass">
            <div className="feature-icon">🔍</div>
            <h3>Semantic Discovery</h3>
            <p>Supervisors use cosine similarity vector search to dynamically find and recruit the exact experts they need from a massive database of agents.</p>
          </div>
          <div className="feature-card glass">
            <div className="feature-icon">⚡</div>
            <h3>Swarm Protocol</h3>
            <p>Agents don't just chat—they delegate. The Orchestrator spawns sub-agents in the background, waits for their output, and synthesizes a master response.</p>
          </div>
          <div className="feature-card glass">
            <div className="feature-icon">🌐</div>
            <h3>Multi-Transport</h3>
            <p>Interact with your swarm via a premium React Web UI, or take them on the go natively through Telegram with perfectly synced memory.</p>
          </div>
        </div>
      </section>

      {/* Architecture Section */}
      <section id="architecture" className="startup-architecture">
        <div className="section-header">
          <h2>How the Swarm Works</h2>
          <p>A peek under the hood of our modular, domain-driven infrastructure.</p>
        </div>
        
        <div className="architecture-diagram">
          <div className="arch-layer">
            <div className="arch-box outline">User Request (Web / Telegram)</div>
          </div>
          <div className="arch-arrow">↓</div>
          <div className="arch-layer">
            <div className="arch-box master">Master Orchestrator (Supervisor)</div>
          </div>
          <div className="arch-arrow">↙ ↓ ↘</div>
          <div className="arch-layer multi">
            <div className="arch-box specialist">Business Expert</div>
            <div className="arch-box specialist">Personal Coach</div>
            <div className="arch-box specialist">Code Optimizer</div>
          </div>
          <div className="arch-arrow">↓</div>
          <div className="arch-layer">
            <div className="arch-box db">Supabase pgvector Database</div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="startup-footer">
        <div className="footer-content">
          <div className="footer-brand">
            <img src={logo} alt="The Hub Logo" width="24" height="24" />
            <span>The Hub © 2026. Released under the MIT License.</span>
          </div>
          <div className="footer-links">
            <a href="https://github.com/TadiwanasheZvidzaRodney/the_agent_app_store" target="_blank" rel="noopener noreferrer">GitHub</a>
            <a href="https://github.com/TadiwanasheZvidzaRodney/the_agent_app_store/blob/main/CONTRIBUTING.md" target="_blank" rel="noopener noreferrer">Contribute</a>
            <a href="https://github.com/TadiwanasheZvidzaRodney/the_agent_app_store/blob/main/CODE_OF_CONDUCT.md" target="_blank" rel="noopener noreferrer">Code of Conduct</a>
          </div>
        </div>
      </footer>
    </div>
  )
}
