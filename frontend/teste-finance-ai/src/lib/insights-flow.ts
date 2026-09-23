import type { FinancialProfile, FinancialProfileInput } from "./api";


const PERCENTAGE = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
});


export const FINANCIAL_PROFILE_FIELDS: (keyof FinancialProfileInput)[] = [
  "main_goal",
  "investment_horizon",
  "risk_profile",
  "liquidity_need",
  "has_debts",
  "income_type",
  "main_priority",
];

export type InsightsView =
  | "loading"
  | "error"
  | "onboarding"
  | "preparing"
  | "dashboard";

export function resolveInsightsView(state: {
  loading: boolean;
  fatalError: boolean;
  hasProfile: boolean;
  editingProfile: boolean;
  transitioning: boolean;
  hasAnalysis: boolean;
}): InsightsView {
  if (state.loading) return "loading";
  if (state.fatalError) return "error";
  if (!state.hasProfile || state.editingProfile) return "onboarding";
  if (state.transitioning || !state.hasAnalysis) return "preparing";
  return "dashboard";
}

export function onboardingProgress(stepIndex: number, totalSteps: number): number {
  if (totalSteps <= 0) return 0;
  const safeIndex = Math.min(Math.max(stepIndex, 0), totalSteps - 1);
  return ((safeIndex + 1) / totalSteps) * 100;
}

export function updateProfileAnswer(
  answers: Partial<FinancialProfileInput>,
  key: keyof FinancialProfileInput,
  value: string | boolean,
): Partial<FinancialProfileInput> {
  return { ...answers, [key]: value };
}

export function isCompleteProfile(
  value: Partial<FinancialProfileInput>,
): value is FinancialProfileInput {
  return FINANCIAL_PROFILE_FIELDS.every((field) => value[field] !== undefined);
}

export function profileToInput(
  profile: FinancialProfile,
): FinancialProfileInput {
  return {
    main_goal: profile.main_goal,
    investment_horizon: profile.investment_horizon,
    risk_profile: profile.risk_profile,
    liquidity_need: profile.liquidity_need,
    has_debts: profile.has_debts,
    income_type: profile.income_type,
    main_priority: profile.main_priority,
  };
}

export function formatTreasurySelicRate(selicSpread: number | null): string {
  if (selicSpread === null) return "Indisponível";
  const operator = selicSpread >= 0 ? "+" : "−";
  return `Selic ${operator} ${PERCENTAGE.format(Math.abs(selicSpread))}% a.a.`;
}
