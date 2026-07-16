import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { AuthProvider, useAuth } from "./auth";
import Library from "./pages/Library";
import Login from "./pages/Login";
import Profile from "./pages/Profile";
import Vocabulary from "./pages/Vocabulary";
import Reader from "./pages/readers/Reader";
import Calibration from "./pages/Calibration";
import Onboarding from "./pages/Onboarding";

function AuthRoute({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

// Requires login + completed onboarding (language + level chosen, then calibration done).
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (!user.target_language) return <Navigate to="/onboarding" replace />;
  if (!user.calibration_done) return <Navigate to="/calibration" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />

        <Route
          path="/onboarding"
          element={
            <AuthRoute>
              <Onboarding />
            </AuthRoute>
          }
        />

        <Route
          path="/calibration"
          element={
            <AuthRoute>
              <Calibration />
            </AuthRoute>
          }
        />

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