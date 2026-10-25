(function () {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const state = {
    csrf: "",
    email: "",
    workflows: null,
    providerMeta: {},
    catalogs: {},
    keys: [],
    auditEntries: [],
    auditTotal: 0,
    pipelineEntries: [],
    pipelineTotal: 0,
  };

  function toast(message) {
    const node = $("#admin-toast");
    node.textContent = message;
    node.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { node.hidden = true; }, 3200);
  }

  function errorText(error) {
    return error && error.message ? error.message : String(error || "Request failed.");
  }

  async function api(path, options = {}) {
    const method = String(options.method || "GET").toUpperCase();
    const headers = { ...(options.headers || {}) };
    if (options.body !== undefined) headers["Content-Type"] = "application/json";
    if (method !== "GET" && state.csrf) headers["X-VibeCut-Admin-CSRF"] = state.csrf;
    const response = await fetch(`/_ductator/api${path}`, {
      ...options,
      method,
      headers,
      credentials: "same-origin",
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });
    let data = null;
    try { data = await response.json(); } catch (_) { data = null; }
    if (response.status === 401 && !options.noAuthRedirect) {
      showLogin();
      throw new Error((data && data.detail) || "Admin login required.");
    }
    if (!response.ok) {
      throw new Error((data && data.detail) || `Request failed (${response.status}).`);
    }
    return data || {};
  }

  function showLogin() {
    $("#admin-app").hidden = true;
    $("#admin-login").hidden = false;
    $("#login-form").hidden = false;
    $("#bootstrap-form").hidden = true;
    $("#login-password").value = "";
    $("#auth-title").textContent = "Admin login";
    $("#auth-note").textContent = "Local admin only. No signup.";
  }

  function showBootstrap() {
    $("#admin-app").hidden = true;
    $("#admin-login").hidden = false;
    $("#login-form").hidden = true;
    $("#bootstrap-form").hidden = false;
    $("#auth-title").textContent = "Create the admin";
    $("#auth-note").textContent = "Local bootstrap only. This account is the only admin; signup is disabled.";
  }

  function saveSession(data) {
    state.csrf = String(data.csrf || "");
    state.email = String(data.email || "");
    $("#admin-email").textContent = state.email;
  }

  async function init() {
    try {
      const bootstrap = await api("/bootstrap");
      if (bootstrap.needed) {
        if (bootstrap.allowed) showBootstrap();
        else showLogin();
        return;
      }
    } catch (_) {
      // Continue to login; a failed bootstrap probe is not fatal.
    }
    try {
      const me = await api("/me");
      saveSession(me);
      showApp();
    } catch (_) {
      showLogin();
    }
  }

  function showApp() {
    $("#admin-login").hidden = true;
    $("#admin-app").hidden = false;
    loadTab("overview");
  }

  function setTab(name) {
    $$("#admin-tabs button").forEach((button) => {
      button.classList.toggle("active", button.dataset.tab === name);
    });
    $$(".admin-panel").forEach((panel) => {
      panel.hidden = panel.id !== `tab-${name}`;
    });
    loadTab(name);
  }

  async function loadTab(name) {
    try {
      if (name === "overview") await loadOverview();
      if (name === "models") await loadModels();
      if (name === "keys") await loadKeys();
      if (name === "pipeline") await loadPipeline();
      if (name === "audit") await loadAudit();
      if (name === "access") loadAccess();
    } catch (error) {
      toast(errorText(error));
    }
  }

  function empty(text) {
    const node = document.createElement("p");
    node.className = "muted";
    node.textContent = text;
    return node;
  }

  function table(columns, rows, rowBuilder) {
    const wrap = document.createElement("div");
    wrap.className = "log-table";
    if (!rows.length) {
      wrap.append(empty("No entries yet."));
      return wrap;
    }
    const table = document.createElement("table");
    const thead = document.createElement("thead");
    const headRow = document.createElement("tr");
    columns.forEach((label) => {
      const th = document.createElement("th");
      th.textContent = label;
      headRow.append(th);
    });
    thead.append(headRow);
    const tbody = document.createElement("tbody");
    rows.forEach((row) => tbody.append(rowBuilder(row)));
    table.append(thead, tbody);
    wrap.append(table);
    return wrap;
  }

  function jsonDiff(before, after) {
    if (before === undefined || before === null) {
      if (after === undefined || after === null) return null;
    }
    const details = document.createElement("details");
    details.className = "log-diff";
    const summary = document.createElement("summary");
    summary.textContent = "View change";
    const pre = document.createElement("pre");
    pre.textContent = JSON.stringify({ before, after }, null, 2);
    details.append(summary, pre);
    return details;
  }

  async function loadOverview() {
    const data = await api("/overview");
    const configured = (data.keys || []).filter((item) => item.configured).length;
    const workflows = data.workflows || {};
    const routeCount = Object.values(workflows).reduce(
      (total, workflow) => total + ((workflow && workflow.routes) || []).length,
      0,
    );
    const cards = [
      [data.email, "signed in"],
      [`${configured} / ${(data.keys || []).length}`, "AI keys configured"],
      [routeCount, `model routes · ${Object.keys(workflows).length} workflows`],
      [`${(data.pipeline || []).length}`, "recent model calls"],
    ];
    const grid = $("#overview-cards");
    grid.replaceChildren();
    cards.forEach(([value, label]) => {
      const card = document.createElement("div");
      card.className = "overview-card";
      const strong = document.createElement("strong");
      strong.textContent = String(value);
      const span = document.createElement("span");
      span.textContent = label;
      card.append(strong, span);
      grid.append(card);
    });
    const pipeline = $("#overview-pipeline");
    pipeline.replaceChildren(table(
      ["When", "Workflow", "Route", "Status"],
      data.pipeline || [],
      (row) => {
        const tr = document.createElement("tr");
        [new Date(row.ts * 1000).toLocaleTimeString(), row.workflow, `${row.provider} / ${row.model}`, row.status].forEach((value) => {
          const td = document.createElement("td");
          td.textContent = String(value ?? "");
          tr.append(td);
        });
        return tr;
      },
    ));
    const audit = $("#overview-audit");
    audit.replaceChildren(table(
      ["When", "Actor", "Action", "Result"],
      data.audit || [],
      (row) => {
        const tr = document.createElement("tr");
        [new Date(row.ts * 1000).toLocaleTimeString(), row.actor, row.action, row.outcome].forEach((value) => {
          const td = document.createElement("td");
          td.textContent = String(value ?? "");
          tr.append(td);
        });
        return tr;
      },
    ));
  }

  async function catalogFor(provider, workflow, refresh = false) {
    const key = `${provider}|${workflow}`;
    if (!refresh && state.catalogs[key]) return state.catalogs[key];
    const result = await api(`/catalog?provider=${encodeURIComponent(provider)}&workflow=${encodeURIComponent(workflow)}${refresh ? "&refresh=1" : ""}`);
    state.catalogs[key] = result;
    return result;
  }

  function providerLabel(provider) {
    return (state.providerMeta[provider] && state.providerMeta[provider].label) || provider;
  }

  function makeModelCombo(route, workflow, provider, rerender) {
    const wrap = document.createElement("div");
    wrap.className = "model-combo";
    const input = document.createElement("input");
    input.type = "search";
    input.placeholder = "Search available models…";
    input.value = route.model || "";
    input.autocomplete = "off";
    const menu = document.createElement("div");
    menu.className = "model-menu";
    menu.hidden = true;
    wrap.append(input, menu);

    let active = -1;
    const models = () => (state.catalogs[`${provider}|${workflow}`]?.models) || [];
    const filtered = () => {
      const query = input.value.trim().toLowerCase();
      return models().filter((model) => !query
        || String(model.id).toLowerCase().includes(query)
        || String(model.name).toLowerCase().includes(query)).slice(0, 80);
    };
    const close = () => { menu.hidden = true; active = -1; };
    const choose = (model) => {
      route.model = String(model.id);
      input.value = route.model;
      close();
    };
    const renderMenu = () => {
      const rows = filtered();
      menu.replaceChildren();
      if (!rows.length) {
        const node = document.createElement("div");
        node.className = "model-empty";
        node.textContent = models().length ? "No matching models." : "Catalog unavailable or empty.";
        menu.append(node);
      } else {
        rows.forEach((model, index) => {
          const node = document.createElement("button");
          node.type = "button";
          node.className = `model-option${index === active ? " active" : ""}`;
          const strong = document.createElement("strong");
          strong.textContent = model.name || model.id;
          const span = document.createElement("span");
          span.textContent = `${model.id}${model.context_length ? ` · ${Math.round(model.context_length / 1000)}k ctx` : ""}${model.reasoning ? " · reasoning" : ""}`;
          node.append(strong, span);
          node.addEventListener("mousedown", (event) => { event.preventDefault(); choose(model); });
          menu.append(node);
        });
      }
      menu.hidden = false;
    };
    input.addEventListener("focus", renderMenu);
    input.addEventListener("input", () => { route.model = input.value.trim(); renderMenu(); });
    input.addEventListener("keydown", (event) => {
      const rows = filtered();
      if (event.key === "ArrowDown") { event.preventDefault(); active = Math.min(rows.length - 1, active + 1); renderMenu(); }
      else if (event.key === "ArrowUp") { event.preventDefault(); active = Math.max(0, active - 1); renderMenu(); }
      else if (event.key === "Enter" && active >= 0 && rows[active]) { event.preventDefault(); choose(rows[active]); }
      else if (event.key === "Escape") close();
    });
    input.addEventListener("blur", () => setTimeout(() => {
      if (!models().some((model) => model.id === input.value)) {
        input.value = route.model || "";
      }
      close();
    }, 140));
    if (route.model && models().length && !models().some((model) => model.id === route.model)) {
      input.title = "Saved model is not in the current catalog.";
      input.style.borderColor = "var(--accent)";
    }
    return wrap;
  }

  function workflowDescription(name) {
    return {
      story_brief: "Transcript analysis and story context.",
      rewrite: "Script rewrite for the cut and target language.",
      translate: "Online translation before rewrite.",
      hook_rank: "Optional LLM rerank for opening hooks.",
      tts: "Voice-over provider and model.",
      music: "Music generation provider and model.",
      stt: "Transcription provider and model.",
    }[name] || "";
  }

  function renderWorkflowCard(workflow, cfg) {
    const name = workflow.name;
    const kind = workflow.kind;
    const card = document.createElement("section");
    card.className = "workflow-card";
    card.dataset.workflow = name;
    const draft = {
      reasoning: cfg.reasoning || "",
      max_output_tokens: Number(cfg.max_output_tokens || 0),
      timeout_s: Number(cfg.timeout_s || 300),
    };
    const head = document.createElement("header");
    head.className = "workflow-head";
    const copy = document.createElement("div");
    const title = document.createElement("h2");
    title.textContent = workflow.label;
    const desc = document.createElement("p");
    desc.textContent = workflowDescription(name);
    copy.append(title, desc);
    const actions = document.createElement("div");
    actions.className = "workflow-actions";
    const reset = document.createElement("button");
    reset.type = "button";
    reset.className = "ghost small";
    reset.textContent = "Reset to default";
    const save = document.createElement("button");
    save.type = "button";
    save.className = "primary small";
    save.textContent = "Save";
    actions.append(reset, save);
    head.append(copy, actions);
    card.append(head);

    const routes = document.createElement("div");
    routes.className = "route-list";
    const routeObjects = (cfg.routes || []).map((item) => ({ ...item }));
    if (!routeObjects.length) routeObjects.push({ provider: "", model: "" });

    const rerender = () => {
      const replacement = renderWorkflowCard(workflow, {
        ...cfg,
        ...draft,
        routes: routeObjects,
      });
      card.replaceWith(replacement);
    };

    routeObjects.forEach((route, index) => {
      const row = document.createElement("div");
      row.className = "route-row";
      const number = document.createElement("span");
      number.className = "route-index";
      number.textContent = `${index + 1}.`;
      const provider = document.createElement("select");
      (workflow.providers || []).forEach((providerId) => {
        const option = document.createElement("option");
        option.value = providerId;
        option.textContent = providerLabel(providerId);
        if (route.provider === providerId) option.selected = true;
        provider.append(option);
      });
      provider.addEventListener("change", () => {
        route.provider = provider.value;
        route.model = "";
        catalogFor(provider.value, name).catch(() => null).finally(rerender);
      });
      const combo = makeModelCombo(route, name, route.provider, rerender);
      const tools = document.createElement("div");
      tools.className = "route-tools";
      const up = document.createElement("button");
      up.type = "button"; up.title = "Move up"; up.textContent = "↑";
      up.disabled = index === 0;
      up.addEventListener("click", () => {
        [routeObjects[index - 1], routeObjects[index]] = [routeObjects[index], routeObjects[index - 1]];
        rerender();
      });
      const down = document.createElement("button");
      down.type = "button"; down.title = "Move down"; down.textContent = "↓";
      down.disabled = index === routeObjects.length - 1;
      down.addEventListener("click", () => {
        [routeObjects[index + 1], routeObjects[index]] = [routeObjects[index], routeObjects[index + 1]];
        rerender();
      });
      const remove = document.createElement("button");
      remove.type = "button"; remove.title = "Remove route"; remove.textContent = "×";
      remove.disabled = routeObjects.length <= 1;
      remove.addEventListener("click", () => { routeObjects.splice(index, 1); rerender(); });
      tools.append(up, down, remove);
      row.append(number, provider, combo, tools);
      routes.append(row);
    });
    card.append(routes);

    const add = document.createElement("button");
    add.type = "button";
    add.className = "ghost small route-add";
    add.textContent = "+ Add fallback";
    add.disabled = routeObjects.length >= 6;
    add.addEventListener("click", () => {
      const provider = workflow.providers[0] || "";
      routeObjects.push({ provider, model: "" });
      catalogFor(provider, name).catch(() => null).finally(rerender);
    });
    card.append(add);

    const foot = document.createElement("div");
    foot.className = "workflow-foot";
    if (kind === "text") {
      const reasoningLabel = document.createElement("label");
      reasoningLabel.textContent = "Reasoning";
      const reasoning = document.createElement("select");
      wrapperReasoningOptions(reasoning, cfg.reasoning);
      reasoning.addEventListener("change", () => { draft.reasoning = reasoning.value; });
      reasoningLabel.append(reasoning);
      foot.append(reasoningLabel);
      const tokenLabel = document.createElement("label");
      tokenLabel.textContent = "Max output tokens";
      const tokens = document.createElement("input");
      tokens.type = "number"; tokens.min = "64"; tokens.max = "128000";
      tokens.dataset.field = "tokens";
      tokens.value = String(cfg.max_output_tokens || 3200);
      tokens.addEventListener("input", () => { draft.max_output_tokens = Number(tokens.value || 0); });
      tokenLabel.append(tokens);
      foot.append(tokenLabel);
    }
    const timeoutLabel = document.createElement("label");
    timeoutLabel.className = "narrow";
    timeoutLabel.textContent = "Timeout (s)";
    const timeout = document.createElement("input");
    timeout.type = "number"; timeout.min = "10"; timeout.max = "3600";
    timeout.dataset.field = "timeout";
    timeout.value = String(cfg.timeout_s || 300);
    timeout.addEventListener("input", () => { draft.timeout_s = Number(timeout.value || 0); });
    timeoutLabel.append(timeout);
    foot.append(timeoutLabel);
    const footActions = document.createElement("div");
    footActions.className = "workflow-actions";
    footActions.append(reset.cloneNode(true), save.cloneNode(true));
    footActions.querySelectorAll("button")[0].addEventListener("click", async () => {
      if (!confirm(`Reset ${workflow.label} to the built-in route?`)) return;
      try {
        await api(`/workflows/${encodeURIComponent(name)}/reset`, { method: "POST" });
        toast(`${workflow.label} reset.`);
        await loadModels();
      } catch (error) { toast(errorText(error)); }
    });
    footActions.querySelectorAll("button")[1].addEventListener("click", async () => {
      const selected = routeObjects.map((route) => ({ provider: route.provider, model: route.model }));
      if (selected.some((route) => !route.provider || !route.model)) {
        toast("Choose a provider and a model from the catalog for every route.");
        return;
      }
      const unknown = selected.find((route) => {
        const models = state.catalogs[`${route.provider}|${name}`]?.models || [];
        return !models.some((model) => model.id === route.model);
      });
      if (unknown) {
        toast(`Model ${unknown.model} is not in the current catalog.`);
        return;
      }
      try {
        await api(`/workflows/${encodeURIComponent(name)}`, {
          method: "POST",
          body: {
            routes: selected,
            reasoning: kind === "text" ? (draft.reasoning || cfg.reasoning || "") : "",
            max_output_tokens: kind === "text" ? Number(draft.max_output_tokens || 0) : 0,
            timeout_s: Number(draft.timeout_s || cfg.timeout_s || 300),
          },
        });
        toast(`${workflow.label} saved.`);
        await loadModels();
      } catch (error) { toast(errorText(error)); }
    });
    foot.append(footActions);
    card.append(foot);

    // Header buttons mirror the footer actions so the screenshot layout works.
    const headReset = actions.querySelectorAll("button")[0];
    const headSave = actions.querySelectorAll("button")[1];
    headReset.addEventListener("click", () => footActions.querySelectorAll("button")[0].click());
    headSave.addEventListener("click", () => footActions.querySelectorAll("button")[1].click());
    return card;
  }

  function wrapperReasoningOptions(select, value) {
    ["none", "low", "medium", "high", "max"].forEach((item) => {
      const option = document.createElement("option");
      option.value = item;
      option.textContent = item;
      if (item === value) option.selected = true;
      select.append(option);
    });
  }

  async function loadModels(forceRefresh = false) {
    const data = await api("/workflows");
    state.workflows = data.workflows || {};
    state.providerMeta = {};
    (data.provider_meta || []).forEach((item) => { state.providerMeta[item.id] = item; });
    const kinds = data.kinds || {};
    const labels = data.labels || {};
    const providers = data.providers || {};
    const workflows = Object.keys(labels).map((name) => ({
      name, label: labels[name], kind: kinds[name] || "text",
      providers: providers[name] || [],
    }));
    await Promise.all(workflows.flatMap((workflow) => (
      (state.workflows[workflow.name]?.routes || []).map((route) => (
        route.provider ? catalogFor(route.provider, workflow.name, forceRefresh).catch(() => null) : null
      ))
    )));
    const target = $("#workflow-cards");
    target.replaceChildren();
    workflows.forEach((workflow) => {
      target.append(renderWorkflowCard(workflow, state.workflows[workflow.name] || {}));
    });
    $("#catalog-status").textContent = "Model lists refresh from provider catalogs and are cached for 15 minutes.";
  }

  function renderKeyCard(key) {
    const card = document.createElement("section");
    card.className = "key-card";
    const head = document.createElement("div");
    head.className = "key-head";
    const title = document.createElement("h2");
    title.textContent = key.label;
    const source = document.createElement("span");
    source.textContent = key.source || "not set";
    head.append(title, source);
    const masked = document.createElement("p");
    masked.className = "key-value";
    masked.textContent = key.masked || "not configured";
    const src = document.createElement("p");
    src.className = "key-source";
    const envManaged = key.source === "env";
    src.textContent = envManaged
      ? `env-managed: ${key.env || "environment"} (change the environment to rotate)`
      : (key.env ? `fallback env: ${key.env}` : "stored locally");
    const form = document.createElement("form");
    form.className = "key-form";
    const input = document.createElement("input");
    input.type = "password";
    input.autocomplete = "off";
    input.placeholder = key.configured ? "Replace key…" : "Paste key…";
    const save = document.createElement("button");
    save.type = "submit"; save.className = "primary small"; save.textContent = "Save";
    if (envManaged) {
      input.disabled = true;
      input.placeholder = "Managed by environment";
      save.disabled = true;
    }
    form.append(input, save);
    const actions = document.createElement("div");
    actions.className = "key-actions";
    const test = document.createElement("button");
    test.type = "button"; test.className = "ghost small"; test.textContent = "Test";
    const clear = document.createElement("button");
    clear.type = "button"; clear.className = "ghost small"; clear.textContent = "Clear";
    if (envManaged) clear.disabled = true;
    actions.append(test, clear);
    const message = document.createElement("p");
    message.className = "key-error";
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!input.value.trim()) {
        message.textContent = "Enter a key first. Use Clear to remove the stored key.";
        return;
      }
      try {
        await api(`/keys/${encodeURIComponent(key.name)}`, { method: "POST", body: { value: input.value } });
        toast(`${key.label} saved.`);
        input.value = "";
        await loadKeys();
      } catch (error) { message.textContent = errorText(error); }
    });
    test.addEventListener("click", async () => {
      test.disabled = true; message.textContent = "Testing…";
      try {
        const result = await api(`/keys/${encodeURIComponent(key.name)}/test`, { method: "POST" });
        const label = result.tested === false ? "Stored (not tested)" : (result.ok ? "OK" : "Not ready");
        message.textContent = `${label} · ${result.detail || ""}`;
      } catch (error) { message.textContent = errorText(error); }
      finally { test.disabled = false; }
    });
    clear.addEventListener("click", async () => {
      if (!confirm(`Clear ${key.label}?`)) return;
      try {
        await api(`/keys/${encodeURIComponent(key.name)}`, { method: "POST", body: { value: "", clear: true } });
        toast(`${key.label} cleared.`);
        await loadKeys();
      } catch (error) { message.textContent = errorText(error); }
    });
    card.append(head, masked, src, form, actions, message);
    return card;
  }

  async function loadKeys() {
    const data = await api("/keys");
    state.keys = data.keys || [];
    const path = $("#keys-path");
    if (path && data.paths?.secrets) path.textContent = data.paths.secrets;
    const target = $("#key-cards");
    target.replaceChildren();
    state.keys.forEach((key) => target.append(renderKeyCard(key)));
  }

  function renderPipeline() {
    const target = $("#pipeline-table");
    target.replaceChildren(table(
      ["When", "Workflow", "Route", "Status", "ms", "Tokens", "Error"],
      state.pipelineEntries,
      (row) => {
        const tr = document.createElement("tr");
        const values = [
          new Date(row.ts * 1000).toLocaleString(),
          `${row.workflow} #${row.route_index + 1}`,
          `${row.provider} / ${row.model}`,
          row.status,
          Math.round(row.latency_ms),
          `${row.input_tokens || 0} → ${row.output_tokens || 0}`,
          row.error || "",
        ];
        values.forEach((value) => { const td = document.createElement("td"); td.textContent = String(value); tr.append(td); });
        return tr;
      },
    ));
    const more = $("#pipeline-more");
    if (more) more.hidden = state.pipelineEntries.length >= state.pipelineTotal;
  }

  async function loadPipeline(append = false) {
    const filter = $("#pipeline-filter").value.trim();
    const offset = append ? state.pipelineEntries.length : 0;
    const data = await api(`/pipeline?limit=100&offset=${offset}&workflow=${encodeURIComponent(filter)}`);
    state.pipelineEntries = append ? [...state.pipelineEntries, ...(data.entries || [])] : (data.entries || []);
    state.pipelineTotal = Number(data.total || 0);
    renderPipeline();
  }

  function renderAudit() {
    const target = $("#audit-table");
    target.replaceChildren(table(
      ["When", "Actor", "Action", "Resource", "Result", "Detail"],
      state.auditEntries,
      (row) => {
        const tr = document.createElement("tr");
        const when = document.createElement("td"); when.textContent = new Date(row.ts * 1000).toLocaleString();
        const actor = document.createElement("td"); actor.textContent = row.actor || "anonymous";
        const action = document.createElement("td"); action.textContent = row.action || "";
        const resource = document.createElement("td"); resource.textContent = row.resource_id || row.resource_type || "";
        const result = document.createElement("td"); result.textContent = row.outcome || "";
        const detail = document.createElement("td");
        const diff = jsonDiff(row.before, row.after);
        if (diff) detail.append(diff); else detail.textContent = row.detail || "";
        tr.append(when, actor, action, resource, result, detail);
        return tr;
      },
    ));
    const more = $("#audit-more");
    if (more) more.hidden = state.auditEntries.length >= state.auditTotal;
  }

  async function loadAudit(append = false) {
    const filter = $("#audit-filter").value.trim();
    const includeHttp = $("#audit-http")?.checked ? 1 : 0;
    const offset = append ? state.auditEntries.length : 0;
    const data = await api(`/audit?limit=100&offset=${offset}&action=${encodeURIComponent(filter)}&include_http=${includeHttp}`);
    state.auditEntries = append ? [...state.auditEntries, ...(data.entries || [])] : (data.entries || []);
    state.auditTotal = Number(data.total || 0);
    renderAudit();
  }

  function loadAccess() {
    $("#account-email").value = state.email;
  }

  function bind() {
    $("#login-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const error = $("#login-error");
      error.hidden = true;
      try {
        const data = await api("/login", {
          method: "POST",
          body: { email: $("#login-email").value, password: $("#login-password").value },
        });
        saveSession(data);
        showApp();
      } catch (exc) { error.textContent = errorText(exc); error.hidden = false; }
    });
    $("#bootstrap-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const error = $("#bootstrap-error");
      error.hidden = true;
      if ($("#bootstrap-password").value !== $("#bootstrap-confirm").value) {
        error.textContent = "Passwords do not match.";
        error.hidden = false;
        return;
      }
      try {
        const data = await api("/bootstrap", {
          method: "POST",
          body: { email: $("#bootstrap-email").value, password: $("#bootstrap-password").value },
        });
        saveSession(data);
        showApp();
      } catch (exc) { error.textContent = errorText(exc); error.hidden = false; }
    });
    $("#admin-tabs").addEventListener("click", (event) => {
      const button = event.target.closest("[data-tab]");
      if (button) setTab(button.dataset.tab);
    });
    $("#logout").addEventListener("click", async () => {
      try { await api("/logout", { method: "POST" }); } catch (_) { /* already gone */ }
      state.csrf = "";
      $("#login-email").value = "";
      $("#login-password").value = "";
      showLogin();
    });
    $("#refresh-catalogs").addEventListener("click", async () => {
      state.catalogs = {};
      $("#catalog-status").textContent = "Refreshing catalogs…";
      try { await loadModels(true); toast("Catalogs refreshed."); }
      catch (error) { toast(errorText(error)); }
    });
    $("#reload-pipeline").addEventListener("click", () => loadPipeline(false).catch((error) => toast(errorText(error))));
    $("#pipeline-more").addEventListener("click", () => loadPipeline(true).catch((error) => toast(errorText(error))));
    $("#reload-audit").addEventListener("click", () => loadAudit(false).catch((error) => toast(errorText(error))));
    $("#audit-more").addEventListener("click", () => loadAudit(true).catch((error) => toast(errorText(error))));
    $("#audit-http").addEventListener("change", () => loadAudit(false).catch((error) => toast(errorText(error))));
    $("#pipeline-filter").addEventListener("keydown", (event) => { if (event.key === "Enter") loadPipeline(false); });
    $("#audit-filter").addEventListener("keydown", (event) => { if (event.key === "Enter") loadAudit(false); });
    $("#verify-audit").addEventListener("click", async () => {
      try {
        const result = await api("/audit/verify");
        $("#audit-verify").textContent = result.ok
          ? `Audit chain verified · ${result.entries} entries.`
          : `Audit chain broken at entry ${result.broken_at}${result.reason ? ` · ${result.reason}` : ""}.`;
      } catch (error) { $("#audit-verify").textContent = errorText(error); }
    });
    $("#account-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const error = $("#account-error");
      error.hidden = true;
      try {
        const data = await api("/account", {
          method: "POST",
          noAuthRedirect: true,
          body: {
            email: $("#account-email").value,
            current_password: $("#account-current").value,
            new_password: $("#account-new").value,
          },
        });
        state.email = data.email;
        $("#admin-email").textContent = state.email;
        $("#account-current").value = "";
        $("#account-new").value = "";
        toast("Account updated.");
      } catch (exc) { error.textContent = errorText(exc); error.hidden = false; }
    });
  }

  bind();
  init();
})();
