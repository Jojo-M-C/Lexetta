import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { api, type Language } from "../api";
import { useAuth } from "../auth";

export default function LanguageSelect() {
  const [languages, setLanguages] = useState<Language[]>([]);
  const [selected, setSelected] = useState("de");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { user, updateUser } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    api.listLanguages().then(setLanguages).catch((e) => setError(e.message));
  }, []);

  // The language is set once. If this user already has one, don't show the
  // screen again — send them on to wherever they belong.
  if (user?.target_language) {
    return <Navigate to={user.calibration_done ? "/library" : "/calibration"} replace />;
  }

  const handleContinue = async () => {
    setSaving(true);
    setError(null);
    try {
      const updated = await api.setLanguage(selected);
      updateUser({ target_language: updated.target_language });
      navigate("/calibration");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save language");
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="bg-white rounded-lg shadow p-8 w-full max-w-lg">
        <h1 className="text-xl font-bold text-gray-900 mb-1">
          Choose your translation language
        </h1>
        <p className="text-sm text-gray-500 mb-6">
          Word translations will be shown in this language. This is set once and
          can't be changed later.
        </p>

        {error && (
          <div className="bg-red-50 text-red-700 p-3 rounded mb-4 text-sm">
            Error: {error}
          </div>
        )}

        <label className="block text-sm font-medium text-gray-700 mb-2">
          Translation language
        </label>
        <select
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          disabled={languages.length === 0}
          className="w-full border border-gray-300 rounded p-2 mb-6"
        >
          {languages.map((l) => (
            <option key={l.code} value={l.code}>
              {l.name}
            </option>
          ))}
        </select>

        <button
          onClick={handleContinue}
          disabled={saving || languages.length === 0}
          className="w-full bg-blue-600 text-white rounded p-2 font-medium hover:bg-blue-700 disabled:bg-gray-300"
        >
          {saving ? "Saving…" : "Continue"}
        </button>
      </div>
    </div>
  );
}