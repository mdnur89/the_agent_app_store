import { useState, useEffect, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import Header from '../components/Header'
import '../App.css'
import { apiFetch } from '../lib/api'
import { isRecordingSupported, playAudioResponse, startRecording } from '../lib/voice'

export default function Chat() {
  const { agentId } = useParams()
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState(null)
  const [recording, setRecording] = useState(false)
  const [speakingIndex, setSpeakingIndex] = useState(null)
  const [notice, setNotice] = useState(null)
  const messagesEndRef = useRef(null)
  const recorderRef = useRef(null)

  const canRecord = isRecordingSupported()

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Releasing the mic on unmount matters: navigating away mid-recording
  // otherwise leaves the browser's recording indicator lit until the tab dies.
  useEffect(() => () => recorderRef.current?.cancel(), [])

  const exchange = async (path, options, optimistic) => {
    setNotice(null)
    if (optimistic) setMessages(prev => [...prev, optimistic])
    setLoading(true)
    try {
      const data = await (await apiFetch(path, options)).json()
      if (data.session_id) setSessionId(data.session_id)
      setMessages(prev => {
        // A voice turn only learns what the user actually said once the server
        // has transcribed it, so backfill the placeholder rather than leaving
        // "🎤 Transcribing…" in the transcript forever.
        const next = [...prev]
        if (data.transcript && next.length && next[next.length - 1].pending) {
          next[next.length - 1] = { role: 'user', content: data.transcript }
        }
        return [...next, { role: 'assistant', content: data.reply }]
      })
    } catch (err) {
      setMessages(prev => prev.filter(m => !m.pending))
      setNotice(err.message || 'Could not reach the agent.')
    } finally {
      setLoading(false)
    }
  }

  const sendMessage = async (e) => {
    e.preventDefault()
    const text = input.trim()
    if (!text) return
    setInput('')
    await exchange(
      `/api/agents/${agentId}/chat`,
      { method: 'POST', body: JSON.stringify({ text, session_id: sessionId }) },
      { role: 'user', content: text },
    )
  }

  const toggleRecording = async () => {
    if (recording) {
      const recorder = recorderRef.current
      recorderRef.current = null
      setRecording(false)
      try {
        const file = await recorder.stop()
        const form = new FormData()
        form.append('audio', file)
        if (sessionId) form.append('session_id', sessionId)
        // No Content-Type header: apiFetch leaves FormData alone so the
        // browser can set the multipart boundary itself.
        await exchange(
          `/api/agents/${agentId}/chat/voice`,
          { method: 'POST', body: form },
          { role: 'user', content: '🎤 Transcribing…', pending: true },
        )
      } catch (err) {
        setNotice(err.message || 'Could not record audio.')
      }
      return
    }
    try {
      setNotice(null)
      recorderRef.current = await startRecording()
      setRecording(true)
    } catch {
      setNotice('Microphone access was blocked. Check your browser permissions.')
    }
  }

  const speak = async (index, text) => {
    setSpeakingIndex(index)
    setNotice(null)
    try {
      const res = await apiFetch(`/api/agents/${agentId}/speak`, {
        method: 'POST', body: JSON.stringify({ text }),
      })
      await playAudioResponse(await res.blob())
    } catch (err) {
      setNotice(err.message || 'Could not play that reply.')
    } finally {
      setSpeakingIndex(null)
    }
  }

  return (
    <div className="dashboard" style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Header />
      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', maxWidth: '800px', margin: '0 auto', width: '100%', padding: '24px' }}>
        <div style={{ marginBottom: '16px' }}>
          <Link to="/dashboard" style={{ color: 'var(--text)', textDecoration: 'none' }}>← Back to Dashboard</Link>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', background: 'var(--code-bg)', borderRadius: '12px', padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px', border: '1px solid var(--border)' }}>
          {messages.length === 0 ? (
            <div style={{ margin: 'auto', color: 'var(--text)', textAlign: 'center' }}>
              <h3>Start a conversation</h3>
              <p>Type a message{canRecord ? ', or hold a thought and tap the mic' : ''} to begin.</p>
            </div>
          ) : (
            messages.map((msg, i) => (
              <div key={i} style={{ alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start', maxWidth: '80%', background: msg.role === 'user' ? 'var(--accent)' : 'var(--bg)', color: msg.role === 'user' ? 'white' : 'var(--text-h)', padding: '12px 16px', borderRadius: '12px', border: msg.role === 'user' ? 'none' : '1px solid var(--border)', opacity: msg.pending ? 0.7 : 1 }}>
                {msg.content}
                {msg.role === 'assistant' && (
                  <button
                    onClick={() => speak(i, msg.content)}
                    disabled={speakingIndex !== null}
                    title="Play this reply"
                    aria-label="Play this reply"
                    style={{ marginLeft: '10px', background: 'transparent', border: 'none', cursor: speakingIndex === null ? 'pointer' : 'wait', color: 'var(--text)', fontSize: '15px', padding: 0 }}
                  >
                    {speakingIndex === i ? '🔊' : '🔈'}
                  </button>
                )}
              </div>
            ))
          )}
          {loading && <div style={{ alignSelf: 'flex-start', padding: '12px 16px', color: 'var(--text)' }}>Let me think...</div>}
          <div ref={messagesEndRef} />
        </div>

        {notice && (
          <p role="status" style={{ margin: '12px 0 0', color: 'var(--accent)', fontSize: '14px' }}>{notice}</p>
        )}

        <form onSubmit={sendMessage} style={{ marginTop: '16px', display: 'flex', gap: '8px' }}>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={recording ? 'Recording… tap the mic to send' : 'Type a message...'}
            disabled={recording}
            style={{ flex: 1, padding: '16px', borderRadius: '8px', border: '1px solid var(--border)', background: 'var(--code-bg)', color: 'var(--text-h)' }}
          />
          {canRecord && (
            <button
              type="button"
              onClick={toggleRecording}
              disabled={loading}
              title={recording ? 'Stop and send' : 'Record a voice message'}
              aria-label={recording ? 'Stop recording and send' : 'Record a voice message'}
              style={{ background: recording ? '#c0392b' : 'var(--code-bg)', color: recording ? 'white' : 'var(--text-h)', border: '1px solid var(--border)', borderRadius: '8px', padding: '0 18px', fontSize: '18px', cursor: 'pointer' }}
            >
              {recording ? '■' : '🎤'}
            </button>
          )}
          <button type="submit" disabled={loading || recording} style={{ background: 'var(--accent)', color: 'white', border: 'none', borderRadius: '8px', padding: '0 24px', fontWeight: 'bold', cursor: 'pointer' }}>
            Send
          </button>
        </form>
      </main>
    </div>
  )
}
