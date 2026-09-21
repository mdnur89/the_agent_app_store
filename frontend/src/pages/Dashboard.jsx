import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import Header from '../components/Header'
import AgentForm from '../components/AgentForm'
import AgentGrid from '../components/AgentGrid'
import '../App.css'
import { apiFetch } from '../lib/api'

export default function Dashboard() {
  const [agents, setAgents] = useState([])
  const [loading, setLoading] = useState(true)
  const [openCategories, setOpenCategories] = useState({})
  const [viewMoreCategories, setViewMoreCategories] = useState({})

  const toggleViewMore = (category) => {
    setViewMoreCategories(prev => ({
      ...prev,
      [category]: !prev[category]
    }))
  }

  const toggleCategory = (category) => {
    setOpenCategories(prev => ({
      ...prev,
      [category]: prev[category] === undefined ? false : !prev[category]
    }))
  }

  const isCategoryOpen = (category) => {
    return openCategories[category] !== undefined ? openCategories[category] : true
  }

  const fetchAgents = async () => {
    try {
      const res = await apiFetch('/api/agents/')
      const data = await res.json()
      setAgents(data)
    } catch (err) {
      console.error("Failed to fetch agents:", err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchAgents()
  }, [])

  const systemAgents = agents.filter(a => a.is_system)
  const customAgents = agents.filter(a => !a.is_system)

  return (
    <div className="dashboard">
      <Header />
      
      {/* Community Banner */}
      <div className="community-banner" style={{
        background: 'var(--code-bg)',
        border: '1px solid var(--border)',
        borderRadius: '12px',
        padding: '24px',
        marginBottom: '24px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <div>
          <h3 style={{ margin: '0 0 8px 0', color: 'var(--text-h)' }}>Built by the Community 🌍</h3>
          <p style={{ margin: 0, color: 'var(--text)' }}>The Hub is open source. Contribute your own specialist agent to the official Swarm registry!</p>
        </div>
        <a href="https://github.com/TadiwanasheZvidzaRodney/the_agent_app_store/blob/main/CONTRIBUTING.md" target="_blank" rel="noopener noreferrer" style={{
          background: 'var(--text-h)',
          color: 'var(--bg)',
          padding: '12px 24px',
          borderRadius: '8px',
          textDecoration: 'none',
          fontWeight: 'bold',
          whiteSpace: 'nowrap'
        }}>
          Contribute an Agent
        </a>
      </div>
      {/* Render System Agents Grouped by Category */}
      {(() => {
        const categories = [...new Set(systemAgents.map(a => a.category))]
        return categories.map(category => {
          const isOpen = isCategoryOpen(category);
          
          return (
          <section key={category} className="system-agents-tabs" style={{ marginBottom: '24px', background: 'var(--bg)', borderRadius: '12px', border: '1px solid var(--border)', overflow: 'hidden' }}>
            
            {/* Accordion Header */}
            <div 
              onClick={() => toggleCategory(category)}
              style={{ padding: '16px 24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer', background: 'var(--accent-bg)', transition: 'background 0.2s' }}
            >
              <h2 style={{ margin: 0, textTransform: 'capitalize', fontSize: '20px' }}>
                {category} Experts
              </h2>
              <span style={{ transform: isOpen ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.3s ease', fontSize: '18px' }}>
                ▼
              </span>
            </div>

            {/* Accordion Content */}
            {isOpen && (
              <>
                <div className="tabs-container" style={{ padding: '24px', display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '20px', borderTop: '1px solid var(--border)' }}>
                  {systemAgents
                    .filter(a => a.category === category)
                    .slice(0, viewMoreCategories[category] ? undefined : 3)
                    .map(agent => (
                      <div key={agent.id} className="agent-tab" style={{ background: 'var(--accent-bg)', padding: '24px', borderRadius: '16px', border: '1px solid var(--accent-border)', display: 'flex', flexDirection: 'column', gap: '16px', transition: 'transform 0.2s', boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}>
                        
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                          <h3 style={{ margin: 0, fontSize: '20px', color: 'var(--text-h)', fontWeight: '600' }}>{agent.name}</h3>
                          <span className="badge" style={{ background: 'var(--accent)', color: 'white', fontWeight: 'bold' }}>{category.toUpperCase()}</span>
                        </div>
                        
                        <p style={{ fontSize: '15px', color: 'var(--text)', margin: 0, lineHeight: '1.5', flexGrow: 1 }}>{agent.description}</p>
                        
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 'auto' }}>
                          <div style={{ display: 'flex', gap: '8px' }}>
                            <span className="voice-tag" style={{ background: 'rgba(255,255,255,0.1)', padding: '4px 8px', borderRadius: '4px', fontSize: '12px' }}>🎤 {agent.voice_type}</span>
                            <span className="badge" style={{ background: 'rgba(255,255,255,0.1)', padding: '4px 8px', borderRadius: '4px', fontSize: '12px' }}>{agent.llm_model}</span>
                          </div>
                        </div>
                        
                        <Link to={`/chat/${agent.id}`} style={{ display: 'block', textAlign: 'center', background: 'var(--accent)', color: 'white', padding: '10px 16px', borderRadius: '8px', textDecoration: 'none', fontWeight: 'bold', marginTop: '8px' }}>
                          💬 Chat Now
                        </Link>
                      </div>
                  ))}
                </div>
                {systemAgents.filter(a => a.category === category).length > 3 && (
                  <div style={{ padding: '0 24px 24px', textAlign: 'center' }}>
                    <button 
                      onClick={() => toggleViewMore(category)}
                      style={{ background: 'transparent', border: '1px solid var(--accent)', color: 'var(--accent)', padding: '8px 24px', borderRadius: '20px', cursor: 'pointer', fontWeight: '600', transition: 'all 0.2s' }}
                      onMouseOver={e => { e.target.style.background = 'var(--accent)'; e.target.style.color = 'white'; }}
                      onMouseOut={e => { e.target.style.background = 'transparent'; e.target.style.color = 'var(--accent)'; }}
                    >
                      {viewMoreCategories[category] ? 'Show Less ▲' : `View All ${systemAgents.filter(a => a.category === category).length} ▼`}
                    </button>
                  </div>
                )}
              </>
            )}
          </section>
        )})
      })()}

      <main className="dashboard-layout">
        <AgentForm onAgentCreated={fetchAgents} />
        <AgentGrid agents={customAgents} loading={loading} onChanged={fetchAgents} />
      </main>
    </div>
  )
}
