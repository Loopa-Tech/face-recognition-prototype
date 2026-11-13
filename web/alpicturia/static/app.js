"use strict";
const $ = (s, r = document) => r.querySelector(s);
const esc = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const root = $("#workspace");
const labels = {
  attendee: "Festivalier",
  photographer: "Photographe",
  admin: "Administrateur",
  queued: "En attente",
  running: "En cours",
  ready: "Prêt",
  failed: "Échec",
  sent: "Envoyé",
  sending: "Envoi",
  expired: "Expiré",
  done: "Terminé",
  cancelled: "Annulé",
};
let user = null,
  events = [],
  activeEvent = "",
  poll = null,
  uploadRunning = false,
  paused = false,
  uploadQueue = [],
  currentTable = "users",
  currentOffset = 0,
  adminQuery = "";
const status = (s) =>
  `<span class="badge ${esc(s)}">${esc(labels[s] || s)}</span>`;
const date = (v) => (v ? new Date(v * 1000).toLocaleString("fr-CH") : "—");
const errorBox = (e) =>
  `<p class="error" role="alert">${esc(e.message || e)}</p>`;
const empty = (s) => `<div class="empty">${esc(s)}</div>`;
const toast = (s) => {
  const el = $("#toast");
  el.textContent = s;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 4500);
};
async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...options,
    headers: {
      ...(typeof options.body === "string"
        ? { "Content-Type": "application/json" }
        : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    let message = `Erreur ${response.status}`;
    try {
      const data = await response.json();
      message =
        typeof data.detail === "string"
          ? data.detail
          : "Vérifiez les champs du formulaire.";
    } catch {}
    throw Object.assign(new Error(message), { status: response.status });
  }
  if (response.status === 204) return null;
  return response.headers.get("content-type")?.includes("application/json")
    ? response.json()
    : response.text();
}
const json = (method, data) => ({ method, body: JSON.stringify(data) });
function formObject(form) {
  return Object.fromEntries(new FormData(form));
}
function showError(form, e) {
  let box = $(".form-error", form);
  if (!box) {
    box = document.createElement("div");
    box.className = "form-error";
    form.append(box);
  }
  box.innerHTML = errorBox(e);
}
async function submit(form, fn) {
  const b = $("button[type=submit]", form);
  if (b) b.disabled = true;
  $(".form-error", form)?.remove();
  try {
    await fn();
  } catch (e) {
    showError(form, e);
  } finally {
    if (b) b.disabled = false;
  }
}
function auth(mode = "login") {
  const signup = mode === "signup",
    forgot = mode === "forgot";
  root.innerHTML = `<section class="auth"><p class="eyebrow">BIENVENUE CHEZ ALPICTURIA</p><h1>${signup ? "Vos souvenirs commencent ici." : forgot ? "Retrouvons votre compte." : "Content de vous retrouver."}</h1><div class="tabs"><button data-auth="login" class="${mode === "login" ? "active" : ""}">Connexion</button><button data-auth="signup" class="${signup ? "active" : ""}">Créer un compte</button></div><form id="auth-form">${signup ? '<label for="name">Votre nom</label><input id="name" name="name" autocomplete="name" required minlength="2" maxlength="100">' : ""}<label for="email">Email</label><input type="email" id="email" name="email" autocomplete="email" required maxlength="254">${!forgot ? `<label for="password">Mot de passe ${signup ? "· 12 caractères minimum" : ""}</label><input type="password" id="password" name="password" autocomplete="${signup ? "new-password" : "current-password"}" required ${signup ? 'minlength="12"' : ""} maxlength="128">` : ""}${signup ? '<label for="role">Je suis</label><select id="role" name="role"><option value="attendee">Festivalier · retrouver mes photos</option><option value="photographer">Photographe professionnel · importer mes séries</option></select><p class="tiny">Les photographes doivent être assignés à un événement par l’administration avant de pouvoir importer des photos.</p>' : ""}<button type="submit" class="primary">${signup ? "Créer mon compte" : forgot ? "Envoyer le lien" : "Me connecter"} ↗</button></form>${!forgot ? '<button class="link" data-auth="forgot">Mot de passe oublié ?</button>' : ""}<p class="tiny">Consultez notre <a href="/privacy">politique de confidentialité</a>.</p></section>`;
  $("#auth-form").addEventListener("submit", (e) => {
    e.preventDefault();
    submit(e.target, async () => {
      const data = formObject(e.target);
      if (forgot) {
        const result = await api("/api/auth/forgot", json("POST", data));
        e.target.innerHTML = `<p class="success">${esc(result.message)}</p>`;
        return;
      }
      user = await api(
        "/api/auth/" + (signup ? "signup" : "login"),
        json("POST", data),
      );
      await route();
    });
  });
}
function verification() {
  root.innerHTML = `<section class="auth"><p class="eyebrow">DERNIÈRE ÉTAPE</p><h1>Confirmez votre email.</h1><p>Nous avons préparé un email pour <strong>${esc(user.email)}</strong>. Ouvrez son lien pour activer votre compte.</p><p class="notice">Pensez à vérifier les courriers indésirables.</p><div class="row"><button class="primary" data-action="refresh-account">J’ai confirmé mon email</button><button class="quiet" data-action="resend">Renvoyer l’email</button><button class="link" data-action="logout">Déconnexion</button></div></section>`;
}
async function tokenPage() {
  const action = location.pathname.split("/").pop();
  const token = new URLSearchParams(location.hash.slice(1)).get("token");
  history.replaceState(null, "", location.pathname);
  if (!token) {
    root.innerHTML = errorBox(
      "Lien invalide ou incomplet. Demandez un nouvel email.",
    );
    return;
  }
  if (action === "verify") {
    try {
      await api("/api/auth/verify", json("POST", { token }));
      root.innerHTML =
        '<section class="auth"><h1>Email confirmé.</h1><p>Votre compte est prêt.</p><a class="button" href="/app">Retrouver mes photos ↗</a></section>';
    } catch (e) {
      root.innerHTML = errorBox(e);
    }
    return;
  }
  root.innerHTML =
    '<section class="auth"><h1>Nouveau mot de passe.</h1><form id="reset-form"><label for="new-password">12 caractères minimum</label><input id="new-password" name="password" type="password" autocomplete="new-password" required minlength="12" maxlength="128"><button class="primary" type="submit">Enregistrer le mot de passe</button></form></section>';
  $("#reset-form").onsubmit = (e) => {
    e.preventDefault();
    submit(e.target, async () => {
      await api(
        "/api/auth/reset",
        json("POST", { token, password: e.target.password.value }),
      );
      root.innerHTML =
        '<section class="auth"><h1>Mot de passe modifié.</h1><a class="button" href="/account">Me connecter</a></section>';
    });
  };
}
async function attendee() {
  events = await api("/api/events");
  const selected = new URLSearchParams(location.search).get("event");
  if (selected && events.some((e) => e.id === selected)) activeEvent = selected;
  root.innerHTML = `<p class="eyebrow">BONJOUR ${esc(user.name.toUpperCase())}</p><h1>Retrouvez vos instants.</h1><div class="split"><section class="panel"><h2>Une nouvelle recherche</h2>${events.length ? `<form id="selfie-form"><label for="event">Votre événement</label><select id="event" name="event" required>${events.map((e) => `<option value="${e.id}" ${e.id === activeEvent ? "selected" : ""}>${esc(e.title)} · ${esc(e.date)}</option>`).join("")}</select><label for="selfie">Votre selfie</label><input id="selfie" type="file" name="selfie" accept="image/jpeg,image/png,image/webp" capture="user" required><img id="selfie-preview" class="camera-preview hidden" alt="Aperçu de votre selfie"><p class="tiny">De face, bien éclairé, un seul visage. JPEG, PNG ou WebP · 25 Mo maximum.</p><label class="check"><input type="checkbox" name="consent" required><span>J’autorise l’analyse de mon selfie pour rechercher mes photos dans cet événement. Le selfie sera supprimé après le traitement ; mes résultats expireront après sept jours. <a href="/privacy">En savoir plus</a>.</span></label><button type="submit" class="primary">Lancer ma recherche ↗</button></form>` : empty("Aucun événement disponible pour le moment. Revenez après votre festival.")}<p class="tiny">Les résultats sont des photos candidates. La reconnaissance peut se tromper ou manquer certaines photos.</p></section><section><div class="toolbar"><h2>Mes recherches</h2><button class="quiet small" data-action="refresh-searches">Actualiser</button></div><div id="search-list" class="stack"></div></section></div><section id="results" class="section hidden"></section>`;
  const input = $("#selfie");
  let previewUrl = null;
  if (input)
    input.onchange = () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      const file = input.files[0];
      const img = $("#selfie-preview");
      if (file) {
        previewUrl = URL.createObjectURL(file);
        img.src = previewUrl;
        img.classList.remove("hidden");
      } else img.classList.add("hidden");
    };
  const form = $("#selfie-form");
  if (form)
    form.onsubmit = (e) => {
      e.preventDefault();
      submit(form, async () => {
        const file = input.files[0];
        if (!file) throw new Error("Choisissez votre selfie.");
        if (file.size > 25 * 1024 * 1024)
          throw new Error("Le fichier dépasse 25 Mo.");
        activeEvent = form.event.value;
        const result = await api(`/api/events/${activeEvent}/searches`, {
          method: "POST",
          body: file,
          headers: {
            "Content-Type": file.type,
            "X-Consent-Version": "selfie-search-v1",
          },
        });
        toast("Recherche ajoutée à la file de traitement.");
        form.reset();
        $("#selfie-preview").classList.add("hidden");
        if (previewUrl) URL.revokeObjectURL(previewUrl);
        await refreshSearches();
        showResults(result.id);
      });
    };
  await refreshSearches();
  poll = setInterval(() => refreshSearches().catch(() => {}), 6000);
}
async function refreshSearches() {
  const el = $("#search-list");
  if (!el) return;
  const rows = await api("/api/searches");
  el.innerHTML = rows.length
    ? rows
        .map(
          (r) =>
            `<article class="panel search-card"><div><h3>${esc(r.title)}</h3><p>${date(r.created)}</p>${status(r.status)}${r.error ? errorBox(r.error) : ""}</div><div class="row"><button class="quiet small" data-result="${r.id}">Voir</button><button class="link danger" data-delete-search="${r.id}">Supprimer</button></div></article>`,
        )
        .join("")
    : empty("Vos recherches apparaîtront ici.");
  const current = $("#results")?.dataset.search;
  if (current) await showResults(current, false);
}
async function showResults(id, scroll = true) {
  const result = await api("/api/searches/" + id);
  const el = $("#results");
  el.dataset.search = id;
  el.classList.remove("hidden");
  el.innerHTML = `<div class="toolbar"><h2>Votre galerie</h2>${status(result.status)}</div>${result.error ? errorBox(result.error) : ""}${["queued", "running"].includes(result.status) ? '<p class="notice" role="status">Votre recherche attend son traitement. Les résultats s’afficheront ici automatiquement.</p>' : ""}${result.status === "ready" ? (result.photos.length ? `<p class="subtle">${result.photos.length} photo(s) candidate(s) · aperçus protégés. Les achats ne sont pas encore ouverts.</p><div class="gallery">${result.photos.map((p) => `<button class="photo" data-photo="${p.id}" aria-label="Agrandir ${esc(p.filename)}"><img loading="lazy" src="/api/photos/${p.id}/preview" alt="${esc(p.filename)}"></button>`).join("")}</div>` : empty("Aucune correspondance trouvée. Vérifiez votre événement, essayez un autre selfie ou revenez lorsque de nouvelles photos auront été traitées.")) : ""}${result.status === "expired" ? empty("Cette recherche a expiré. Vous pouvez en créer une nouvelle.") : ""}`;
  if (scroll) el.scrollIntoView({ behavior: "smooth", block: "start" });
}
async function photographer() {
  events = await api("/api/photographer/events");
  if (!events.some((e) => e.id === activeEvent))
    activeEvent = events[0]?.id || "";
  root.innerHTML = `<p class="eyebrow">ESPACE PHOTOGRAPHE</p><h1>Vos séries, en un endroit.</h1><p class="intro">Importez vos photos depuis votre ordinateur. Le traitement facial s’effectue en arrière-plan.</p>${events.length ? `<div class="toolbar"><select id="upload-event" aria-label="Événement">${events.map((e) => `<option value="${e.id}" ${e.id === activeEvent ? "selected" : ""}>${esc(e.title)} ${e.published ? "" : "· brouillon"}</option>`).join("")}</select><button class="quiet" data-action="refresh-photos">Actualiser les photos</button></div><div class="split"><section class="panel"><div class="dropzone" id="dropzone"><h2>Déposez votre série ici.</h2><p>Ou sélectionnez plusieurs fichiers.</p><input id="bulk-files" aria-label="Choisir les photos à importer" type="file" multiple accept="image/jpeg,image/png,image/webp"><p class="tiny">JPEG, PNG, WebP · 25 Mo et 40 Mpx par photo.<br>RAW : exportez vos photos en JPEG avant l’import.</p></div><div id="upload-progress"></div><div class="row"><button id="upload-start" class="primary hidden">Démarrer l’import</button><button id="upload-pause" class="quiet hidden">Mettre en pause</button><button id="upload-retry" class="quiet hidden">Reprendre les échecs</button></div><p class="tiny">Gardez cet onglet ouvert. Après une coupure, resélectionnez votre série : les fichiers déjà reçus seront reconnus comme doublons. La reprise s’effectue par fichier complet.</p><div class="upload-list" id="upload-list"></div></section><section><h2>Traitements</h2><div id="photo-summary"></div><p class="tiny">Les fichiers reçus restent disponibles après un redémarrage. Les traitements en échec peuvent être relancés individuellement.</p></section></div><div class="toolbar"><h2>Vos photos</h2><span id="photo-total" class="subtle"></span></div><div id="photo-list"></div>` : empty("Aucun événement assigné. Votre compte photographe est créé ; un administrateur doit maintenant vous assigner à un événement.")}`;
  if (!events.length) return;
  $("#upload-event").onchange = async (e) => {
    if (uploadRunning) {
      e.target.value = activeEvent;
      toast("Terminez l’import avant de changer d’événement.");
      return;
    }
    activeEvent = e.target.value;
    uploadQueue = [];
    renderQueue();
    await refreshPhotos();
  };
  $("#bulk-files").onchange = (e) => selectFiles(e.target.files);
  const zone = $("#dropzone");
  zone.ondragover = (e) => {
    e.preventDefault();
    zone.classList.add("drag");
  };
  zone.ondragleave = () => zone.classList.remove("drag");
  zone.ondrop = (e) => {
    e.preventDefault();
    zone.classList.remove("drag");
    selectFiles(e.dataTransfer.files);
  };
  $("#upload-start").onclick = runUploads;
  $("#upload-pause").onclick = () => {
    paused = !paused;
    $("#upload-pause").textContent = paused ? "Continuer" : "Mettre en pause";
    if (!paused) runUploads();
  };
  $("#upload-retry").onclick = () => {
    uploadQueue
      .filter((x) => x.state === "failed")
      .forEach((x) => {
        x.state = "waiting";
        x.progress = 0;
      });
    paused = false;
    runUploads();
  };
  await refreshPhotos();
  poll = setInterval(
    () =>
      refreshPhotos(Number($("#photo-list")?.dataset.offset || 0)).catch(
        () => {},
      ),
    6000,
  );
}
function selectFiles(files) {
  if (uploadRunning) {
    toast("Attendez la fin de l’import en cours.");
    return;
  }
  const accepted = [...files].slice(0, 5000);
  uploadQueue = accepted.map((file) => ({
    file,
    state:
      !/\.(jpe?g|png|webp)$/i.test(file.name) || file.size > 25 * 1024 * 1024
        ? "failed"
        : "waiting",
    progress: 0,
    error:
      file.size > 25 * 1024 * 1024
        ? "Plus de 25 Mo"
        : !/\.(jpe?g|png|webp)$/i.test(file.name)
          ? "Format non pris en charge"
          : "",
  }));
  renderQueue();
}
function renderQueue() {
  const el = $("#upload-list");
  if (!el) return;
  const done = uploadQueue.filter((x) =>
    ["done", "duplicate"].includes(x.state),
  ).length;
  const failed = uploadQueue.filter((x) => x.state === "failed").length;
  $("#upload-progress").innerHTML = uploadQueue.length
    ? `<p>${done} / ${uploadQueue.length} reçue(s) · ${failed} échec(s)</p><progress value="${done}" max="${uploadQueue.length}" aria-label="Progression de l’import"></progress>`
    : "";
  const dictionary = {
    waiting: "En attente",
    uploading: "Envoi",
    done: "Reçue",
    duplicate: "Déjà reçue",
    failed: "Échec",
  };
  el.innerHTML =
    uploadQueue
      .slice(0, 100)
      .map(
        (x) =>
          `<div class="upload-row"><span>${esc(x.file.name)} ${x.error ? `<small class="danger">${esc(x.error)}</small>` : ""}</span><span>${dictionary[x.state]} ${x.state === "uploading" ? x.progress + " %" : ""}</span></div>`,
      )
      .join("") +
    (uploadQueue.length > 100
      ? '<p class="tiny">Les 100 premiers fichiers sont affichés. Tous les fichiers sélectionnés seront traités.</p>'
      : "");
  $("#upload-start").classList.toggle(
    "hidden",
    !uploadQueue.some((x) => x.state === "waiting") || uploadRunning,
  );
  $("#upload-pause").classList.toggle("hidden", !uploadRunning && !paused);
  $("#upload-retry").classList.toggle("hidden", !failed || uploadRunning);
}
function sendFile(item) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/events/${activeEvent}/photos`);
    xhr.setRequestHeader(
      "Content-Type",
      item.file.type || "application/octet-stream",
    );
    xhr.setRequestHeader("X-Filename", encodeURIComponent(item.file.name));
    xhr.timeout = 180000;
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        item.progress = Math.round((e.loaded / e.total) * 100);
        renderQueue();
      }
    };
    xhr.onerror = () => reject(new Error("Connexion interrompue."));
    xhr.ontimeout = () => reject(new Error("Délai dépassé."));
    xhr.onload = () => {
      let data;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        return reject(new Error("Réponse serveur invalide."));
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data);
      else
        reject(
          new Error(
            typeof data.detail === "string"
              ? data.detail
              : "Import impossible.",
          ),
        );
    };
    xhr.send(item.file);
  });
}
async function runUploads() {
  if (uploadRunning) return;
  uploadRunning = true;
  paused = false;
  renderQueue();
  async function lane() {
    while (!paused) {
      const item = uploadQueue.find((x) => x.state === "waiting");
      if (!item) break;
      item.state = "uploading";
      renderQueue();
      try {
        const result = await sendFile(item);
        item.state = result.duplicate ? "duplicate" : "done";
        item.error = "";
      } catch (e) {
        item.state = "failed";
        item.error = e.message;
      }
      renderQueue();
    }
  }
  try {
    await Promise.all([lane(), lane(), lane()]);
  } finally {
    uploadRunning = false;
    renderQueue();
    await refreshPhotos();
    if (!paused) toast("Import terminé. Consultez les éventuels échecs.");
  }
}
async function refreshPhotos(offset = 0) {
  if (!$("#photo-list") || !activeEvent) return;
  const result = await api(
    `/api/events/${activeEvent}/photos?offset=${offset}&limit=50`,
  );
  $("#photo-total").textContent =
    `${result.total} photo(s) · page ${Math.floor(offset / 50) + 1}`;
  const counts = result.items.reduce(
    (a, r) => ((a[r.status] = (a[r.status] || 0) + 1), a),
    {},
  );
  $("#photo-summary").innerHTML =
    Object.entries(counts)
      .map(([key, value]) => `<p>${status(key)} <strong>${value}</strong></p>`)
      .join("") + '<p class="tiny">Compteurs de la page affichée.</p>';
  $("#photo-list").innerHTML = result.items.length
    ? `<div class="table-wrap"><table><thead><tr><th>Fichier</th><th>État</th><th>Visages</th><th>Actions</th></tr></thead><tbody>${result.items.map((p) => `<tr><td>${esc(p.filename)}${p.error ? errorBox(p.error) : ""}</td><td>${status(p.status)}</td><td>${p.face_count}</td><td><div class="row">${p.status === "ready" ? `<button class="quiet small" data-photo="${p.id}">Voir</button>` : ""}${p.status === "failed" ? `<button class="quiet small" data-retry-photo="${p.id}">Relancer</button>` : ""}<button class="link danger" data-delete-photo="${p.id}">Supprimer</button></div></td></tr>`).join("")}</tbody></table></div><div class="toolbar">${offset ? `<button class="quiet" data-photo-page="${Math.max(0, offset - 50)}">Précédent</button>` : ""}${offset + 50 < result.total ? `<button class="quiet" data-photo-page="${offset + 50}">Suivant</button>` : ""}</div>`
    : empty("Aucune photo importée.");
  $("#photo-list").dataset.offset = offset;
}
async function account() {
  const keys = await api("/api/keys");
  root.innerHTML = `<p class="eyebrow">MON COMPTE</p><h1>Bonjour ${esc(user.name)}.</h1><div class="split"><section class="panel"><h2>Votre espace</h2><p>${esc(user.email)}<br>${esc(labels[user.role])} · email confirmé</p><div class="row"><a class="button small" href="/app">Mes photos</a>${user.role !== "attendee" ? '<a class="button secondary small" href="/photographer">Photographe</a>' : ""}${user.role === "admin" ? '<a class="button secondary small" href="/admin">Administration</a>' : ""}</div><hr><h3>Vos données</h3><a class="button secondary small" href="/api/me/export" download="alpicturia-donnees.json">Exporter mes données</a><p class="tiny">Vous pouvez aussi supprimer chaque recherche depuis votre galerie.</p><div class="row"><button class="quiet" data-action="logout">Déconnexion</button>${user.role !== "admin" ? '<button class="quiet danger" data-action="delete-account">Supprimer mon compte</button>' : ""}</div></section><section class="panel"><h2>Accès API & MCP</h2><p class="subtle">Créez une clé pour vos agents. Elle expire après 90 jours et n’est affichée qu’une fois.</p><form id="key-form"><label for="key-name">Nom de la clé</label><input id="key-name" name="name" required minlength="2" maxlength="80" placeholder="Mon agent personnel"><label class="check"><input type="checkbox" name="write"><span>Autoriser les modifications</span></label>${user.role === "admin" ? '<label class="check"><input type="checkbox" name="admin"><span>Autoriser les opérations administrateur</span></label>' : ""}<button type="submit" class="primary">Créer une clé</button></form><div id="new-key"></div><h3>Clés actives</h3>${keys.length ? keys.map((k) => `<p>${esc(k.name)} · ${date(k.expires)} <button class="link danger" data-revoke="${k.id}">Révoquer</button></p>`).join("") : empty("Aucune clé active.")}<p class="tiny">Les droits d’un agent sont toujours limités par ceux de votre compte.</p></section></div>`;
  $("#key-form").onsubmit = (e) => {
    e.preventDefault();
    submit(e.target, async () => {
      const scopes = ["read"];
      if (e.target.write.checked) scopes.push("write");
      if (e.target.admin?.checked) scopes.push("admin");
      const data = await api(
        "/api/keys",
        json("POST", {
          name: e.target.elements.namedItem("name").value,
          scopes,
        }),
      );
      $("#new-key").innerHTML =
        `<p class="notice">Copiez cette clé maintenant. Elle ne sera plus affichée.</p><pre class="token">${esc(data.token)}</pre><p class="tiny">Ne la partagez pas et ne la placez jamais dans votre dépôt Git.</p>`;
      e.target.reset();
    });
  };
}
async function admin() {
  if (user.role !== "admin")
    throw new Error("Accès réservé à l’administration.");
  const data = await api("/api/admin/overview");
  root.innerHTML = `<p class="eyebrow">ADMINISTRATION</p><h1>Tout votre événementiel.</h1><div class="stats">${[
    ["users", "Comptes"],
    ["events", "Événements"],
    ["photos", "Photos reçues"],
    ["searches", "Recherches"],
  ]
    .map(
      ([k, label]) =>
        `<article class="stat"><span>${label}</span><strong>${data.counts[k]}</strong></article>`,
    )
    .join(
      "",
    )}</div><div class="split"><section class="panel"><h3>Audience & stockage</h3><p><strong>${data.counts.pageviews_30d}</strong> pages vues · 30 derniers jours</p><p><strong>${(data.counts.storage_bytes / 1024 / 1024).toFixed(1)} Mo</strong> de photos originales</p><p class="tiny">Les pages vues ne représentent pas des visiteurs uniques. Les administrateurs sont inclus.</p></section><section class="panel"><h3>État des services</h3><p>${data.configuration.smtp ? "✓ Emails configurés" : "⚠ SMTP à configurer — emails en attente"}</p><p>${data.configuration.face_engine ? "✓ Moteur facial installé" : "⚠ Dépendances IA à installer"}</p><p>${data.configuration.worker_last_seen && Date.now() / 1000 - data.configuration.worker_last_seen < 300 ? "✓ Worker actif récemment" : "⚠ Worker à démarrer ou à contrôler"}</p><p>${data.configuration.search_console_verification ? "✓ Balise Search Console configurée" : "⚠ Search Console à vérifier sur le domaine définitif"}</p><p class="tiny">${esc(data.configuration.public_url)}</p></section></div><div class="split section"><section><h3>Traitements</h3>${data.job_status.map((r) => `<p>${status(r.status)} ${r.count}</p>`).join("") || empty("Aucun traitement.")}</section><section><h3>Emails transactionnels</h3>${data.email_status.map((r) => `<p>${status(r.status)} ${r.count}</p>`).join("") || empty("Aucun email.")}</section></div><div class="toolbar"><h2>Données & activité</h2><button class="primary small" data-action="new-event">Créer un événement</button></div><div class="tabs" id="admin-tabs">${[
    ["users", "Comptes"],
    ["events", "Événements"],
    ["photos", "Photos"],
    ["searches", "Recherches"],
    ["jobs", "Traitements"],
    ["mail", "Emails"],
    ["audit", "Journal"],
    ["assignments", "Assignations"],
  ]
    .map(
      ([k, l]) =>
        `<button data-table="${k}" class="${currentTable === k ? "active" : ""}">${l}</button>`,
    )
    .join(
      "",
    )}</div><div class="toolbar"><input id="admin-search" aria-label="Rechercher dans les données" placeholder="Rechercher un nom, email, fichier ou événement" value="${esc(adminQuery)}"><a id="admin-export" class="button secondary small" href="/api/admin/export/${currentTable}">Exporter toutes les lignes</a></div><div id="admin-data"></div><div id="admin-editor"></div>`;
  let timer;
  $("#admin-search").oninput = (e) => {
    adminQuery = e.target.value;
    clearTimeout(timer);
    timer = setTimeout(() => loadTable(currentTable, 0), 300);
  };
  await loadTable(currentTable, currentOffset);
}
async function loadTable(table, offset = 0) {
  currentTable = table;
  currentOffset = offset;
  const data = await api(
    `/api/admin/data/${table}?offset=${offset}&limit=50&q=${encodeURIComponent(adminQuery)}`,
  );
  $("#admin-export").href = "/api/admin/export/" + table;
  document
    .querySelectorAll("[data-table]")
    .forEach((b) => b.classList.toggle("active", b.dataset.table === table));
  const rows = data.items;
  const columns = rows[0] ? Object.keys(rows[0]) : [];
  $("#admin-data").innerHTML =
    `<p class="subtle">${data.total} enregistrement(s) · page ${Math.floor(offset / 50) + 1}</p>${rows.length ? `<div class="table-wrap"><table><thead><tr>${columns.map((c) => `<th>${esc(c)}</th>`).join("")}<th>Actions</th></tr></thead><tbody>${rows.map((r) => `<tr>${columns.map((c) => `<td>${c === "status" ? status(r[c]) : ["created", "last_seen", "expires", "consented"].includes(c) ? date(r[c]) : esc(r[c])}</td>`).join("")}<td><div class="row">${table === "users" && r.role !== "admin" ? `<button class="quiet small" data-toggle-user="${r.id}" data-disabled="${r.disabled}">${r.disabled ? "Réactiver" : "Désactiver"}</button>` : ""}${table === "events" ? `<button class="quiet small" data-edit-event="${r.id}">Modifier</button><button class="quiet small" data-assign="${r.id}">Assigner</button>` : ""}${table === "photos" && r.status === "failed" ? `<button class="quiet small" data-retry-photo="${r.id}">Relancer</button>` : ""}${table === "mail" && r.status === "failed" ? `<button class="quiet small" data-retry-mail="${r.id}">Relancer</button>` : ""}${table === "assignments" ? `<button class="quiet small danger" data-unassign="${r.event_id}" data-user="${r.user_id}">Retirer</button>` : ""}</div></td></tr>`).join("")}</tbody></table></div>` : empty("Aucun résultat.")}<div class="toolbar">${offset ? `<button class="quiet" data-admin-page="${Math.max(0, offset - 50)}">Précédent</button>` : ""}${offset + 50 < data.total ? `<button class="quiet" data-admin-page="${offset + 50}">Suivant</button>` : ""}</div>`;
}
async function eventEditor(id = null) {
  let data = {
    title: "",
    slug: "",
    location: "",
    date: "",
    description: "",
    published: 0,
  };
  if (id) {
    data = await api("/api/admin/events/" + id);
    if (!data) throw new Error("Événement introuvable dans cette page.");
  }
  const el = $("#admin-editor");
  el.innerHTML = `<section class="panel"><h2>${id ? "Modifier" : "Créer"} un événement</h2><form id="event-form"><div class="split"><div><label for="event-title">Nom</label><input id="event-title" name="title" required minlength="2" maxlength="150" value="${esc(data.title)}"><label for="event-slug">Adresse publique · slug</label><input id="event-slug" name="slug" required pattern="[a-z0-9]+(-[a-z0-9]+)*" minlength="2" maxlength="100" value="${esc(data.slug)}" placeholder="festival-lausanne-2027"></div><div><label for="event-location">Lieu</label><input id="event-location" name="location" required minlength="2" maxlength="150" value="${esc(data.location)}"><label for="event-date">Date</label><input id="event-date" name="date" type="date" required value="${esc(data.date)}"></div></div><label for="description">Description publique</label><textarea id="description" name="description" maxlength="3000">${esc(data.description)}</textarea><label class="check"><input type="checkbox" name="published" ${data.published ? "checked" : ""}><span>Publier l’événement sur le site et dans le sitemap</span></label><button type="submit" class="primary">Enregistrer</button></form></section>`;
  el.scrollIntoView({ behavior: "smooth" });
  $("#event-form").onsubmit = (e) => {
    e.preventDefault();
    submit(e.target, async () => {
      const body = formObject(e.target);
      body.published = e.target.published.checked;
      await api(
        "/api/admin/events" + (id ? "/" + id : ""),
        json(id ? "PUT" : "POST", body),
      );
      toast("Événement enregistré.");
      await admin();
    });
  };
}
async function assignmentEditor(eventId) {
  let photographers = [],
    offset = 0;
  while (true) {
    const batch = await api(
      "/api/admin/photographers?offset=" + offset + "&limit=100",
    );
    photographers.push(...batch);
    if (batch.length < 100) break;
    offset += 100;
  }
  const el = $("#admin-editor");
  el.innerHTML = `<section class="panel"><h2>Assigner un photographe</h2>${photographers.length ? `<form id="assignment-form"><label for="assignment-user">Photographe</label><select id="assignment-user" name="user_id">${photographers.map((u) => `<option value="${u.id}">${esc(u.name)} · ${esc(u.email)}</option>`).join("")}</select><button type="submit" class="primary">Assigner à cet événement</button></form>` : empty("Aucun compte photographe disponible. Le photographe doit d’abord créer son compte.")}</section>`;
  el.scrollIntoView({ behavior: "smooth" });
  const f = $("#assignment-form");
  if (f)
    f.onsubmit = (e) => {
      e.preventDefault();
      submit(f, async () => {
        await api(
          `/api/admin/events/${eventId}/photographers`,
          json("POST", formObject(f)),
        );
        toast("Photographe assigné.");
        await loadTable("assignments");
      });
    };
}
async function route() {
  if (poll) {
    clearInterval(poll);
    poll = null;
  }
  if (location.pathname.startsWith("/account/")) return tokenPage();
  if (!user) {
    try {
      user = await api("/api/me");
    } catch (e) {
      if (e.status === 401) {
        auth();
        return;
      }
      throw e;
    }
  }
  $("#account-link").textContent = user.name.split(" ")[0];
  if (!user.verified) {
    verification();
    return;
  }
  if (location.pathname === "/admin") return admin();
  if (location.pathname === "/photographer") return photographer();
  if (location.pathname === "/account") return account();
  return attendee();
}
document.addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  try {
    if (b.dataset.auth) return auth(b.dataset.auth);
    if (b.dataset.result) return showResults(b.dataset.result);
    if (b.dataset.photo) {
      const img = $("#lightbox-image");
      img.src = "/api/photos/" + b.dataset.photo + "/preview";
      $("#lightbox").showModal();
      return;
    }
    if (b.id === "close-lightbox") return $("#lightbox").close();
    if (b.dataset.deleteSearch) {
      if (!confirm("Supprimer cette recherche et ses résultats ?")) return;
      await api("/api/searches/" + b.dataset.deleteSearch, {
        method: "DELETE",
      });
      if ($("#results")?.dataset.search === b.dataset.deleteSearch) {
        $("#results").classList.add("hidden");
        delete $("#results").dataset.search;
      }
      return refreshSearches();
    }
    if (b.dataset.deletePhoto) {
      if (
        !confirm(
          "Supprimer définitivement cette photo, son index et ses correspondances ?",
        )
      )
        return;
      await api("/api/photos/" + b.dataset.deletePhoto, { method: "DELETE" });
      return refreshPhotos();
    }
    if (b.dataset.retryPhoto) {
      await api("/api/photos/" + b.dataset.retryPhoto + "/retry", {
        method: "POST",
      });
      toast("Traitement relancé.");
      return location.pathname === "/admin"
        ? loadTable(currentTable, currentOffset)
        : refreshPhotos();
    }
    if (b.dataset.photoPage !== undefined)
      return refreshPhotos(Number(b.dataset.photoPage));
    if (b.dataset.table) return loadTable(b.dataset.table, 0);
    if (b.dataset.adminPage !== undefined)
      return loadTable(currentTable, Number(b.dataset.adminPage));
    if (b.dataset.editEvent) return eventEditor(b.dataset.editEvent);
    if (b.dataset.assign) return assignmentEditor(b.dataset.assign);
    if (b.dataset.unassign) {
      await api(
        `/api/admin/events/${b.dataset.unassign}/photographers/${b.dataset.user}`,
        { method: "DELETE" },
      );
      return loadTable("assignments");
    }
    if (b.dataset.toggleUser) {
      if (!confirm("Confirmer la modification de l’accès de ce compte ?"))
        return;
      await api(
        `/api/admin/users/${b.dataset.toggleUser}/${b.dataset.disabled === "1" ? "enable" : "disable"}`,
        { method: "POST" },
      );
      return loadTable("users", currentOffset);
    }
    if (b.dataset.retryMail) {
      await api("/api/admin/mail/" + b.dataset.retryMail + "/retry", {
        method: "POST",
      });
      return loadTable("mail", currentOffset);
    }
    if (b.dataset.revoke) {
      await api("/api/keys/" + b.dataset.revoke, { method: "DELETE" });
      return account();
    }
    switch (b.dataset.action) {
      case "logout":
        await api("/api/auth/logout", { method: "POST" });
        user = null;
        return auth();
      case "resend":
        await api("/api/auth/resend", { method: "POST" });
        return toast("Email de confirmation demandé.");
      case "refresh-account":
        user = await api("/api/me");
        return route();
      case "refresh-searches":
        return refreshSearches();
      case "refresh-photos":
        return refreshPhotos();
      case "new-event":
        return eventEditor();
      case "delete-account":
        if (
          !confirm(
            "Supprimer définitivement votre compte, vos recherches et vos photos si vous êtes photographe ?",
          )
        )
          return;
        await api("/api/me", {
          method: "DELETE",
          headers: { "X-Confirm-Delete": "DELETE" },
        });
        user = null;
        location.href = "/";
    }
  } catch (err) {
    toast(err.message);
  }
});
window.addEventListener("beforeunload", (e) => {
  if (uploadRunning || uploadQueue.some((x) => x.state === "waiting")) {
    e.preventDefault();
    e.returnValue = "";
  }
});
(async () => {
  try {
    if (root) await route();
    const list = $("#public-events");
    if (list) {
      const rows = await api("/api/events");
      list.innerHTML = rows.length
        ? rows
            .map(
              (e) =>
                `<a class="event-card" href="/events/${esc(e.slug)}"><div class="symbol" aria-hidden="true">✳</div><p>${esc(e.date)} · ${esc(e.location)}</p><h3>${esc(e.title)}</h3><span class="subtle">Retrouver mes photos ↗</span></a>`,
            )
            .join("")
        : empty("Les prochains événements seront annoncés ici.");
    }
    if (!location.pathname.startsWith("/account/"))
      api("/api/metrics", {
        method: "POST",
        headers: { "X-Page": location.pathname },
      }).catch(() => {});
  } catch (e) {
    if (root) root.innerHTML = errorBox(e);
    else toast(e.message);
  }
})();

if ("serviceWorker" in navigator)
  navigator.serviceWorker.register("/sw.js").catch(() => {});
