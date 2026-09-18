"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  BrainCircuit,
  LineChart,
  Target,
  Bell,
  ShieldCheck,
  Wallet,
  Sparkles,
  UserPlus,
  ListChecks,
  TrendingUp,
  WifiOff,
  Lock,
  ChevronDown,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/contexts/ToastContext";

const MODULES = [
  {
    icon: LineChart,
    title: "Dashboard financeiro",
    description:
      "Saldo, entradas e saídas com a tendência de cada um mês a mês — sem precisar abrir planilha nenhuma.",
    color: "text-emerald-500 bg-emerald-500/10",
  },
  {
    icon: Wallet,
    title: "Transações organizadas",
    description:
      "Registre, edite e categorize entradas e saídas em poucos cliques, com histórico completo e pesquisável.",
    color: "text-teal-400 bg-teal-400/10",
  },
  {
    icon: Target,
    title: "Metas com progresso real",
    description:
      "Crie metas, registre depósitos e acompanhe o percentual concluído até bater o objetivo.",
    color: "text-blue-400 bg-blue-400/10",
  },
  {
    icon: BrainCircuit,
    title: "Insights a partir do seu histórico",
    description:
      "Categoria de gasto dominante, despesas recorrentes e mudanças de comportamento — cada análise vem com a conta de onde veio o número, não só a conclusão.",
    color: "text-ai-400 bg-ai-500/10",
  },
  {
    icon: Bell,
    title: "Central de notificações",
    description:
      "Avisos de gastos fora do padrão e atualizações de metas reunidos em um só lugar, sem precisar caçar informação.",
    color: "text-amber-400 bg-amber-400/10",
  },
  {
    icon: ShieldCheck,
    title: "Conta protegida",
    description:
      "Autenticação real e dados isolados por conta — ninguém além de você tem acesso às suas finanças.",
    color: "text-rose-400 bg-rose-400/10",
  },
];

const DIFFERENTIATORS = [
  {
    icon: BrainCircuit,
    title: "Insights de verdade, não genéricos",
    description:
      "Nada de frases prontas: cada recomendação é calculada em cima do seu próprio histórico de transações.",
  },
  {
    icon: Lock,
    title: "Isolamento real entre contas",
    description:
      "Cada usuário só acessa os próprios dados — validado explicitamente, não é só uma promessa.",
  },
  {
    icon: WifiOff,
    title: "Continua funcionando sem conexão",
    description:
      "Se você ficar sem conexão, o sistema segue operando localmente no seu navegador até a conexão voltar.",
  },
];

const HOW_IT_WORKS = [
  {
    icon: UserPlus,
    step: "1",
    title: "Crie sua conta",
    description: "Leva menos de um minuto — só nome, e-mail e senha.",
  },
  {
    icon: ListChecks,
    step: "2",
    title: "Registre suas transações",
    description: "Entradas e saídas, cada uma com sua categoria.",
  },
  {
    icon: TrendingUp,
    step: "3",
    title: "Acompanhe metas e insights",
    description: "O sistema aprende com seu histórico e mostra o que importa.",
  },
];

const FAQ = [
  {
    question: "Preciso pagar para usar o Finance.AI?",
    answer: "Não. Você pode criar sua conta e usar o sistema gratuitamente.",
  },
  {
    question: "Meus dados financeiros ficam visíveis para outras pessoas?",
    answer:
      "Não. Cada conta tem autenticação própria e acesso isolado aos próprios dados — isso já foi testado explicitamente com múltiplas contas simultâneas.",
  },
  {
    question: "Como os insights são gerados?",
    answer:
      "A partir do histórico real das suas transações: categoria de gasto dominante, despesas recorrentes e mudanças de comportamento mês a mês. Cada um vem com a comparação entre os períodos e o que mais contribuiu para a mudança — não são recomendações genéricas.",
  },
  {
    question: "O sistema funciona sem internet?",
    answer:
      "Se você ficar sem conexão, o Finance.AI passa a funcionar localmente no seu navegador automaticamente, para você não ficar sem acesso.",
  },
  {
    question: "Funciona bem no celular?",
    answer: "Sim, a interface é totalmente responsiva, do dashboard ao editor de transações.",
  },
];

