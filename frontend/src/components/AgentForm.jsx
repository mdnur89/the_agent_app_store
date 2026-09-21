import { useState } from 'react'
import { apiFetch } from '../lib/api'

export default function AgentForm({ onAgentCreated }) {
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    system_prompt: '',
    llm_model: 'llama-3.1-8b-instant',
    voice_type: 'default'
  })

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value })
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    try {
      const res = await apiFetch('/api/agents/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...formData, isActive: true })
      })
      if (res.ok) onAgentCreated()
      setFormData({ ...formData, name: '', description: '', system_prompt: '' })
    } catch (err) {
      console.error("Failed to create agent:", err)
    }
  }

  return (
    <section className="form-section">
      <h2>Create New Agent</h2>
      <form className="agent-form" onSubmit={handleSubmit}>
        <div className="input-group">
          <label>Agent Name</label>
          <input 
            type="text" 
            name="name" 
            value={formData.name} 
            onChange={handleChange} 
            placeholder="e.g., Sales Coach" 
            required 
          />
        </div>

        <div className="input-group">
          <label>Description</label>
          <input 
            type="text" 
            name="description" 
            value={formData.description} 
            onChange={handleChange} 
            placeholder="Briefly describe what this agent does" 
          />
        </div>

        <div className="input-group">
          <label>System Prompt</label>
          <textarea 
            name="system_prompt" 
            value={formData.system_prompt} 
            onChange={handleChange} 
            placeholder="You are an expert sales coach. Your goal is to..." 
            rows="4" 
            required 
          />
        </div>

        <div className="row">
          <div className="input-group">
            <label>LLM Model</label>
            <select name="llm_model" value={formData.llm_model} onChange={handleChange}>
              <option value="llama-3.1-8b-instant">Llama 3.1 (8B) - Fastest</option>
              <option value="llama-3.3-70b-versatile">Llama 3.3 (70B) - Smartest</option>
              <option value="gemini-1.5-flash">Gemini 1.5 Flash</option>
            </select>
          </div>

          <div className="input-group">
            <label>Voice Type</label>
            <select name="voice_type" value={formData.voice_type} onChange={handleChange}>
              <option value="default">Default</option>
              <option value="male-1">Professional Male</option>
              <option value="female-1">Professional Female</option>
            </select>
          </div>
        </div>

        <button type="submit" className="submit-btn">Deploy Agent</button>
      </form>
    </section>
  )
}
