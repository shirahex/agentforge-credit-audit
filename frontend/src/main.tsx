import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import './index.css'
import { Audit } from './pages/Audit'
import { History } from './pages/History'
import { Model } from './pages/Model'
import { NewAudit } from './pages/NewAudit'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<NewAudit />} />
          <Route path="audit/:id" element={<Audit />} />
          <Route path="history" element={<History />} />
          <Route path="model" element={<Model />} />
          <Route path="*" element={<NewAudit />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </StrictMode>,
)
