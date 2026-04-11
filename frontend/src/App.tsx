import { ProjectProvider } from './context/ProjectContext'
import AppShell from './layout/AppShell'

export default function App() {
  return (
    <ProjectProvider>
      <AppShell />
    </ProjectProvider>
  )
}
