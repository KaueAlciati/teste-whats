/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/features/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/lib/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/contexts/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/hooks/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        border: "var(--border)",
        ring: "var(--ring)",
        card: {
          DEFAULT: "var(--card)",
          foreground: "var(--card-foreground)",
        },
        muted: {
          DEFAULT: "var(--muted)",
          foreground: "var(--muted-foreground)",
        },
        primary: {
          DEFAULT: "var(--primary)",
          foreground: "var(--primary-foreground)",
        },
        destructive: {
          DEFAULT: "var(--destructive)",
          foreground: "var(--destructive-foreground)",
        },
        // Paleta neutra reescrita com uma leve sombra esverdeada (em vez do
        // cinza puro do zinc padrão do Tailwind), pra tela escura ficar com
        // uma identidade própria em vez do "cinza-chumbo de qualquer SaaS".
        // Toda classe zinc-100...zinc-950 já usada no app herda isso de graça.
        zinc: {
          50: "hsl(150, 20%, 97%)",
          100: "hsl(150, 14%, 93%)",
          200: "hsl(150, 10%, 85%)",
          300: "hsl(150, 8%, 72%)",
          400: "hsl(150, 6%, 56%)",
          500: "hsl(152, 6%, 44%)",
          600: "hsl(154, 8%, 32%)",
          700: "hsl(156, 10%, 21%)",
          800: "hsl(158, 12%, 14%)",
          900: "hsl(160, 14%, 9%)",
          950: "hsl(162, 18%, 6%)",
        },
        // Verde de marca reafinado: mais profundo e um pouco mais teal que
        // o emerald padrão do Tailwind (#10b981), pra não parecer "verde
        // de template". Usado para dinheiro entrando, ações principais e
        // estado positivo.
        emerald: {
          50: "#ECFDF6",
          100: "#D1FAE8",
          200: "#A3F2D1",
          300: "#6BE0B3",
          400: "#3AC895",
          500: "#1BAF80",
          600: "#0E8D68",
          700: "#0B7054",
          800: "#0A5943",
          900: "#093F31",
          950: "#04241C",
        },
        // Vermelho-coral reafinado (menos "pink", mais alerta) para saídas
        // e ações destrutivas.
        rose: {
          300: "#FCA5AD",
          400: "#F97A88",
          500: "#EF4A5F",
          600: "#D6324B",
        },
        // Acento exclusivo para conteúdo gerado por IA (insights,
        // previsões). Fica deliberadamente fora da paleta financeira
        // (verde=dinheiro, vermelho=alerta) pra sinalizar "isto quem
        // disse foi a IA", não um dado bruto da sua conta.
        ai: {
          50: "#F2F0FF",
          100: "#E4E0FF",
          200: "#C9C0FF",
          300: "#A99CFB",
          400: "#8D7CF7",
          500: "#7562EF",
          600: "#5D48D6",
          700: "#4A38AD",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
  plugins: [],
};
