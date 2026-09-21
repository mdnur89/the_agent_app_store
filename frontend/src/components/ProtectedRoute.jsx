import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/auth-state'

export default function ProtectedRoute({ children }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <div className="page-state">Loading your account…</div>
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return children
}
