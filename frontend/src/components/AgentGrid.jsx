import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'

export default function AgentGrid({ agents, loading, onChanged }) {
  const togglePublish = async (agent) => {
    await apiFetch(`/api/agents/${agent.id}/${agent.visibility === 'public' ? 'unpublish' : 'publish'}`, { method: 'POST' })
    onChanged()
  }
  return (
    <section className="grid-section">
      <h2>Active Agents</h2>
      {loading ? (
        <p className="loading">Fetching agents...</p>
      ) : agents.length === 0 ? (
        <p className="empty-state">No agents deployed yet. Create your first one!</p>
      ) : (
        <div className="agents-grid">
          {agents.map((agent) => (
            <div key={agent.id} className={`agent-card ${agent.isActive ? 'active' : 'inactive'}`}>
              <div className="card-header">
                <h3>{agent.name}</h3>
                <span className="badge">{agent.visibility}</span>
              </div>
              <p className="card-desc">{agent.description || 'No description provided.'}</p>
              <div className="card-footer">
                <span className="voice-tag">🎤 {agent.voice_type}</span>
                <span className={`status-dot ${agent.isActive ? 'live' : 'offline'}`}></span>
              </div>
              <div style={{ marginTop: '16px' }}>
                <Link to={`/chat/${agent.id}`} className="chat-link">
                  Chat Now
                </Link>
                {agent.is_owner && <button className="publish-btn" onClick={() => togglePublish(agent)}>
                  {agent.visibility === 'public' ? 'Unpublish' : 'Publish'}
                </button>}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
