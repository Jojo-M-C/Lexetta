import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

export default function Library() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-4xl mx-auto">
        <div className="flex justify-between items-center mb-8">
          <h1 className="text-3xl font-bold">My Library</h1>
          <div className="flex items-center gap-4">
            <span className="text-gray-600">
              {user?.username} ({user?.reading_level ?? "no level"})
            </span>
            <button
              onClick={handleLogout}
              className="text-sm text-blue-600 hover:underline"
            >
              Log out
            </button>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <p className="text-gray-500">
            No documents yet. Upload functionality coming soon.
          </p>
        </div>
      </div>
    </div>
  );
}