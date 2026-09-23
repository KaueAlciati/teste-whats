import { describe, expect, it } from "vitest";

import type { FinancialProfileInput } from "./api";
import {
  formatTreasurySelicRate,
  isCompleteProfile,
  onboardingProgress,
  resolveInsightsView,
  updateProfileAnswer,
} from "./insights-flow";


const completeProfile: FinancialProfileInput = {
  main_goal: "emergency_reserve",
  investment_horizon: "one_to_three_years",
  risk_profile: "conservative",
  liquidity_need: "high",
  has_debts: false,
  income_type: "fixed",
  main_priority: "increase_savings",
};

describe("fluxo de Insights", () => {
  it("apresenta a taxa do Tesouro Selic como ágio ou deságio sobre a Selic", () => {
    expect(formatTreasurySelicRate(0.01)).toBe("Selic + 0,01% a.a.");
    expect(formatTreasurySelicRate(-0.03)).toBe("Selic − 0,03% a.a.");
  });

  it("mostra onboarding para usuário novo", () => {
    expect(
      resolveInsightsView({
        loading: false,
        fatalError: false,
        hasProfile: false,
        editingProfile: false,
        transitioning: false,
        hasAnalysis: false,
      }),
    ).toBe("onboarding");
  });

  it("calcula o progresso das sete etapas", () => {
    expect(onboardingProgress(0, 7)).toBeCloseTo(14.2857, 3);
    expect(onboardingProgress(6, 7)).toBe(100);
  });

  it("preserva respostas ao avançar e voltar", () => {
    const first = updateProfileAnswer({}, "main_goal", "emergency_reserve");
    const second = updateProfileAnswer(first, "has_debts", false);

    expect(second.main_goal).toBe("emergency_reserve");
    expect(second.has_debts).toBe(false);
  });

  it("só permite finalizar com todas as respostas", () => {
    expect(isCompleteProfile({ main_goal: "emergency_reserve" })).toBe(false);
    expect(isCompleteProfile(completeProfile)).toBe(true);
  });

  it("mostra dashboard depois do onboarding mesmo sem transações", () => {
    expect(
      resolveInsightsView({
        loading: false,
        fatalError: false,
        hasProfile: true,
        editingProfile: false,
        transitioning: false,
        hasAnalysis: true,
      }),
    ).toBe("dashboard");
  });

  it("trata loading, erro, preparação e atualização de perfil", () => {
    const base = {
      loading: false,
      fatalError: false,
      hasProfile: true,
      editingProfile: false,
      transitioning: false,
      hasAnalysis: true,
    };

    expect(resolveInsightsView({ ...base, loading: true })).toBe("loading");
    expect(
      resolveInsightsView({ ...base, fatalError: true, hasProfile: false }),
    ).toBe("error");
    expect(resolveInsightsView({ ...base, transitioning: true })).toBe(
      "preparing",
    );
    expect(resolveInsightsView({ ...base, editingProfile: true })).toBe(
      "onboarding",
    );
  });
});
