document.addEventListener("DOMContentLoaded", async () => {
  if (!document.body.classList.contains("page-dashboard")) return;

  const accountCard = document.getElementById("account-card");
  const telegramCard = document.getElementById("telegram-card");
  const configSummary = document.getElementById("config-summary");
  const configStatusBadge = document.getElementById("config-status-badge");
  const configStatusText = document.getElementById("config-status-text");

  async function handleLogout() {
    try {
      await window.FincontrolAPI.logout();
    } catch (_) {
      // ignore
    } finally {
      window.location.href = "/login";
    }
  }

  async function loadTelegramSection() {
    const status = await window.FincontrolAPI.telegramStatus();
    if (!telegramCard) return;
    if (status.linked) {
      telegramCard.innerHTML = `
        <div class="list-item">
          <strong>Vinculado</strong>
          <small>${window.FincontrolUtils.escapeHtml(status.display_name || status.username || status.channel_user_id || "-")}</small>
        </div>
        <div class="meta-row">
          <span class="pill">Telegram ativo</span>
          <span class="pill">Vinculado em ${window.FincontrolUtils.formatDate(status.linked_at)}</span>
        </div>
        <button class="btn btn-ghost" id="telegram-unlink">Desvincular Telegram</button>
      `;
      document.getElementById("telegram-unlink")?.addEventListener("click", async () => {
        try {
          await window.FincontrolAPI.telegramUnlink();
          await loadTelegramSection();
        } catch (error) {
          alert(error.message || "Não foi possível desvincular agora.");
        }
      });
      return;
    }

    if (status.pending || status.expired) {
      telegramCard.innerHTML = `
        <div class="list-item">
          <strong>${status.expired ? "Código expirado" : "Código gerado"}</strong>
          <small>Abra o bot e envie o código de vinculação.</small>
        </div>
        <div class="meta-row">
          <span class="pill">${status.expired ? "Código expirado" : "Aguardando confirmação"}</span>
          <span class="pill">Expira em ${window.FincontrolUtils.formatDate(status.verification_expires_at)}</span>
        </div>
        <button class="btn btn-primary" id="telegram-code">Gerar novo código</button>
      `;
      document.getElementById("telegram-code")?.addEventListener("click", async () => {
        try {
          const result = await window.FincontrolAPI.telegramLinkCode();
          renderPendingCode(result);
        } catch (error) {
          alert(error.message || "Não foi possível gerar o código agora.");
        }
      });
      return;
    }

    telegramCard.innerHTML = `
      <div class="list-item">
        <strong>Não vinculado</strong>
        <small>Clique para gerar um código temporário de 6 dígitos.</small>
      </div>
      <button class="btn btn-primary" id="telegram-code">Vincular Telegram</button>
    `;
    document.getElementById("telegram-code")?.addEventListener("click", async () => {
      try {
        const result = await window.FincontrolAPI.telegramLinkCode();
        renderPendingCode(result);
      } catch (error) {
        alert(error.message || "Não foi possível gerar o código agora.");
      }
    });
  }

  function renderPendingCode(result) {
    if (!telegramCard) return;
    const code = result?.code || "";
    telegramCard.innerHTML = `
      <div class="list-item">
        <strong>Código de vinculação</strong>
        <small>Envie no Telegram: <strong>/vincular ${window.FincontrolUtils.escapeHtml(code)}</strong></small>
      </div>
      <div class="meta-row">
        <span class="pill">Aguardando confirmação</span>
        <span class="pill">Expira em ${window.FincontrolUtils.formatDate(result?.expires_at)}</span>
      </div>
      <button class="btn btn-ghost" id="telegram-refresh">Gerar novo código</button>
    `;
    document.getElementById("telegram-refresh")?.addEventListener("click", async () => {
      try {
        const next = await window.FincontrolAPI.telegramLinkCode();
        renderPendingCode(next);
      } catch (error) {
        alert(error.message || "Não foi possível gerar o código agora.");
      }
    });
  }

  async function init() {
    try {
      const me = await window.FincontrolAPI.me();
      const user = me.user;
      if (accountCard) {
        accountCard.innerHTML = `
          <div class="list-item"><strong>${window.FincontrolUtils.escapeHtml(user.name || user.display_name || "-")}</strong><small>Nome completo</small></div>
          <div class="list-item"><strong>${window.FincontrolUtils.escapeHtml(user.email || "-")}</strong><small>E-mail</small></div>
          <div class="list-item"><strong>${window.FincontrolUtils.escapeHtml(user.phone || user.telefone || "-")}</strong><small>Telefone</small></div>
          <div class="list-item"><strong>${window.FincontrolUtils.escapeHtml(user.is_active ? "Ativa" : "Inativa")}</strong><small>Status da conta</small></div>
          <div class="list-item"><strong>${window.FincontrolUtils.escapeHtml(user.email_verified ? "Confirmado" : "Pendente")}</strong><small>E-mail</small></div>
          <button class="btn btn-ghost" id="email-verify-button" type="button">Solicitar verificação de e-mail</button>
        `;
        document.getElementById("email-verify-button")?.addEventListener("click", async () => {
          try {
            const result = await window.FincontrolAPI.requestEmailVerification();
            if (result?.debug_token) {
              alert(`Token de teste: ${result.debug_token}`);
            } else {
              alert("Solicitação enviada. Verifique seu e-mail quando o serviço estiver configurado.");
            }
          } catch (error) {
            alert(error.message || "Não foi possível solicitar a verificação.");
          }
        });
      }
      if (configSummary) configSummary.textContent = "Sua conta e integrações estão disponíveis aqui.";
      if (configStatusBadge) configStatusBadge.textContent = "Conta";
      if (configStatusText) configStatusText.textContent = user.email_verified ? "E-mail confirmado" : "E-mail pendente";

      await window.FincontrolLayout.renderShell(user, "current_month", null, handleLogout);
      await loadTelegramSection();
    } catch (error) {
      window.location.href = "/login";
    }
  }

  init();
});
