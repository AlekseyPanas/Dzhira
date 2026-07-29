// The DerivedDicts wire constants — the frontend mirror of backend/web/registry.py (enum member
// names are the shared wire constants; keep the two files in sync).

export const DerivedDicts = {
    DB: "DB",
} as const;

export type TDerivedDictName = (typeof DerivedDicts)[keyof typeof DerivedDicts];
