export interface NamedConnector {
  name: string;
}

const PREFERRED_CONNECTOR_ORDER = ["priceshape", "drs", "creditsafe", "ga4"];

export function orderConnectors<T extends NamedConnector>(connectors: T[]): T[] {
  const rank = new Map(
    PREFERRED_CONNECTOR_ORDER.map((name, index) => [name, index]),
  );

  return [...connectors].sort((a, b) => {
    const aRank = rank.get(a.name) ?? Number.MAX_SAFE_INTEGER;
    const bRank = rank.get(b.name) ?? Number.MAX_SAFE_INTEGER;
    return aRank - bRank || a.name.localeCompare(b.name);
  });
}