const TRUST_BADGES = ["Grátis para começar", "Sem cartão de crédito", "Dados isolados por conta"];

export default function LandingPage() {
  const { session, loading, login } = useAuth();
  const { addToast } = useToast();
  const router = useRouter();
  const [demoLoading, setDemoLoading] = useState(false);
  const [openFaq, setOpenFaq] = useState<number | null>(0);

  // Quem já está logado não precisa ver a landing — manda direto pro app
  useEffect(() => {
    if (!loading && session) {
      router.replace("/dashboard");
    }
  }, [loading, session, router]);

  async function handleTryDemo() {
    setDemoLoading(true);
    try {
      await login("demo@finance.ai", "demo123456");
      router.push("/dashboard");
    } catch {
      addToast(
        "error",
        "Não foi possível abrir a demonstração agora. Tente novamente em instantes.",
      );
    } finally {
      setDemoLoading(false);
    }
  }

  if (loading || session) return null;

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-50">
      {/* Header */}
      <header className="border-b border-zinc-800/60 sticky top-0 z-30 bg-zinc-950/80 backdrop-blur-md">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
            <div className="w-7 h-7 sm:w-8 sm:h-8 rounded-lg bg-emerald-500 flex items-center justify-center shadow-lg shadow-emerald-500/20 shrink-0">
              <span className="text-black font-bold text-xs sm:text-sm">$</span>
            </div>
            <span className="font-bold tracking-tight text-emerald-500 text-sm sm:text-base whitespace-nowrap">
              FINANCE.AI
            </span>
          </div>
          <nav className="hidden md:flex items-center gap-7">
            <a href="#funcionalidades" className="text-sm text-zinc-400 hover:text-zinc-100 transition-colors">
              Funcionalidades
            </a>
            <a href="#como-funciona" className="text-sm text-zinc-400 hover:text-zinc-100 transition-colors">
              Como funciona
            </a>
            <a href="#faq" className="text-sm text-zinc-400 hover:text-zinc-100 transition-colors">
              Dúvidas
            </a>
          </nav>
          <div className="flex items-center gap-2 sm:gap-4 shrink-0">
            <Link
              href="/login"
              className="text-xs sm:text-sm text-zinc-400 hover:text-zinc-100 transition-colors whitespace-nowrap"
            >
              Entrar
            </Link>
            <Link
              href="/register"
              className="text-xs sm:text-sm bg-emerald-600 hover:bg-emerald-500 text-white font-semibold px-3 py-1.5 sm:px-4 sm:py-2 rounded-lg transition-colors whitespace-nowrap"
            >
              <span className="sm:hidden">Criar conta</span>
              <span className="hidden sm:inline">Criar conta grátis</span>
            </Link>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="max-w-6xl mx-auto px-4 sm:px-6 pt-16 sm:pt-24 pb-10 sm:pb-14 text-center animate-fade-slide-up">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-medium mb-6">
          <Sparkles size={13} />
          Controle financeiro pessoal com insights baseados no seu histórico real
        </div>
        <h1 className="text-3xl sm:text-5xl font-bold tracking-tight leading-tight max-w-3xl mx-auto">
          Entenda para onde vai o seu dinheiro —{" "}
          <span className="text-emerald-500">antes que ele acabe.</span>
        </h1>
        <p className="text-zinc-400 text-base sm:text-lg mt-5 max-w-xl mx-auto">
          Transações, metas e projeções em um só painel, feito para quem quer
          sair da planilha sem perder o controle. Sem letra miúda, sem
          complicação.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 mt-9">
          <Link
            href="/register"
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold px-6 py-3 rounded-xl transition-all active:scale-[0.98] shadow-lg shadow-emerald-500/20"
          >
            Criar conta grátis
            <ArrowRight size={18} />
          </Link>
          <a
            href="#como-funciona"
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 text-zinc-200 font-semibold px-6 py-3 rounded-xl transition-all active:scale-[0.98]"
          >
            Ver como funciona
          </a>
        </div>

        {/* Selos de confiança — só afirmações reais, sem métricas inventadas */}
        <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 mt-8 text-xs text-zinc-500">
          {TRUST_BADGES.map((badge) => (
            <span key={badge} className="inline-flex items-center gap-1.5">
              <span className="w-1 h-1 rounded-full bg-emerald-500" />
              {badge}
            </span>
          ))}
        </div>
      </section>

      {/* Preview ilustrativo do produto */}
      <section className="max-w-5xl mx-auto px-4 sm:px-6 pb-16 sm:pb-24">
        <div className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-3 sm:p-4 shadow-2xl shadow-black/40">
          <div className="rounded-xl bg-zinc-950 border border-zinc-800/80 overflow-hidden">
            <div className="flex items-center gap-1.5 px-4 py-3 border-b border-zinc-800/60">
              <span className="w-2.5 h-2.5 rounded-full bg-rose-500/70" />
              <span className="w-2.5 h-2.5 rounded-full bg-amber-500/70" />
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500/70" />
            </div>
            <div className="p-4 sm:p-6 grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
              <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
                <p className="text-xs text-zinc-500">Saldo Total</p>
                <p className="text-xl sm:text-2xl font-bold mt-1">R$ 5.207,30</p>
                <p className="text-xs text-emerald-500 mt-1">+12% vs. mês anterior</p>
              </div>
              <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
                <p className="text-xs text-zinc-500">Entradas</p>
                <p className="text-xl sm:text-2xl font-bold mt-1 text-emerald-500">R$ 7.700,00</p>
                <p className="text-xs text-zinc-500 mt-1">Salário + renda extra</p>
              </div>
              <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
                <p className="text-xs text-zinc-500">Saídas</p>
                <p className="text-xl sm:text-2xl font-bold mt-1">R$ 3.190,50</p>
                <p className="text-xs text-zinc-500 mt-1">Dentro da média mensal</p>
              </div>
            </div>
            <div className="px-4 sm:px-6 pb-5">
              <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4 flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-ai-500/10 flex items-center justify-center shrink-0">
                  <BrainCircuit size={18} className="text-ai-400" />
                </div>
                <div>
                  <p className="text-sm font-semibold">Meta &quot;Viagem para o Nordeste&quot;</p>
                  <p className="text-xs text-zinc-500">31% concluída · faltam R$ 2.750,00</p>
                </div>
              </div>
            </div>
          </div>
        </div>
        <p className="text-center text-xs text-zinc-500 mt-4">
          Quer ver com dados reais sem criar conta?{" "}
          <button
            onClick={handleTryDemo}
            disabled={demoLoading}
            className="text-zinc-400 hover:text-emerald-400 underline underline-offset-2 transition-colors disabled:opacity-50"
          >
            {demoLoading ? "Abrindo demonstração..." : "Acessar a conta de demonstração"}
          </button>
        </p>
      </section>

      {/* Como funciona */}
      <section id="como-funciona" className="max-w-5xl mx-auto px-4 sm:px-6 pb-20 sm:pb-28 scroll-mt-16">
        <div className="text-center mb-12">
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight">Como funciona</h2>
          <p className="text-zinc-400 mt-3 max-w-lg mx-auto">
            Três passos entre criar a conta e ter clareza sobre suas finanças.
          </p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 sm:gap-4">
          {HOW_IT_WORKS.map((step, index) => (
            <div key={step.step} className="relative text-center px-2">
              {index < HOW_IT_WORKS.length - 1 && (
                <div className="hidden sm:block absolute top-7 left-[60%] w-full h-px bg-zinc-800" />
              )}
              <div className="relative inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-zinc-900 border border-zinc-800 mb-4">
                <step.icon size={22} className="text-emerald-500" />
                <span className="absolute -top-2 -right-2 w-5 h-5 rounded-full bg-emerald-500 text-black text-[10px] font-bold flex items-center justify-center">
                  {step.step}
                </span>
              </div>
              <h3 className="font-semibold mb-1.5">{step.title}</h3>
              <p className="text-sm text-zinc-400 leading-relaxed max-w-[220px] mx-auto">
                {step.description}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* Funcionalidades */}
      <section id="funcionalidades" className="max-w-6xl mx-auto px-4 sm:px-6 pb-20 sm:pb-28 scroll-mt-16">
        <div className="text-center mb-12">
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight">
            Tudo que você precisa para organizar sua vida financeira
          </h2>
          <p className="text-zinc-400 mt-3 max-w-lg mx-auto">
            Cada módulo pensado para reduzir o esforço de manter suas
            finanças em dia.
          </p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {MODULES.map((feature, idx) => (
            <div
              key={feature.title}
              style={{ animationDelay: `${idx * 60}ms` }}
              className="p-5 sm:p-6 rounded-2xl border border-zinc-800 bg-zinc-900/40 hover:bg-zinc-900/70 hover:border-zinc-700 transition-colors animate-fade-slide-up"
            >
              <div
                className={`w-10 h-10 rounded-xl flex items-center justify-center mb-4 ${feature.color}`}
              >
                <feature.icon size={20} />
              </div>
              <h3 className="font-semibold mb-1.5">{feature.title}</h3>
              <p className="text-sm text-zinc-400 leading-relaxed">
                {feature.description}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* Diferenciais */}
      <section className="max-w-5xl mx-auto px-4 sm:px-6 pb-20 sm:pb-28">
        <div className="text-center mb-12">
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight">Por que o Finance.AI</h2>
          <p className="text-zinc-400 mt-3 max-w-lg mx-auto">
            Três decisões de arquitetura que fazem diferença no uso diário.
          </p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
          {DIFFERENTIATORS.map((item) => (
            <div key={item.title} className="text-center px-2">
              <div className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-emerald-500/10 mb-4">
                <item.icon size={20} className="text-emerald-500" />
              </div>
              <h3 className="font-semibold mb-1.5">{item.title}</h3>
              <p className="text-sm text-zinc-400 leading-relaxed">{item.description}</p>
            </div>
          ))}
        </div>
      </section>

      {/* FAQ */}
      <section id="faq" className="max-w-3xl mx-auto px-4 sm:px-6 pb-20 sm:pb-28 scroll-mt-16">
        <div className="text-center mb-10">
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight">Perguntas frequentes</h2>
        </div>
        <div className="space-y-3">
          {FAQ.map((item, index) => {
            const isOpen = openFaq === index;
            return (
              <div
                key={item.question}
                className="rounded-xl border border-zinc-800 bg-zinc-900/40 overflow-hidden"
              >
                <button
                  onClick={() => setOpenFaq(isOpen ? null : index)}
                  aria-expanded={isOpen}
                  className="w-full flex items-center justify-between gap-4 p-4 sm:p-5 text-left"
                >
                  <span className="text-sm sm:text-base font-medium">{item.question}</span>
                  <ChevronDown
                    size={18}
                    className={`shrink-0 text-zinc-500 transition-transform ${isOpen ? "rotate-180" : ""}`}
                  />
                </button>
                {isOpen && (
                  <p className="px-4 sm:px-5 pb-4 sm:pb-5 text-sm text-zinc-400 leading-relaxed">
                    {item.answer}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {/* CTA final */}
      <section className="max-w-4xl mx-auto px-4 sm:px-6 pb-24 sm:pb-32">
        <div className="rounded-3xl border border-emerald-500/20 bg-gradient-to-br from-emerald-500/10 via-zinc-900/40 to-zinc-900/40 p-8 sm:p-12 text-center">
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight">
            Comece a organizar suas finanças hoje
          </h2>
          <p className="text-zinc-400 mt-3 max-w-md mx-auto">
            Gratuito para começar. Leva menos de um minuto para criar sua conta.
          </p>
          <Link
            href="/register"
            className="inline-flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold px-7 py-3 rounded-xl transition-all active:scale-[0.98] mt-7 shadow-lg shadow-emerald-500/20"
          >
            Criar minha conta grátis
            <ArrowRight size={18} />
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-zinc-800/60">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8 flex flex-col sm:flex-row items-center justify-between gap-4 text-sm text-zinc-500">
          <span>© {new Date().getFullYear()} Finance.AI</span>
          <div className="flex items-center gap-5">
            <a href="#funcionalidades" className="hover:text-zinc-300 transition-colors">
              Funcionalidades
            </a>
            <Link href="/login" className="hover:text-zinc-300 transition-colors">
              Entrar
            </Link>
            <Link href="/register" className="hover:text-zinc-300 transition-colors">
              Criar conta
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
