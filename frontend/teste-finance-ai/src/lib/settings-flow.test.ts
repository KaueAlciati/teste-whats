import { describe, expect, it, vi } from "vitest";

import {
  formatWhatsappPhone,
  logoutAndRedirect,
  REGIONAL_PREFERENCES,
} from "./settings-flow";


describe("fluxo de Configurações", () => {
  it("formata o WhatsApp brasileiro vinculado", () => {
    expect(formatWhatsappPhone("5515999999999")).toBe("+55 (15) 99999-9999");
  });

  it("mantém as preferências informativas sem depender de API opcional", () => {
    expect(REGIONAL_PREFERENCES).toEqual({ currency: "BRL", locale: "pt-BR" });
  });

  it("remove a sessão antes de redirecionar no logout", async () => {
    const calls: string[] = [];
    const logout = vi.fn(async () => {
      calls.push("logout");
    });
    const redirect = vi.fn((path: string) => {
      calls.push(`redirect:${path}`);
    });

    await logoutAndRedirect(logout, redirect);

    expect(calls).toEqual(["logout", "redirect:/login"]);
    expect(logout).toHaveBeenCalledOnce();
    expect(redirect).toHaveBeenCalledWith("/login");
  });
});
