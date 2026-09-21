import { Link } from 'react-router-dom'
import logo from '../assets/logo.svg'
import { useAuth } from '../context/auth-state'
import { supabase } from '../lib/supabase'

export default function Header() {
  const { user } = useAuth()
  return (
    <header className="dashboard-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <img src={logo} alt="Agent App Store Logo" width="40" height="40" />
        <h1 style={{ margin: 0 }}>Agent Control Center</h1>
      </div>
      <nav className="account-nav">
        <span>{user?.email}</span>
        <Link to="/settings">Settings</Link>
        <Link to="/">Home</Link>
        <button onClick={() => supabase.auth.signOut()}>Sign out</button>
      </nav>
    </header>
  )
}
