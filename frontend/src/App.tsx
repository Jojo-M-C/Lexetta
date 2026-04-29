import { useEffect, useState } from "react";

interface User {
  id: number;
  username: string;
  reading_level: string | null;
}

function App() {
  const [users, setUsers] = useState<User[]>([]);

  useEffect(() => {
    fetch("http://localhost:8000/users")
      .then((res) => res.json())
      .then(setUsers);
  }, []);

  return (
    <div className="p-8">
      <h1 className="text-3xl font-bold mb-4 text-blue-600">Users</h1>
      <ul className="space-y-2">
        {users.map((u) => (
          <li key={u.id} className="p-3 bg-gray-100 rounded">
            {u.username} ({u.reading_level ?? "no level"})
          </li>
        ))}
      </ul>
    </div>
  );
}

export default App;