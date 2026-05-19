import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { api } from "../api";

export default function Profile() {
  const { user, logout, updateUser } = useAuth();
  const navigate = useNavigate();
  const [saving, setSaving] = useState(false);

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  const handleToggleML = async () => {
    if (!user) return;
    const next = !user.use_ml_predictions;
    setSaving(true);
    try {
      const updated = await api.updateMe({ use_ml_predictions: next });
      updateUser({ use_ml_predictions: updated.use_ml_predictions });
    } catch (e) {
      console.error("Failed to update settings:", e);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-3xl font-bold mb-8">Profile</h1>

      <div className="bg-white rounded-lg shadow p-6 mb-4">
        <div className="space-y-4">
          <div>
            <label className="text-sm text-gray-500">Username</label>
            <p className="font-medium">{user?.username}</p>
          </div>
          <div>
            <label className="text-sm text-gray-500">Reading Level</label>
            <p className="font-medium">{user?.reading_level ?? "Not set"}</p>
          </div>

          <div className="flex items-center justify-between pt-2">
            <div>
              <p className="font-medium">ML Predictions</p>
              <p className="text-sm text-gray-500">
                {user?.use_ml_predictions
                  ? "Using ML model for difficulty"
                  : "Using CEFR word list for difficulty"}
              </p>
            </div>
            <button
              role="switch"
              aria-checked={user?.use_ml_predictions ?? false}
              disabled={saving}
              onClick={handleToggleML}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none disabled:opacity-50 ${
                user?.use_ml_predictions ? "bg-blue-600" : "bg-gray-200"
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                  user?.use_ml_predictions ? "translate-x-6" : "translate-x-1"
                }`}
              />
            </button>
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