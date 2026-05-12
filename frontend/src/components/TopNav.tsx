import { NavLink } from "react-router-dom";
import "../styles/TopNav.css";

interface TopNavLink {
  to: string;
  label: string;
  end?: boolean;
}

const NAV_LINKS: TopNavLink[] = [
  { to: "/", label: "Home", end: true },
  { to: "/predictions", label: "Prediction" },
  { to: "/live", label: "Live Timing" },
  { to: "/about", label: "About Us" },
];

interface TopNavProps {
  variant?: "overlay" | "solid";
}

export default function TopNav({ variant = "overlay" }: TopNavProps) {
  return (
    <nav className={`topnav topnav-${variant}`} aria-label="Primary">
      <div className="topnav-brand">
        <span className="topnav-brand-mark">F1</span>
        <span className="topnav-brand-text">ZOOM</span>
      </div>
      <ul className="topnav-links">
        {NAV_LINKS.map((link) => (
          <li key={link.to}>
            <NavLink
              to={link.to}
              end={link.end}
              className={({ isActive }) =>
                `topnav-link${isActive ? " is-active" : ""}`
              }
            >
              {link.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
