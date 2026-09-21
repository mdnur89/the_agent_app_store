import { useEffect, useState } from 'react'
import Header from '../components/Header'
import { apiFetch } from '../lib/api'
import '../App.css'

export default function Settings() {
  const [profile, setProfile] = useState(null)
  const [code, setCode] = useState(null)
  const [seconds, setSeconds] = useState(0)
  const [error, setError] = useState('')
  const load = () => apiFetch('/api/users/me').then(r => r.json()).then(setProfile).catch(e => setError(e.message))
  useEffect(() => { load() }, [])
  useEffect(() => {
    if (!code) return
    const tick = () => setSeconds(Math.max(0, Math.ceil((new Date(code.expires_at) - Date.now()) / 1000)))
    tick()
    const timer = setInterval(tick, 1000)
    return () => clearInterval(timer)
  }, [code])

  const generate = async () => {
    setError('')
    try { setCode(await (await apiFetch('/api/users/me/telegram/link-code', { method: 'POST' })).json()) }
    catch (e) { setError(e.message) }
  }
  const disconnect = async () => {
    try { await apiFetch('/api/users/me/telegram', { method: 'DELETE' }); setCode(null); await load() }
    catch (e) { setError(e.message) }
  }

  return <div className="dashboard"><Header /><main className="settings-card">
    <h2>Account settings</h2>
    <p>{profile?.email}</p>
    <div className="settings-row"><div><h3>Telegram</h3><p>{profile?.telegram_linked ? 'Connected' : 'Not connected'}</p></div>
      {profile?.telegram_linked ? <button onClick={disconnect}>Disconnect</button> : <button onClick={generate}>Generate link code</button>}
    </div>
    {code && <div className="link-code"><strong>{code.code}</strong><p>Send <code>/link {code.code}</code> to the bot. Expires in {seconds}s.</p></div>}
    {error && <p>{error}</p>}
  </main></div>
}
