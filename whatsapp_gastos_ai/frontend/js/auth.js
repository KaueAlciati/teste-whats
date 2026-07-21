document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("login-form");
  if (!form) return;

  const feedback = document.getElementById("login-feedback");
  const identifier = document.getElementById("identifier");
  const password = document.getElementById("password");
  const rememberMe = document.getElementById("remember_me");

  async function checkLogged() {
    try {
      await window.FincontrolAPI.me();
      window.location.href = "/dashboard";
    } catch (error) {
      if (feedback) feedback.textContent = "";
    }
  }

  checkLogged();

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (feedback) feedback.textContent = "Entrando...";

    try {
      await window.FincontrolAPI.login(identifier.value.trim(), password.value, rememberMe.checked);
      window.location.href = "/dashboard";
    } catch (error) {
      if (feedback) feedback.textContent = error.message || "Não foi possível entrar.";
    }
  });
});
