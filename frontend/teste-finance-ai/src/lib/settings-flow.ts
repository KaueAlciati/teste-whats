export const REGIONAL_PREFERENCES = {
  currency: "BRL",
  locale: "pt-BR",
} as const;

export function formatWhatsappPhone(phone?: string): string {
  if (!phone) return "Não informado";
  const digits = phone.replace(/\D/g, "");

  if (digits.length === 13 && digits.startsWith("55")) {
    return `+55 (${digits.slice(2, 4)}) ${digits.slice(4, 9)}-${digits.slice(9)}`;
  }
  if (digits.length === 12 && digits.startsWith("55")) {
    return `+55 (${digits.slice(2, 4)}) ${digits.slice(4, 8)}-${digits.slice(8)}`;
  }
  return phone.startsWith("+") ? phone : `+${phone}`;
}

export async function logoutAndRedirect(
  logout: () => Promise<void>,
  redirect: (path: string) => void,
): Promise<void> {
  await logout();
  redirect("/login");
}
