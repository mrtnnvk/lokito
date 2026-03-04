"use client";

import { useEffect, useRef } from "react";
import L from "leaflet";
import type { MatchResponse } from "@/lib/types";

// Fix Leaflet default marker icon issue in bundlers
const defaultIcon = L.icon({
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});

const schoolIcon = L.icon({
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
  className: "hue-rotate-120", // green tint via CSS
});

interface MapViewProps {
  response: MatchResponse;
}

export default function MapView({ response }: MapViewProps) {
  const mapRef = useRef<L.Map | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    // Clean up previous map
    if (mapRef.current) {
      mapRef.current.remove();
      mapRef.current = null;
    }

    const school = response.result.school;
    const centerLat = school?.lat ?? 50.07;
    const centerLon = school?.lon ?? 14.47;

    const map = L.map(containerRef.current).setView([centerLat, centerLon], 14);
    mapRef.current = map;

    // OSM tile layer
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 19,
    }).addTo(map);

    // Matched school marker
    if (school?.lat && school?.lon) {
      L.marker([school.lat, school.lon], { icon: schoolIcon })
        .addTo(map)
        .bindPopup(
          `<strong>Vaše spádová škola</strong><br>${school.name}`
        )
        .openPopup();
    }

    // Nearby school markers
    for (const nearby of response.nearby) {
      if (nearby.lat && nearby.lon) {
        L.marker([nearby.lat, nearby.lon], { icon: defaultIcon })
          .addTo(map)
          .bindPopup(
            `${nearby.name}<br><small>${nearby.distance_km.toFixed(1)} km</small>`
          );
      }
    }

    // Fit bounds to show all markers
    const allCoords: [number, number][] = [];
    if (school?.lat && school?.lon) {
      allCoords.push([school.lat, school.lon]);
    }
    for (const nearby of response.nearby) {
      if (nearby.lat && nearby.lon) {
        allCoords.push([nearby.lat, nearby.lon]);
      }
    }
    if (allCoords.length > 1) {
      map.fitBounds(L.latLngBounds(allCoords), { padding: [30, 30] });
    }

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [response]);

  return <div ref={containerRef} className="w-full h-full" />;
}
