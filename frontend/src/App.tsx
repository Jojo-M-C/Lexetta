import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { AuthProvider, useAuth } from "./auth";
import Library from "./pages/Library";
import Login from "./pages/Login";
import Profile from "./pages/Profile";
import Vocabulary from "./pages/Vocabulary";
import Reader from "./pages/Reader";

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />

        <Route
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route path="/library" element={<Library />} />
          <Route path="/vocabulary" element={<Vocabulary />} />
          <Route path="/profile" element={<Profile />} />
        </Route>
          <Route
            path="/reader/:documentId"
            element={
              <ProtectedRoute>
                <Reader />
              </ProtectedRoute>
            }
          />

        <Route path="*" element={<Navigate to="/library" replace />} />
      </Routes>
    </AuthProvider>
  );
}