export type QueryKey = readonly unknown[];

export function createFeatureQueryKeys(feature: string) {
  const base = [feature] as const;

  return {
    all: base,
    list: <P extends Record<string, unknown> | undefined>(params?: P) =>
      (params ? [...base, "list", params] : [...base, "list"]) as QueryKey,
    detail: (id: string | number) => [...base, "detail", id] as QueryKey,
  };
}
