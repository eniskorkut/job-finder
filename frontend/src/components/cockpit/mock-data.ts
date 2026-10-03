import { KNOWN_CITIES } from "./city-coordinates";
import type { CityHub, Dossier } from "./types";

/**
 * Clean, lightweight city database initialized with static geographic coordinates.
 * Mock dossiers are eliminated in production to slash bundle size.
 */
export const initialCityDatabase: Record<string, CityHub> = Object.fromEntries(
  Object.entries(KNOWN_CITIES).map(([key, city]) => [
    key,
    {
      name: city.name,
      lat: city.lat,
      lng: city.lng,
      count: 0,
      dossiers: [],
    },
  ])
);

export function getAllDossiersFromDatabase(db: Record<string, CityHub>): Dossier[] {
  const all: Dossier[] = [];
  Object.entries(db).forEach(([key, city]) => {
    city.dossiers.forEach((d) => {
      all.push({ ...d, cityKey: key, cityName: city.name });
    });
  });
  return all;
}

export const CITY_DATABASE = initialCityDatabase;
