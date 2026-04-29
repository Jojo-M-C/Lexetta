import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

export default function Profile() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-3xl font-bold mb-8">Profile</h1>

      <div className="bg-white rounded-lg shadow p-6 mb-4">
        <div className="space-y-3">
          <div>
            <label className="text-sm text-gray-500">Username</label>
            <p className="font-medium">{user?.username}</p>
          </div>
          <div>
            <label className="text-sm text-gray-500">Reading Level</label>
            <p className="font-medium">{user?.reading_level ?? "Not set"}</p>
          </div>
          <div>
            <label className="text-sm text-gray-500">ML Predictions</label>
            <p className="font-medium">
              {user?.use_ml_predictions ? "Enabled" : "Disabled"}
            </p>
          </div>
        </div>
      </div>

      <button
        onClick={handleLogout}
        className="bg-red-50 text-red-700 hover:bg-red-100 rounded-lg px-4 py-2 font-medium"
      >
        Log out
      </button>
    </div>
  );
}