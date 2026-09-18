import "./globals.css";
import { Manrope, JetBrains_Mono } from "next/font/google";
import { AppProviders } from "@/components/providers";

// Manrope carrega a interface (textos, títulos, botões): uma geométrica
// contemporânea, com um pouco mais de personalidade que a Inter padrão.
// JetBrains Mono é reservado para números — saldo, valores de transação,
// percentuais de meta — para dar a precisão "de extrato" que combina com
// um produto financeiro, e para os números alinharem em colunas (tabular).
const manrope = Manrope({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
  weight: ["400", "500", "600", "700"],
});

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="pt-br"
      suppressHydrationWarning
      className={`${manrope.variable} ${jetbrainsMono.variable}`}
    >
      <body className="bg-background text-foreground min-h-screen font-sans antialiased">
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
