"use client";

import { useState, useMemo, useRef, useEffect } from "react";
import { normalizeStreet } from "@/lib/normalize";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";

interface AddressInputProps {
  streets: string[];
  onSearch: (street: string, number: number) => void;
  loading: boolean;
}

export default function AddressInput({
  streets,
  onSearch,
  loading,
}: AddressInputProps) {
  const [streetInput, setStreetInput] = useState("");
  const [numberInput, setNumberInput] = useState("");
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const suggestionsRef = useRef<HTMLUListElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Filter streets based on input (Czech-aware)
  const suggestions = useMemo(() => {
    if (streetInput.length < 1) return [];
    const norm = normalizeStreet(streetInput);
    return streets
      .filter((s) => normalizeStreet(s).includes(norm))
      .slice(0, 8);
  }, [streetInput, streets]);

  // Keyboard navigation in suggestions
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!showSuggestions || suggestions.length === 0) {
      if (e.key === "Enter") {
        handleSubmit();
      }
      return;
    }

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((i) => Math.min(i + 1, suggestions.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && selectedIndex >= 0) {
      e.preventDefault();
      selectStreet(suggestions[selectedIndex]);
    } else if (e.key === "Escape") {
      setShowSuggestions(false);
    }
  };

  const selectStreet = (street: string) => {
    setStreetInput(street);
    setShowSuggestions(false);
    setSelectedIndex(-1);
    // Focus number input after selecting street
    setTimeout(() => {
      document.getElementById("number-input")?.focus();
    }, 50);
  };

  const handleSubmit = () => {
    const num = parseInt(numberInput, 10);
    if (!streetInput.trim()) return;
    if (isNaN(num) || num < 1) return;
    onSearch(streetInput.trim(), num);
  };

  // Close suggestions when clicking outside
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (
        inputRef.current &&
        !inputRef.current.contains(e.target as Node) &&
        suggestionsRef.current &&
        !suggestionsRef.current.contains(e.target as Node)
      ) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
      <div className="flex flex-col sm:flex-row gap-3">
        {/* Street input with autocomplete */}
        <div className="relative flex-1">
          <Label htmlFor="street-input" className="mb-1">Ulice</Label>
          <Input
            ref={inputRef}
            id="street-input"
            type="text"
            value={streetInput}
            onChange={(e) => {
              setStreetInput(e.target.value);
              setShowSuggestions(true);
              setSelectedIndex(-1);
            }}
            onFocus={() => streetInput.length >= 1 && setShowSuggestions(true)}
            onKeyDown={handleKeyDown}
            placeholder="např. Průběžná"
            autoComplete="off"
          />

          {/* Suggestions dropdown */}
          {showSuggestions && suggestions.length > 0 && (
            <ul
              ref={suggestionsRef}
              className="absolute z-50 w-full mt-1 bg-white border border-gray-200
                         rounded-lg shadow-lg max-h-60 overflow-auto"
            >
              {suggestions.map((street, i) => (
                <li
                  key={street}
                  className={`px-4 py-2 cursor-pointer text-sm
                    ${i === selectedIndex
                      ? "bg-blue-50 text-blue-900"
                      : "text-gray-700 hover:bg-gray-50"
                    }`}
                  onMouseDown={() => selectStreet(street)}
                  onMouseEnter={() => setSelectedIndex(i)}
                >
                  {street}
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Number input */}
        <div className="w-full sm:w-32">
          <Label htmlFor="number-input" className="mb-1">Číslo</Label>
          <Input
            id="number-input"
            type="number"
            min="1"
            value={numberInput}
            onChange={(e) => setNumberInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
            placeholder="č.o."
          />
        </div>

        {/* Submit button */}
        <div className="flex items-end">
          <Button
            onClick={handleSubmit}
            disabled={loading || !streetInput.trim() || !numberInput}
            className="w-full sm:w-auto"
          >
            {loading ? "Hledám…" : "Najít školu"}
          </Button>
        </div>
      </div>

      <p className="mt-3 text-xs text-gray-400">
        Zadejte ulici a číslo orientační (to &quot;červené&quot; na domě).
      </p>
    </div>
  );
}
