import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { api } from "../api";
import { READING_LEVELS } from "../lib/levels";

export default function Profile() {
  const { user, logout, updateUser } = useAuth();
  const navigate = useNavigate();
  const [saving, setSaving] = useState(false);
  const [languageName, setLanguageName] = useState<string | null>(null);

  useEffect(() => {
    if (!user?.target_language) return;
    api
      .listLanguages()
      .then((langs) => {
        const match = langs.find((l) => l.code === user.target_language);
        setLanguageName(match?.name ?? user.target_language);
      })
      .catch(() => setLanguageName(user.target_language));
  }, [user?.target_language]);

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  const handleChangeLevel = async (reading_level: string) => {
    setSaving(true);
    try {
      const updated = await api.updateMe({ reading_level });
      updateUser({ reading_level: updated.reading_level });
    } catch (e) {
      console.error("Failed to update reading level:", e);
    } finally {
      setSaving(false);
    }
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

  const handleToggleHighlighting = async () => {
    if (!user) return;
    const next = !user.highlighting_enabled;
    setSaving(true);
    try {
      const updated = await api.updateMe({ highlighting_enabled: next });
      updateUser({ highlighting_enabled: updated.highlighting_enabled });
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
            <label className="text-sm text-gray-500" htmlFor="reading-level">
              Reading Level
            </label>
            <select
              id="reading-level"
              value={user?.reading_level ?? ""}
              disabled={saving}
              onChange={(e) => handleChangeLevel(e.target.value)}
              className="mt-1 block w-56 border border-gray-300 rounded p-2 font-medium disabled:opacity-50"
            >
              {!user?.reading_level && <option value="">Not set</option>}
              {READING_LEVELS.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.label}
                </option>
              ))}
            </select>
            <p className="text-sm text-gray-500 mt-1">
              Words at or above this level are highlighted.
            </p>
          </div>
          <div>
            <label className="text-sm text-gray-500">Translation Language</label>
            <p className="font-medium">
              {languageName ?? user?.target_language ?? "Not set"}
            </p>
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

          <div className="flex items-center justify-between pt-2">
            <div>
              <p className="font-medium">Proactive Highlighting</p>
              <p className="text-sm text-gray-500">
                {user?.highlighting_enabled
                  ? "Difficult words are highlighted automatically"
                  : "Words are not highlighted; click any word to look it up"}
              </p>
            </div>
            <button
              role="switch"
              aria-checked={user?.highlighting_enabled ?? false}
              disabled={saving}
              onClick={handleToggleHighlighting}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none disabled:opacity-50 ${
                user?.highlighting_enabled ? "bg-blue-600" : "bg-gray-200"
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                  user?.highlighting_enabled ? "translate-x-6" : "translate-x-1"
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