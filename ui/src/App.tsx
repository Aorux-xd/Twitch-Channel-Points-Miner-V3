/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { ThemeProvider } from './context/ThemeContext';
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { LoginPage } from './components/LoginPage';
import { motion, AnimatePresence } from 'motion/react';
import { getPanelToken } from './lib/auth';
import { ROUTES, labelForPath } from './routes';

function DashboardShell() {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const activeTab = labelForPath(location.pathname);

  const setActiveTab = (tab: string) => {
    const row = ROUTES.find((r) => r.label === tab);
    navigate(row?.path ?? '/');
  };

  return (
    <div className="min-h-screen bg-dashboard-bg text-text-main flex transition-colors duration-300">
      <Sidebar
        isCollapsed={isCollapsed}
        setIsCollapsed={setIsCollapsed}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
      />

      <motion.main
        initial={false}
        animate={{
          paddingLeft: isCollapsed ? 120 : 300,
        }}
        className="flex-1 pr-6 min-w-0"
      >
        <div className="pt-6">
          <Header />
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.15 }}
            >
              <Routes>
                {ROUTES.map((r) => (
                  <Route key={r.path} path={r.path} element={r.element} />
                ))}
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </motion.div>
          </AnimatePresence>
        </div>
      </motion.main>

    </div>
  );
}

function RequireAuth({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState(() => getPanelToken());

  React.useEffect(() => {
    const onStorage = () => setToken(getPanelToken());
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  if (!token) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

export default function App() {
  const [authed, setAuthed] = useState(() => Boolean(getPanelToken()));

  return (
    <ThemeProvider>
      <BrowserRouter>
        <Routes>
          <Route
            path="/login"
            element={
              authed ? (
                <Navigate to="/" replace />
              ) : (
                <LoginPage onSuccess={() => setAuthed(true)} />
              )
            }
          />
          <Route
            path="/*"
            element={
              <RequireAuth>
                <DashboardShell />
              </RequireAuth>
            }
          />
        </Routes>
      </BrowserRouter>
    </ThemeProvider>
  );
}
