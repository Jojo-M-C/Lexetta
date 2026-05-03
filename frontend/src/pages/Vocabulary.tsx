import { useEffect, useState } from "react";
import { api, type VocabularyCard } from "../api";
import { Download } from "lucide-react";

export default function Vocabulary() {
  const [cards, setCards] = useState<VocabularyCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  useEffect(() => {
    api
      .listVocabulary()
      .then(setCards)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const filtered = search
    ? cards.filter((c) =>
        c.word.toLowerCase().includes(search.toLowerCase())
      )
    : cards;

  return (
    <div className="max-w-6xl mx-auto">
      <div className="flex justify-between items-center mb-8">
        <div className="flex items-baseline gap-4">
          <h1 className="text-3xl font-bold">Vocabulary</h1>
          <span className="text-sm text-gray-500">
            {cards.length} {cards.length === 1 ? "card" : "cards"}
          </span>
        </div>
            <div className="w-48">
              <button
                onClick={() => api.exportVocabulary()}
                disabled={cards.length === 0}
                className="w-full bg-blue-600 hover:bg-blue-700 text-white rounded-lg py-2.5 font-medium flex items-center justify-center gap-2 disabled:bg-gray-300 disabled:cursor-not-allowed"
              >
                <Download size={16} />
                Export to Anki
              </button>
            </div>
      </div>

      <input
        type="text"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search words..."
        className="w-full mb-6 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
      />

      {loading ? (
        <p className="text-gray-500">Loading...</p>
      ) : error ? (
        <p className="text-red-600">Error: {error}</p>
      ) : filtered.length === 0 ? (
        <div className="bg-white rounded-lg shadow p-6">
          <p className="text-gray-500">
            {cards.length === 0
              ? "No vocabulary yet. Click words while reading to add them here."
              : "No words match your search."}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((card) => (
            <div
              key={card.id}
              className="bg-white rounded-lg shadow-sm border border-gray-200 grid grid-cols-2 divide-x divide-gray-200"
            >
              {/* Front: word + context */}
              <div className="p-5">
                <h3 className="font-bold text-lg mb-2">{card.word}</h3>
                <p className="text-sm text-gray-600 italic leading-relaxed">
                  "{card.context}"
                </p>
              </div>

              {/* Back: translation */}
              <div className="p-5 flex flex-col justify-center">
                {card.translation ? (
                  <p className="text-xl font-medium text-gray-900">
                    {card.translation}
                  </p>
                ) : (
                  <p className="text-gray-400 italic">No translation</p>
                )}
                <p className="text-xs text-gray-400 mt-2">
                  {new Date(card.created_at).toLocaleDateString()}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}