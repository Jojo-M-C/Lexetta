import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type User } from "../api";
import { useAuth } from "../auth";

export default function Login() {
  const [users, setUsers] = useState<User[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { login } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    api
      .listUsers()
      .then((users) => {
        setUsers(users);
        if (users.length > 0) setSelectedId(users[0].id);
      })
      .catch((e) => setError(e.message));
  }, []);

  const handleLogin = () => {
    const user = users.find((u) => u.id === selectedId);
    if (!user) return;
    login(user);
    navigate("/library");
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="bg-white rounded-lg shadow p-8 w-96">
        <h1 className="text-2xl font-bold mb-6">Lexetta</h1>

        {error && (
          <div className="bg-red-50 text-red-700 p-3 rounded mb-4 text-sm">
            Error: {error}
          </div>
        )}

        <label className="block text-sm font-medium text-gray-700 mb-2">
          Choose a learner profile
        </label>
        <select
          value={selectedId ?? ""}
          onChange={(e) => setSelectedId(Number(e.target.value))}
          className="w-full border border-gray-300 rounded p-2 mb-6"
        >
          {users.map((u) => (
            <option key={u.id} value={u.id}>
              {u.username} ({u.reading_level ?? "no level"})
            </option>
          ))}
        </select>

        <button
          onClick={handleLogin}
          disabled={selectedId === null}
          className="w-full bg-blue-600 text-white rounded p-2 font-medium hover:bg-blue-700 disabled:bg-gray-300"
        >
          Continue
        </button>
      </div>
    </div>
  );
}