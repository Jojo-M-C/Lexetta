import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { api, type CalibrationItem } from "../api";
import { useAuth } from "../auth";

export default function Calibration() {
  const [items, setItems] = useState<CalibrationItem[]>([]);
  const [index, setIndex] = useState(0);
  const [ratings, setRatings] = useState<Record<number, number>>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { user, updateUser } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    api.getCalibrationWords().then(setItems).catch((e) => setError(e.message));
  }, []);

  if (!user?.target_language) return <Navigate to="/onboarding" replace />;
  if (user?.calibration_done) return <Navigate to="/library" replace />;

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="bg-red-50 text-red-700 p-4 rounded">Error: {error}</div>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-gray-400">Loading…</div>
      </div>
    );
  }

  const item = items[index];
  const currentRating = ratings[item.id];
  const isLast = index === items.length - 1;
  const allRated = items.every((i) => ratings[i.id] !== undefined);

  const handleRate = (rating: number) => {
    setRatings((prev) => ({ ...prev, [item.id]: rating }));
  };

  const handleNext = () => {
    if (index < items.length - 1) setIndex((i) => i + 1);
  };

  const handleBack = () => {
    if (index > 0) setIndex((i) => i - 1);
  };

  const handleSubmit = async () => {
    if (!allRated) return;
    setSubmitting(true);
    try {
      await api.submitCalibration(
        Object.entries(ratings).map(([item_id, difficulty_rating]) => ({
          item_id: Number(item_id),
          difficulty_rating,
        }))
      );
      updateUser({ calibration_done: true });
      navigate("/library");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Submission failed");
      setSubmitting(false);
    }
  };

  const progress = Math.round(((index + 1) / items.length) * 100);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="bg-white rounded-lg shadow p-8 w-full max-w-lg">
        <h1 className="text-xl font-bold text-gray-900 mb-1">Quick calibration</h1>
        <p className="text-sm text-gray-500 mb-6">
          Rate how difficult each word feels to you. There are no right or wrong answers.
        </p>

        {/* Progress */}
        <div className="flex items-center gap-3 mb-6">
          <div className="flex-1 bg-gray-100 rounded-full h-2">
            <div
              className="bg-orange-200 h-2 rounded-full transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
          <span className="text-xs text-gray-400 whitespace-nowrap">
            {index + 1} / {items.length}
          </span>
        </div>

        {/* Word card */}
        <div className="border border-gray-200 rounded-lg p-6 mb-6 text-center">
          <p className="text-3xl font-semibold text-gray-900 mb-3">{item.word}</p>
          <p className="text-sm text-gray-500 italic">"{item.sentence}"</p>
        </div>

        {/* Rating buttons */}
        <p className="text-sm font-medium text-gray-700 mb-3 text-center">
          How difficult is this word for you?
        </p>
        <div className="flex justify-center gap-2 mb-2">
          {[1, 2, 3, 4, 5].map((n) => (
            <button
              key={n}
              onClick={() => handleRate(n)}
              className={`w-12 h-12 rounded-lg text-sm font-semibold transition-colors ${
                currentRating === n
                  ? "bg-orange-200 text-gray-900"
                  : "bg-gray-100 text-gray-700 hover:bg-orange-100"
              }`}
            >
              {n}
            </button>
          ))}
        </div>
        <div className="flex justify-between text-xs text-gray-400 mb-8 px-1">
          <span>Very easy</span>
          <span>Very hard</span>
        </div>

        {/* Navigation */}
        <div className="flex justify-between items-center">
          <button
            onClick={handleBack}
            disabled={index === 0}
            className="text-sm text-gray-500 hover:text-gray-700 disabled:opacity-30"
          >
            ← Back
          </button>

          {isLast ? (
            <button
              onClick={handleSubmit}
              disabled={!allRated || submitting}
              className="bg-blue-600 text-white rounded px-5 py-2 text-sm font-medium hover:bg-blue-700 disabled:bg-gray-300"
            >
              {submitting ? "Saving…" : "Finish"}
            </button>
          ) : (
            <button
              onClick={handleNext}
              disabled={currentRating === undefined}
              className="bg-blue-600 text-white rounded px-5 py-2 text-sm font-medium hover:bg-blue-700 disabled:bg-gray-300"
            >
              Next →
            </button>
          )}
        </div>

        {isLast && !allRated && (
          <p className="text-xs text-gray-400 text-center mt-3">
            Please rate all words before finishing.
          </p>
        )}
      </div>
    </div>
  );
}