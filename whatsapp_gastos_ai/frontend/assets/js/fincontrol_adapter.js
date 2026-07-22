(function () {
  "use strict";

  async function api(path, options) {
    var response = await fetch(path, Object.assign({
      credentials: "include",
      headers: { "Content-Type": "application/json" }
    }, options || {}));
    var payload = await response.json().catch(function () { return {}; });
    if (!response.ok || payload.success === false) {
      throw new Error(payload.message || "Não foi possível concluir a operação.");
    }
    return payload.data;
  }

  function showError(form, message) {
    var old = form.querySelector("[data-fincontrol-error]");
    if (old) old.remove();
    var error = document.createElement("div");
    error.className = "text-danger small mt-3";
    error.dataset.fincontrolError = "true";
    error.textContent = message;
    form.appendChild(error);
  }

  function setBusy(button, busy) {
    if (!button) return;
    button.disabled = busy;
    if (busy) button.dataset.originalText = button.textContent;
    button.textContent = busy ? "Aguarde..." : (button.dataset.originalText || button.textContent);
  }

  function bindLogin() {
    var form = document.querySelector("form.user");
    var email = document.querySelector("[name=email]");
    var password = document.querySelector("[name=password]");
    if (!form || !email || !password || form.querySelector("[name=password_repeat]") || !document.body.classList.contains("bg-gradient-primary")) return;
    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      var button = form.querySelector("button[type=submit]");
      setBusy(button, true);
      try {
        await api("/api/auth/login", {
          method: "POST",
          body: JSON.stringify({
            identifier: email.value.trim(),
            password: password.value,
            remember_me: Boolean(document.querySelector("#formCheck-1")?.checked)
          })
        });
        window.location.assign("/dashboard");
      } catch (error) {
        showError(form, error.message);
        setBusy(button, false);
      }
    });
  }

  function ensurePhoneField(form) {
    if (form.querySelector("[name=phone]")) return form.querySelector("[name=phone]");
    var wrapper = document.createElement("div");
    wrapper.className = "mb-3";
    wrapper.innerHTML = '<input class="form-control form-control-user" type="tel" name="phone" placeholder="Phone" required>'; 
    var email = form.querySelector("[name=email]");
    email.closest(".mb-3").after(wrapper);
    return wrapper.querySelector("[name=phone]");
  }

  function bindRegister() {
    var form = document.querySelector("form.user");
    var firstName = document.querySelector("[name=first_name]");
    var email = document.querySelector("[name=email]");
    var password = document.querySelector("[name=password]");
    var repeat = document.querySelector("[name=password_repeat]");
    if (!form || !firstName || !email || !password || !repeat) return;
    var phone = ensurePhoneField(form);
    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      var button = form.querySelector("button[type=submit]");
      setBusy(button, true);
      try {
        await api("/api/auth/register", {
          method: "POST",
          body: JSON.stringify({
            name: (firstName.value.trim() + " " + (form.querySelector("[name=last_name]")?.value || "").trim()).trim(),
            email: email.value.trim(),
            phone: phone.value.trim(),
            password: password.value,
            confirm_password: repeat.value,
            accept_terms: true
          })
        });
        window.location.assign("/login");
      } catch (error) {
        showError(form, error.message);
        setBusy(button, false);
      }
    });
  }

  function formatMoney(value) {
    return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(Number(value || 0));
  }

  async function loadDashboard() {
    if (document.body.id !== "page-top") return;
    try {
      var data = await api("/api/dashboard/summary?period=current_month");
      var values = [data.cards.balance.value, data.cards.income.value, data.cards.expense.value, data.cards.pending_invoice.value];
      document.querySelectorAll("#content .card .h5 span").forEach(function (node, index) {
        if (index < values.length) node.textContent = formatMoney(values[index]);
      });
      var title = document.querySelector("#content h3");
      if (title && data.user && data.user.name) title.textContent = "Dashboard - " + data.user.name;
    } catch (error) {
      console.error("Falha ao carregar dados do dashboard:", error);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    bindLogin();
    bindRegister();
    loadDashboard();
  });
}());
