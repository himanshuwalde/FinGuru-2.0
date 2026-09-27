import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './lib/auth'
import { LandingPage } from './pages/landing/LandingPage'
import { AuthModal } from './components/AuthModal'
import { AppShell } from './components/AppShell'
import { DashboardPage } from './pages/track/DashboardPage'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="min-h-screen flex items-center justify-center">Loading...</div>
  if (!user) return <Navigate to="/" replace />
  return <>{children}</>
}

function PublicRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="min-h-screen flex items-center justify-center">Loading...</div>
  if (user) return <Navigate to="/track/dashboard" replace />
  return <>{children}</>
}

function AppRoutes() {
  return (
    <Routes>
      {/* Public landing page - shown to unauthenticated users */}
      <Route path="/" element={
        <PublicRoute>
          <LandingPage />
        </PublicRoute>
      } />

      {/* Protected app shell with sidebar + topbar */}
      <Route element={
        <ProtectedRoute>
          <AppShell />
        </ProtectedRoute>
      }>
        <Route path="track/dashboard" element={<DashboardPage />} />
        <Route path="track/*" element={<div className="p-6">Track - Coming Soon</div>} />
        <Route path="grow/*" element={<div className="p-6">Grow - Coming Soon</div>} />
        <Route path="learn/*" element={<div className="p-6">Learn - Coming Soon</div>} />
        <Route path="protect/*" element={<div className="p-6">Protect - Coming Soon</div>} />
        <Route path="ai-cfo/*" element={<div className="p-6">AI CFO - Coming Soon</div>} />
      </Route>
    </Routes>
  )
}

function App() {
  return (
    <AuthProvider>
      <AppRoutes />
      <AuthModal />
    </AuthProvider>
  )
}

export default App
