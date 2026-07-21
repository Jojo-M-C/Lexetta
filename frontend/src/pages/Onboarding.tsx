import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { api, type Language } from "../api";
import { useAuth } from "../auth";
import { DEFAULT_READING_LEVEL, READING_LEVELS } from "../lib/levels";

export default function Onboarding() {
  const [languages, setLanguages] = useState<Language[]>([]);
  const [language, setLanguage] = useState("de");
  const { user, updateUser } = useAuth();
  const [level, setLevel] = useState(user?.reading_level ?? DEFAULT_READING_LEVEL);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    api.listLanguages().then(setLanguages).catch((e) => setError(e.message));
  }, []);

  // The target language is set once, so it doubles as the marker for "onboarding
  // done". If this user already has one, don't show the screen again — send them
  // on to wherever they belong.
  if (user?.target_language) {
    return <Navigate to={user.calibration_done ? "/library" : "/calibration"} replace />;
  }

  const handleContinue = async () => {
    setSaving(true);
    setError(null);
    try {
      // Level first: it's idempotent, whereas setting the language flips the gate
      // above. If a later call fails the user lands back here and can retry.
      const withLevel = await api.updateMe({ reading_level: level });
      updateUser({ reading_level: withLevel.reading_level });
      // Assign the level-matched study text before the language flips the gate,
      // so a failure here leaves the user on onboarding to retry. Idempotent.
      await api.assignStudyText();
      const withLanguage = await api.setLanguage(language);
      updateUser({ target_language: withLanguage.target_language });
      navigate("/calibration");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save your settings");
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="bg-white rounded-lg shadow p-8 w-full max-w-lg">
        <h1 className="text-xl font-bold text-gray-900 mb-1">Welcome to Lexetta</h1>
        <p className="text-sm text-gray-500 mb-6">
          Set these up before your calibration.
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
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
          disabled={languages.length === 0}
          className="w-full border border-gray-300 rounded p-2"
        >
          {languages.map((l) => (
            <option key={l.code} value={l.code}>
              {l.name}
            </option>
          ))}
        </select>
        <p className="text-xs text-gray-400 mt-2 mb-6">
          Word translations will be shown in this language. This is set once and
          can't be changed later.
        </p>

        <label className="block text-sm font-medium text-gray-700 mb-2">
          Reading level
        </label>
        <select
          value={level}
          onChange={(e) => setLevel(e.target.value)}
          className="w-full border border-gray-300 rounded p-2"
        >
          {READING_LEVELS.map((l) => (
            <option key={l.code} value={l.code}>
              {l.label}
            </option>
          ))}
        </select>
        <p className="text-xs text-gray-400 mt-2 mb-6">
          Words at or above this level get highlighted. You can change it later in
          your profile.
        </p>

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
