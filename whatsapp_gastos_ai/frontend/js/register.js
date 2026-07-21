document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("register-form");
  if (!form) return;

  const feedback = document.getElementById("register-feedback");
  const button = document.getElementById("register-button");
  const fields = {
    name: document.getElementById("name"),
    email: document.getElementById("email"),
    phone: document.getElementById("phone"),
    password: document.getElementById("password"),
    confirm_password: document.getElementById("confirm_password"),
    accept_terms: document.getElementById("accept_terms"),
  };

  function setLoading(loading) {
    if (!button) return;
    button.disabled = loading;
    button.textContent = loading ? "Criando conta..." : "Criar conta";
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (feedback) feedback.textContent = "";

    if (fields.password.value !== fields.confirm_password.value) {
      if (feedback) feedback.textContent = "As senhas não conferem.";
      return;
    }
    if (!fields.accept_terms.checked) {
      if (feedback) feedback.textContent = "Você precisa aceitar os termos para continuar.";
      return;
    }

    setLoading(true);
    try {
      await window.FincontrolAPI.register({
        name: fields.name.value.trim(),
        email: fields.email.value.trim(),
        phone: fields.phone.value.trim(),
        password: fields.password.value,
        confirm_password: fields.confirm_password.value,
        accept_terms: fields.accept_terms.checked,
      });
      window.location.href = "/login";
    } catch (error) {
      if (feedback) feedback.textContent = error.message || "Não foi possível criar a conta.";
    } finally {
      setLoading(false);
    }
  });
});
