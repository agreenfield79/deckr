import { ProjectProvider } from './context/ProjectContext'
import { ToastProvider } from './context/ToastContext'
import AppShell from './layout/AppShell'

export default function App() {
  return (
    <ToastProvider>
      <ProjectProvider>
        <AppShell />
      </ProjectProvider>
    </ToastProvider>
  )
}
