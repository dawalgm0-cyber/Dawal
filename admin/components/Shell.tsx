"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { clearToken, getToken } from "@/lib/api";

const NAV = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/bookings", label: "Bookings" },
  { href: "/drivers", label: "Drivers" },
  { href: "/credits", label: "Credits" },
  { href: "/areas", label: "Areas & Captains" },
  { href: "/disputes", label: "Disputes" },
  { href: "/riders", label: "Riders" },
  { href: "/analytics", label: "Analytics" },
  { href: "/compliance", label: "Compliance" },
  { href: "/settings", label: "Settings" },
];

export default function Shell({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
    } else {
      setReady(true);
    }
  }, [router]);

  if (!ready) return <div className="spinner" style={{ padding: "2rem" }}>Loading…</div>;

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          DAW<span>AL</span>
        </div>
        {NAV.map((n) => (
          <Link
            key={n.href}
            href={n.href}
            className={`navlink ${pathname.startsWith(n.href) ? "active" : ""}`}
          >
            {n.label}
          </Link>
        ))}
        <div className="spacer" />
        <button
          className="logout"
          onClick={() => {
            clearToken();
            router.replace("/login");
          }}
        >
          Sign out
        </button>
      </aside>
      <main className="main">
        <div className="topbar">
          <h1>{title}</h1>
        </div>
        {children}
      </main>
    </div>
  );
}
