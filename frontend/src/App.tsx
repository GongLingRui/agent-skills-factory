import { BrowserRouter, Link, Navigate, Route, Routes } from 'react-router-dom'
import DevAuthBootstrap from './components/DevAuthBootstrap'
import AdminLayout from './components/layout/AdminLayout'
import AdminAgentsPage from './components/pages/AdminAgentsPage'
import AdminAuditPage from './components/pages/AdminAuditPage'
import AdminDegradationPage from './components/pages/AdminDegradationPage'
import AdminMetricsPage from './components/pages/AdminMetricsPage'
import AdminPoliciesPage from './components/pages/AdminPoliciesPage'
import AdminQuotasPage from './components/pages/AdminQuotasPage'
import AdminSessionTracePage from './components/pages/AdminSessionTracePage'
import AdminSkillsPage from './components/pages/AdminSkillsPage'
import AdminToolsPage from './components/pages/AdminToolsPage'
import AdminUsersPage from './components/pages/AdminUsersPage'
import AgentAboutPage from './components/pages/AgentAboutPage'
import AppsDirectoryPage from './components/pages/AppsDirectoryPage'
import ChatPage from './components/pages/ChatPage'

function App() {
  return (
    <DevAuthBootstrap>
    <BrowserRouter>
      <Routes>
        <Route path="/admin" element={<AdminLayout />}>
          <Route index element={<Navigate to="agents" replace />} />
          <Route path="agents" element={<AdminAgentsPage />} />
          <Route path="skills" element={<AdminSkillsPage />} />
          <Route path="tools" element={<AdminToolsPage />} />
          <Route path="policies" element={<AdminPoliciesPage />} />
          <Route path="quotas" element={<AdminQuotasPage />} />
          <Route path="users" element={<AdminUsersPage />} />
          <Route path="audit" element={<AdminAuditPage />} />
          <Route path="session-trace" element={<AdminSessionTracePage />} />
          <Route path="degradation" element={<AdminDegradationPage />} />
          <Route path="metrics" element={<AdminMetricsPage />} />
        </Route>
        <Route path="/apps" element={<AppsDirectoryPage />} />
        <Route path="/apps/:agentId/about" element={<AgentAboutPage />} />
        <Route path="/apps/:agentId" element={<ChatPage />} />
        <Route
          path="/"
          element={
            <div className="min-h-[100dvh] flex flex-col items-center justify-center bg-[var(--widget-bg)] text-slate-600 px-6 gap-6">
              <p className="text-center text-sm sm:text-base max-w-md">
                请从门户打开应用，或使用下方入口浏览全部智能体；也可直接访问{' '}
                <code className="rounded bg-slate-100 px-1.5 py-0.5 text-slate-800">
                  /apps/&lt;agent_id&gt;
                </code>
                。
              </p>
              <div className="flex flex-wrap gap-3 justify-center">
                <Link
                  to="/apps"
                  className="inline-flex items-center rounded-xl bg-primary-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-primary-700"
                >
                  浏览应用库
                </Link>
                <Link
                  to="/admin"
                  className="inline-flex items-center rounded-xl border border-slate-300 dark:border-slate-600 px-5 py-2.5 text-sm font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800"
                >
                  管理台
                </Link>
              </div>
            </div>
          }
        />
      </Routes>
    </BrowserRouter>
    </DevAuthBootstrap>
  )
}

export default App
