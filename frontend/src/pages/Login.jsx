import { useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/auth-state'
import { supabase } from '../lib/supabase'
import './Login.css'

export default function Login() {
  const { user } = useAuth()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [mode, setMode] = useState('signin')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  if (user) return <Navigate to={location.state?.from || '/dashboard'} replace />

  const submit = async (event) => {
    event.preventDefault()
    setBusy(true)
    setMessage('')
    const result = mode === 'signup'
      ? await supabase.auth.signUp({ email, password })
      : await supabase.auth.signInWithPassword({ email, password })
    setBusy(false)
    if (result.error) return setMessage(result.error.message)
    if (mode === 'signup' && !result.data.session) setMessage('Check your email to confirm your account, then sign in.')
  }

  return <main className="auth-page">
    <section className="auth-card">
      <p className="eyebrow">THE HUB</p>
      <h1>{mode === 'signin' ? 'Welcome back' : 'Create your account'}</h1>
      <p>Your agents and conversations stay tied to your account.</p>
      <form onSubmit={submit}>
        <label>Email<input type="email" value={email} onChange={e => setEmail(e.target.value)} required /></label>
        <label>Password<input type="password" minLength="6" value={password} onChange={e => setPassword(e.target.value)} required /></label>
        <button className="submit-btn" disabled={busy}>{busy ? 'Working…' : mode === 'signin' ? 'Sign in' : 'Sign up'}</button>
      </form>
      {message && <p className="auth-message">{message}</p>}
      <button className="text-button" onClick={() => setMode(mode === 'signin' ? 'signup' : 'signin')}>
        {mode === 'signin' ? 'Need an account? Sign up' : 'Already registered? Sign in'}
      </button>
    </section>
  </main>
}
