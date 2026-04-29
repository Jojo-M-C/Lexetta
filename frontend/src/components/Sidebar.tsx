import { NavLink } from "react-router-dom";
import { BookOpen, BookMarked, User } from "lucide-react";

const navItems = [
  { to: "/library", label: "Library", icon: BookOpen },
  { to: "/vocabulary", label: "Vocabulary", icon: BookMarked }
];

export default function Sidebar() {
  return (
    <aside className="w-64 bg-white border-r border-gray-200 flex flex-col">
      {/* Logo */}
      <div className="p-6 flex items-center gap-3">
        <div className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center">
          <BookOpen className="text-white" size={20} />
        </div>
        <span className="text-xl font-semibold">Lexetta</span>
      </div>

      {/* Nav links */}
      <nav className="flex-1 px-2">
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-2.5 rounded-lg mb-1 text-sm font-medium ${
                isActive
                  ? "bg-blue-50 text-blue-600"
                  : "text-gray-700 hover:bg-gray-100"
              }`
            }
          >
            <Icon size={18} />
            {label}
          </NavLink>
        ))}

        {/* Profile separator and link */}
        <div className="border-t border-gray-200 my-4" />
        <NavLink
          to="/profile"
          className={({ isActive }) =>
            `flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium ${
              isActive
                ? "bg-blue-50 text-blue-600"
                : "text-gray-700 hover:bg-gray-100"
            }`
          }
        >
          <User size={18} />
          Profile
        </NavLink>
      </nav>
    </aside>
  );
}