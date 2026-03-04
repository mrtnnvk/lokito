"use client";

import { useEffect, useState } from "react";

interface EmailLinkProps {
  email: string | null | undefined;
  className?: string;
}

/**
 * Renders a mailto link only after client-side hydration.
 * Server-rendered HTML contains just a static placeholder — bots scraping
 * the HTML or SSR output never see the actual address.
 */
export default function EmailLink({ email, className = "text-sm text-gray-600" }: EmailLinkProps) {
  const [address, setAddress] = useState<string | null>(null);

  useEffect(() => {
    if (email) setAddress(email);
  }, [email]);

  if (!email) return null;

  // Before hydration: show inert placeholder with no address
  if (!address) {
    return (
      <span className={className} aria-label="email">
        ✉ email
      </span>
    );
  }

  return (
    <a href={`mailto:${address}`} className={className}>
      {address}
    </a>
  );
}
