"use strict";
// Formulář zpětné vazby.
// Když je vyplněný WEB3FORMS_KEY (zdarma na https://web3forms.com), zpráva se odešle přímo
// a přijde e-mailem autorovi. Bez klíče se otevře e-mailový klient s předvyplněnou zprávou.
const WEB3FORMS_KEY = "";
const AUTHOR_EMAIL = "petr@vostry.eu";

(() => {
  const form = document.getElementById("feedback");
  if (!form) return;
  const status = document.getElementById("fb-status");
  const button = form.querySelector("button");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(form));
    if (d.botcheck) return;
    if (!d.message.trim()) {
      status.textContent = "Napište prosím zprávu.";
      form.message.focus();
      return;
    }

    if (!WEB3FORMS_KEY) {
      const body = `${d.message}\n\n${d.name ? "Jméno: " + d.name + "\n" : ""}${d.email ? "E-mail: " + d.email + "\n" : ""}`;
      location.href = `mailto:${AUTHOR_EMAIL}?subject=${encodeURIComponent("Peletky – zpětná vazba")}&body=${encodeURIComponent(body)}`;
      status.textContent = "Otevřel se váš e-mailový klient. Pokud ne, napište na " + AUTHOR_EMAIL + ".";
      return;
    }

    button.disabled = true;
    status.textContent = "Odesílám…";
    try {
      const r = await fetch("https://api.web3forms.com/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          access_key: WEB3FORMS_KEY,
          subject: "Peletky – zpětná vazba",
          from_name: "Porovnávač cen peletek",
          name: d.name || "anonym",
          email: d.email || undefined,
          message: d.message,
          botcheck: "",
        }),
      });
      const res = await r.json();
      if (!res.success) throw new Error(res.message || r.status);
      form.reset();
      status.textContent = "Díky, zpráva odešla.";
    } catch (err) {
      status.textContent = "Odeslání se nepovedlo, napište prosím na " + AUTHOR_EMAIL + ".";
    } finally {
      button.disabled = false;
    }
  });
})();
