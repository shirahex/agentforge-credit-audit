import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes, useParams } from 'react-router-dom'
import { Shell } from './components/Shell'
import './index.css'
import { Audit } from './pages/Audit'
import { Audits } from './pages/Audits'
import { Dashboard } from './pages/Dashboard'
import { Landing } from './pages/Landing'
import { Model } from './pages/Model'
import { NewAudit } from './pages/NewAudit'

try {
  document.documentElement.dataset.theme = localStorage.getItem('af-theme') ?? 'light'
} catch {
  document.documentElement.dataset.theme = 'light'
}

/** Old links (/audit/:id) from reports and earlier versions. */
function OldAudit() {
  const { id } = useParams()
  return <Navigate to={`/app/audit/${id}`} replace />
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route index element={<Landing />} />
        <Route path="audit/:id" element={<OldAudit />} />
        <Route path="history" element={<Navigate to="/app/audits" replace />} />
        <Route path="model" element={<Navigate to="/app/model" replace />} />
        <Route path="app" element={<Shell />}>
          <Route index element={<Dashboard />} />
          <Route path="new" element={<NewAudit />} />
          <Route path="audits" element={<Audits />} />
          <Route path="review" element={<Audits review />} />
          <Route path="audit/:id" element={<Audit />} />
          <Route path="model" element={<Model />} />
          <Route path="*" element={<Navigate to="/app" replace />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
)
