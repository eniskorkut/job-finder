export interface CityCoordinates {
  key: string;
  name: string;
  lat: number;
  lng: number;
}

export const KNOWN_CITIES: Record<string, CityCoordinates> = {
  london: {
    key: "london",
    name: "LONDRA, BİRLEŞİK KRALLIK",
    lat: 51.5074,
    lng: -0.1278,
  },
  san_francisco: {
    key: "san_francisco",
    name: "SAN FRANCISCO, ABD",
    lat: 37.7749,
    lng: -122.4194,
  },
  new_york: {
    key: "new_york",
    name: "NEW YORK, ABD",
    lat: 40.7128,
    lng: -74.006,
  },
  berlin: {
    key: "berlin",
    name: "BERLİN, ALMANYA",
    lat: 52.52,
    lng: 13.405,
  },
  amsterdam: {
    key: "amsterdam",
    name: "AMSTERDAM, HOLLANDA",
    lat: 52.3676,
    lng: 4.9041,
  },
  tokyo: {
    key: "tokyo",
    name: "TOKYO, JAPONYA",
    lat: 35.6762,
    lng: 139.6503,
  },
  singapore: {
    key: "singapore",
    name: "SİNGAPUR",
    lat: 1.3521,
    lng: 103.8198,
  },
  dubai: {
    key: "dubai",
    name: "DUBAİ, BAE",
    lat: 25.2048,
    lng: 55.2708,
  },
  zurich: {
    key: "zurich",
    name: "ZÜRİH, İSVİÇRE",
    lat: 47.3769,
    lng: 8.5417,
  },
  paris: {
    key: "paris",
    name: "PARİS, FRANSA",
    lat: 48.8566,
    lng: 2.3522,
  },
  istanbul: {
    key: "istanbul",
    name: "İSTANBUL, TÜRKİYE",
    lat: 41.0082,
    lng: 28.9784,
  },
  remote: {
    key: "remote",
    name: "UZAKTAN / GLOBAL",
    lat: 20.0,
    lng: 0.0,
  },
};

export function resolveCityFromLocation(location: string | null | undefined): CityCoordinates {
  if (!location) return KNOWN_CITIES.remote;
  const lower = location.toLowerCase();

  if (
    lower.includes("london") ||
    lower.includes("londra") ||
    lower.includes("uk") ||
    lower.includes("united kingdom")
  ) {
    return KNOWN_CITIES.london;
  }
  if (
    lower.includes("san francisco") ||
    lower.includes("bay area") ||
    lower.includes("silicon valley") ||
    lower.includes("sf") ||
    lower.includes("california") ||
    lower.includes("ca")
  ) {
    return KNOWN_CITIES.san_francisco;
  }
  if (lower.includes("new york") || lower.includes("nyc") || lower.includes("manhattan")) {
    return KNOWN_CITIES.new_york;
  }
  if (lower.includes("berlin") || lower.includes("germany") || lower.includes("almanya")) {
    return KNOWN_CITIES.berlin;
  }
  if (lower.includes("amsterdam") || lower.includes("netherlands") || lower.includes("hollanda")) {
    return KNOWN_CITIES.amsterdam;
  }
  if (lower.includes("tokyo") || lower.includes("japan") || lower.includes("japonya")) {
    return KNOWN_CITIES.tokyo;
  }
  if (lower.includes("singapore") || lower.includes("singapur")) {
    return KNOWN_CITIES.singapore;
  }
  if (lower.includes("dubai") || lower.includes("uae") || lower.includes("bae")) {
    return KNOWN_CITIES.dubai;
  }
  if (
    lower.includes("zurich") ||
    lower.includes("zürich") ||
    lower.includes("switzerland") ||
    lower.includes("isviçre")
  ) {
    return KNOWN_CITIES.zurich;
  }
  if (lower.includes("paris") || lower.includes("france") || lower.includes("fransa")) {
    return KNOWN_CITIES.paris;
  }
  if (
    lower.includes("istanbul") ||
    lower.includes("türkiye") ||
    lower.includes("turkey") ||
    lower.includes("ankara") ||
    lower.includes("izmir")
  ) {
    return KNOWN_CITIES.istanbul;
  }

  return KNOWN_CITIES.remote;
}
