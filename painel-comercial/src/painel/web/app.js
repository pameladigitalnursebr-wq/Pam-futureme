// Painel de Inteligência Comercial — interface (sem build, sem dependências).
// Toda regra de negócio fica na API; aqui só há estado de filtros e renderização.

const $ = (sel, raiz = document) => raiz.querySelector(sel);
const fmt = new Intl.NumberFormat("pt-BR");
const num = (n) => fmt.format(n ?? 0);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const dataBR = (s) => (s ? new Date(s).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "");

// Filtros mostrados na barra lateral, na ordem de uso mais comum.
const FILTROS_LATERAIS = [
  ["instituicao", "Instituição"], ["curso", "Curso"], ["uf", "Estado"], ["cidade", "Cidade"],
  ["regiao_ensino", "Região de ensino"], ["modalidade", "Modalidade"], ["grupo", "Grupo educacional"],
  ["escola", "Escola"], ["posicao", "Posição da opção"], ["ano_cadastro", "Ano de cadastro"],
  ["status_comercial", "Status comercial"], ["genero", "Gênero"], ["faixa_etaria", "Faixa etária"],
];
const ABAS_RANKING = [
  ["instituicao", "Instituições"], ["curso", "Cursos"], ["cidade", "Cidades"], ["uf", "Estados"],
  ["regiao_ensino", "Regiões"], ["escola", "Escolas"], ["grupo", "Grupos"],
];
const DISTRIBUICOES = [
  ["modalidade", "Modalidade"], ["posicao", "Posição da opção"], ["ano_cadastro", "Ano de cadastro"],
  ["faixa_etaria", "Faixa etária"],
];

const estado = {
  usuario: null,
  filtros: {},            // { dimensao: [{chave, rotulo}] }
  suspeitas: false,
  aba: "instituicao",
  pagina: 1,
};

// ---------------------------------------------------------------- API

async function api(caminho, opcoes = {}) {
  const r = await fetch(caminho, { credentials: "same-origin", ...opcoes });
  if (r.status === 401 && !caminho.startsWith("/api/sessao")) { mostrarLogin(); throw new Error("sessão"); }
  const corpo = r.headers.get("content-type")?.includes("json") ? await r.json() : await r.text();
  if (!r.ok) {
    const d = corpo?.detail;
    throw Object.assign(new Error(typeof d === "string" ? d : d?.mensagem || "Erro na requisição"), { detalhe: d });
  }
  return corpo;
}

function query(extra = {}) {
  const p = new URLSearchParams();
  for (const [dim, itens] of Object.entries(estado.filtros)) if (itens.length) p.set(dim, itens.map((i) => i.chave).join(","));
  if (estado.suspeitas) p.set("incluir_suspeitas", "true");
  for (const [k, v] of Object.entries(extra)) p.set(k, v);
  return p.toString();
}

const pode = (p) => estado.usuario?.permissoes.includes(p);

// ---------------------------------------------------------------- Login

function mostrarLogin() { $("#app").hidden = true; $("#tela-login").hidden = false; }

$("#form-login").addEventListener("submit", async (e) => {
  e.preventDefault();
  const dados = Object.fromEntries(new FormData(e.target));
  try {
    await api("/api/sessao", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(dados) });
    iniciar();
  } catch (err) { $("#erro-login").textContent = err.message; }
});

$("#sair").addEventListener("click", async () => { await api("/api/sessao", { method: "DELETE" }); mostrarLogin(); });

// ---------------------------------------------------------------- Navegação

document.querySelectorAll(".abas-principais button").forEach((b) =>
  b.addEventListener("click", () => abrirVista(b.dataset.vista)));

function abrirVista(nome) {
  document.querySelectorAll(".abas-principais button").forEach((b) => b.classList.toggle("ativa", b.dataset.vista === nome));
  document.querySelectorAll(".vista").forEach((v) => (v.hidden = v.id !== `vista-${nome}`));
  ({ importacoes: carregarImportacoes, revisao: carregarRevisao, admin: carregarAdmin }[nome] || (() => {}))();
}

// ---------------------------------------------------------------- Filtros

function montarFiltrosLaterais() {
  const lista = $("#lista-filtros");
  lista.innerHTML = "";
  for (const [dim, titulo] of FILTROS_LATERAIS) {
    const bloco = document.createElement("div");
    bloco.className = "filtro";
    bloco.innerHTML = `<span>${esc(titulo)}</span><input type="search" placeholder="Digite para buscar…" aria-label="${esc(titulo)}"><div class="sugestoes" hidden></div>`;
    const input = $("input", bloco), caixa = $(".sugestoes", bloco);
    let temporizador;
    const buscar = () => {
      clearTimeout(temporizador);
      temporizador = setTimeout(async () => {
        const itens = await api(`/api/dimensoes/${dim}/valores?q=${encodeURIComponent(input.value)}&limite=15`);
        caixa.innerHTML = itens.length ? "" : `<div class="vazio">Nada encontrado</div>`;
        for (const i of itens) {
          const b = document.createElement("button");
          b.type = "button";
          b.innerHTML = `<span>${esc(i.rotulo)}</span><span class="qtd">${num(i.alunos)}</span>`;
          b.addEventListener("mousedown", (ev) => { ev.preventDefault(); adicionarFiltro(dim, i); input.value = ""; caixa.hidden = true; });
          caixa.appendChild(b);
        }
        caixa.hidden = false;
      }, 180);
    };
    input.addEventListener("input", buscar);
    input.addEventListener("focus", buscar);
    input.addEventListener("blur", () => setTimeout(() => (caixa.hidden = true), 150));
    lista.appendChild(bloco);
  }
}

function adicionarFiltro(dim, item) {
  const atuais = estado.filtros[dim] || [];
  if (!atuais.some((i) => String(i.chave) === String(item.chave))) estado.filtros[dim] = [...atuais, { chave: item.chave, rotulo: item.rotulo }];
  aplicar();
}

function removerFiltro(dim, chave) {
  estado.filtros[dim] = (estado.filtros[dim] || []).filter((i) => String(i.chave) !== String(chave));
  if (!estado.filtros[dim].length) delete estado.filtros[dim];
  aplicar();
}

$("#limpar-filtros").addEventListener("click", () => { estado.filtros = {}; aplicar(); });
$("#incluir-suspeitas").addEventListener("change", (e) => { estado.suspeitas = e.target.checked; aplicar(); });

function desenharChips() {
  const caixa = $("#filtros-ativos");
  caixa.innerHTML = "";
  const titulos = Object.fromEntries(FILTROS_LATERAIS);
  for (const [dim, itens] of Object.entries(estado.filtros)) {
    for (const i of itens) {
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.innerHTML = `<b>${esc(titulos[dim] || dim)}:</b> ${esc(i.rotulo)} <button aria-label="Remover">×</button>`;
      $("button", chip).addEventListener("click", () => removerFiltro(dim, i.chave));
      caixa.appendChild(chip);
    }
  }
}

// Os filtros vivem na URL: copiar o link compartilha exatamente a mesma consulta.
function salvarNaUrl() {
  const q = query();
  history.replaceState(null, "", q ? `?${q}` : location.pathname);
}

async function lerDaUrl() {
  const p = new URLSearchParams(location.search);
  estado.suspeitas = p.get("incluir_suspeitas") === "true";
  $("#incluir-suspeitas").checked = estado.suspeitas;
  for (const [dim] of FILTROS_LATERAIS.concat(ABAS_RANKING)) {
    const chaves = p.get(dim);
    if (!chaves || estado.filtros[dim]) continue;
    const nomes = await api(`/api/dimensoes/${dim}/rotulos?chaves=${encodeURIComponent(chaves)}`);
    estado.filtros[dim] = chaves.split(",").map((c) => ({ chave: isNaN(c) ? c : Number(c), rotulo: nomes[c] || c }));
  }
}

// ---------------------------------------------------------------- Busca rápida

let tempoBusca;
$("#busca").addEventListener("input", (e) => {
  clearTimeout(tempoBusca);
  const termo = e.target.value.trim();
  const caixa = $("#busca-resultados");
  if (termo.length < 2) { caixa.hidden = true; return; }
  tempoBusca = setTimeout(async () => {
    const r = await api(`/api/busca?q=${encodeURIComponent(termo)}`);
    caixa.innerHTML = r.grupos.length ? "" : `<div class="vazio">Nada encontrado para “${esc(termo)}”.</div>`;
    for (const g of r.grupos) {
      const h = document.createElement("h3");
      h.textContent = g.titulo;
      caixa.appendChild(h);
      for (const i of g.itens) {
        const b = document.createElement("button");
        b.type = "button";
        b.innerHTML = `<span>${esc(i.rotulo)}</span><span class="qtd">${num(i.alunos)} alunos</span>`;
        b.addEventListener("mousedown", (ev) => {
          ev.preventDefault();
          caixa.hidden = true;
          $("#busca").value = "";
          adicionarFiltro(g.dimensao, i);
        });
        caixa.appendChild(b);
      }
    }
    caixa.hidden = false;
  }, 220);
});
$("#busca").addEventListener("blur", () => setTimeout(() => ($("#busca-resultados").hidden = true), 150));

// ---------------------------------------------------------------- Painel

async function aplicar() {
  estado.pagina = 1;
  salvarNaUrl();
  desenharChips();
  await Promise.all([carregarResumo(), carregarRanking(), carregarDistribuicoes(), carregarDetalhe()]);
}

async function carregarResumo() {
  const r = await api(`/api/resumo?${query()}`);
  const cartoes = [
    ["Alunos interessados", r.alunos, "alunos distintos no recorte", true],
    ["Interesses", r.interesses, "opções de instituição (até 3 por aluno)"],
    ["Instituições", r.instituicoes, "com ao menos um interessado"],
    ["Cursos", r.cursos, "citados no pódio dos alunos"],
    ["Estados", r.estados, "da escola do aluno"],
    ["Cidades", r.cidades, `${num(r.escolas)} escolas`],
  ];
  $("#kpis").innerHTML = cartoes.map(([rotulo, valor, nota, principal]) =>
    `<div class="kpi ${principal ? "principal" : ""}"><div class="rotulo">${rotulo}</div><div class="valor">${num(valor)}</div><div class="nota">${esc(nota)}</div></div>`).join("");
  $("#avisos").innerHTML = (r.avisos || []).map((a) => `<div class="aviso">${esc(a)}</div>`).join("");
}

function desenharBarras(caixa, dim, itens) {
  caixa.innerHTML = "";
  if (!itens.length) { caixa.innerHTML = `<div class="vazio">Nenhum resultado para estes filtros.</div>`; return; }
  const maximo = Math.max(...itens.map((i) => i.alunos)) || 1;
  for (const i of itens) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "barra";
    b.innerHTML = `<span class="nome">${esc(i.rotulo)}</span><span class="trilho"><span class="preenchido" style="display:block;width:${(100 * i.alunos) / maximo}%"></span></span><span class="valor">${num(i.alunos)} · ${String(i.percentual).replace(".", ",")}%</span>`;
    b.addEventListener("click", () => adicionarFiltro(dim, i));
    b.addEventListener("mousemove", (ev) => mostrarDica(ev, i));
    b.addEventListener("mouseleave", esconderDica);
    caixa.appendChild(b);
  }
}

function mostrarDica(ev, i) {
  const d = $("#dica-flutuante");
  d.innerHTML = `<b>${esc(i.rotulo)}</b>${num(i.alunos)} alunos · ${num(i.interesses)} interesses<br>${String(i.percentual).replace(".", ",")}% dos alunos do recorte<br><i>clique para filtrar</i>`;
  d.hidden = false;
  d.style.left = `${Math.min(ev.clientX + 14, innerWidth - 330)}px`;
  d.style.top = `${ev.clientY + 14}px`;
}
function esconderDica() { $("#dica-flutuante").hidden = true; }

function montarAbasRanking() {
  const caixa = $("#abas-ranking");
  caixa.innerHTML = "";
  for (const [dim, titulo] of ABAS_RANKING) {
    const b = document.createElement("button");
    b.role = "tab";
    b.textContent = titulo;
    b.setAttribute("aria-selected", dim === estado.aba);
    b.addEventListener("click", () => { estado.aba = dim; montarAbasRanking(); carregarRanking(); });
    caixa.appendChild(b);
  }
}
$("#limite-ranking").addEventListener("change", carregarRanking);

async function carregarRanking() {
  const r = await api(`/api/ranking/${estado.aba}?${query({ limite: $("#limite-ranking").value })}`);
  desenharBarras($("#ranking"), estado.aba, r.itens);
}

async function carregarDistribuicoes() {
  const caixa = $("#distribuicoes");
  if (!caixa.children.length) {
    caixa.innerHTML = DISTRIBUICOES.map(([dim, titulo]) =>
      `<section class="cartao"><div class="cartao-topo"><h2>${titulo}</h2></div><div class="barras" data-dist="${dim}"></div></section>`).join("");
  }
  await Promise.all(DISTRIBUICOES.map(async ([dim]) => {
    const r = await api(`/api/ranking/${dim}?${query({ limite: 12 })}`);
    const itens = dim === "ano_cadastro" || dim === "posicao" ? [...r.itens].sort((a, b) => (a.chave > b.chave ? 1 : -1)) : r.itens;
    desenharBarras($(`[data-dist="${dim}"]`), dim, itens);
  }));
}

$("#ordenar").addEventListener("change", () => { estado.pagina = 1; carregarDetalhe(); });

async function carregarDetalhe() {
  const r = await api(`/api/detalhe?${query({ pagina: estado.pagina, por_pagina: 50, ordenar: $("#ordenar").value })}`);
  $("#total-detalhe").textContent = `· ${num(r.total)} alunos`;
  const cols = Object.entries(r.colunas);
  const celula = (k, v) => {
    if (v === null || v === undefined) return "";
    if (k === "cadastrado_em") return dataBR(v);
    if (typeof v === "boolean") return v ? "Sim" : "Não";
    return esc(v);
  };
  $("#tabela-detalhe").innerHTML =
    `<thead><tr>${cols.map(([, t]) => `<th>${esc(t)}</th>`).join("")}</tr></thead>` +
    `<tbody>${r.itens.map((i) => `<tr>${cols.map(([k]) => `<td>${celula(k, i[k])}</td>`).join("")}</tr>`).join("") ||
      `<tr><td colspan="${cols.length}" class="vazio">Nenhum aluno para estes filtros.</td></tr>`}</tbody>`;
  const pag = $("#paginacao");
  pag.innerHTML = `<button ${r.pagina <= 1 ? "disabled" : ""} data-p="${r.pagina - 1}">‹ Anterior</button>
    <span>Página ${num(r.pagina)} de ${num(Math.max(r.paginas, 1))}</span>
    <button ${r.pagina >= r.paginas ? "disabled" : ""} data-p="${r.pagina + 1}">Próxima ›</button>`;
  pag.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => { estado.pagina = Number(b.dataset.p); carregarDetalhe(); }));
}

document.querySelectorAll("[data-exportar]").forEach((b) => b.addEventListener("click", () => {
  const tipo = b.dataset.exportar;
  const extra = tipo === "ranking" ? { tipo: "ranking", dimensao: estado.aba, formato: "xlsx" }
    : { tipo: "detalhe", formato: tipo.endsWith("csv") ? "csv" : "xlsx" };
  location.href = `/api/exportar?${query(extra)}`;
}));

// ---------------------------------------------------------------- Importações

function resumoImportacao(r) {
  const s = r.resumo || {};
  const linhas = [];
  for (const [ent, titulo] of [["alunos", "Alunos"], ["interesses", "Interesses"], ["instituicoes", "Instituições"],
    ["volume_cursos", "Volume de cursos"], ["volume_cidades", "Volume de cidades"], ["volume_escolas", "Volume de escolas"]]) {
    if (s[ent]) linhas.push(`<div><b>${titulo}:</b> ${Object.entries(s[ent]).map(([k, v]) => `${esc(k.replace(/_/g, " "))} ${num(v)}`).join(" · ")}</div>`);
  }
  const oc = (s.ocorrencias || []).map((o) => `${o.severidade === "erro" ? "Erro" : "Aviso"} ${esc(o.codigo)}: ${num(o.quantidade)}`).join(" · ");
  return `<div class="relatorio ${r.status === "concluida" ? "ok" : "falha"}">
    <div><b>Importação #${r.id}</b> · ${esc(r.fonte)} · modo ${esc(r.modo)} · <span class="status ${esc(r.status)}">${esc(r.status)}</span> · ${((r.duracao_ms || 0) / 1000).toFixed(1).replace(".", ",")} s</div>
    <div>Linhas lidas ${num(r.linhas_lidas)} · ignoradas ${num(r.linhas_ignoradas)} · erros ${num(r.total_erros)} · avisos ${num(r.total_avisos)}</div>
    ${linhas.join("")}${oc ? `<div class="mudo">${oc}</div>` : ""}
    ${r.mensagem ? `<div class="erro">${esc(r.mensagem)}</div>` : ""}
    ${r.total_erros + r.total_avisos ? `<div><a href="/api/importacoes/${r.id}/ocorrencias?formato=csv">Baixar erros e avisos (CSV)</a></div>` : ""}
  </div>`;
}

$("#form-importacao").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = new FormData(e.target);
  form.set("forcar", e.target.forcar.checked ? "true" : "false");
  const botao = $("button[type=submit]", e.target);
  botao.disabled = true;
  botao.textContent = "Importando… (pode levar até 1 minuto)";
  const caixa = $("#resultado-importacao");
  try {
    caixa.innerHTML = resumoImportacao(await api("/api/importacoes", { method: "POST", body: form }));
  } catch (err) {
    caixa.innerHTML = err.detalhe?.importacao ? resumoImportacao(err.detalhe.importacao) : `<div class="relatorio falha"><span class="erro">${esc(err.message)}</span></div>`;
  } finally {
    botao.disabled = false;
    botao.textContent = "Importar";
    carregarImportacoes();
    carregarStatus();
  }
});

async function carregarImportacoes() {
  const lista = await api("/api/importacoes?limite=30");
  $("#tabela-importacoes").innerHTML = `<thead><tr><th>#</th><th>Quando</th><th>Arquivo</th><th>Base</th><th>Status</th><th class="num">Linhas</th><th>Mudanças</th><th>Por</th></tr></thead><tbody>${
    lista.map((i) => {
      const s = i.resumo || {};
      const m = s.interesses ? `+${num(s.interesses.novos)} novos · ${num(s.interesses.atualizados)} alterados · −${num(s.interesses.removidos)} removidos`
        : s.instituicoes ? `${num(s.instituicoes.novas)} novas · ${num(s.instituicoes.atualizadas)} atualizadas` : esc(i.mensagem || "");
      return `<tr><td>${i.id}</td><td>${dataBR(i.iniciado_em)}</td><td>${esc(i.arquivo_nome)}</td><td>${esc(i.fonte)}</td><td><span class="status ${esc(i.status)}">${esc(i.status)}</span></td><td class="num">${num(i.linhas_lidas)}</td><td>${m}</td><td>${esc(i.usuario || "")}</td></tr>`;
    }).join("")}</tbody>`;
}

// ---------------------------------------------------------------- Revisão

async function carregarRevisao() {
  const r = await api("/api/instituicoes/revisao?limite=50");
  $("#total-revisao").textContent = `· ${num(r.total)} pendentes`;
  const caixa = $("#lista-revisao");
  caixa.innerHTML = r.itens.length ? "" : `<p class="vazio">Nada pendente.</p>`;
  for (const i of r.itens) {
    const item = document.createElement("div");
    item.className = "revisao-item";
    item.innerHTML = `<div><b>${esc(i.nome)}</b> <span class="mudo">· ${num(i.interesses)} interesses · ${i.qualidade === "suspeita" ? "suspeita" : "só nos leads"}</span></div><div class="botoes"></div>`;
    const botoes = $(".botoes", item);
    const acao = (rotulo, fn) => { const b = document.createElement("button"); b.textContent = rotulo; b.addEventListener("click", async () => { await fn(); carregarRevisao(); }); botoes.appendChild(b); };
    for (const s of i.sugestoes) {
      acao(`Unificar com “${s.nome}” (${String(s.semelhanca).replace(".", ",")})`, () => {
        if (!confirm(`Unificar “${i.nome}” com “${s.nome}”? Os interesses passam para “${s.nome}” em todas as importações futuras.`)) return;
        return api(`/api/instituicoes/${i.id}/unificar`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ destino_id: s.id }) });
      });
    }
    const json = (corpo) => ({ method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify(corpo) });
    acao("É uma instituição válida", () => api(`/api/instituicoes/${i.id}`, json({ verificada: true, qualidade: "ok" })));
    acao("Marcar como suspeita", () => api(`/api/instituicoes/${i.id}`, json({ verificada: true, qualidade: "suspeita" })));
    caixa.appendChild(item);
  }
}

// ---------------------------------------------------------------- Administração

async function carregarAdmin() {
  const [usuarios, chaves, consultas] = await Promise.all([api("/api/usuarios"), api("/api/chaves"), api("/api/historico-consultas?limite=50")]);
  $("#papeis").innerHTML = Object.entries(estado.usuario.papeis).map(([p, d]) => `<b>${esc(p)}</b>: ${esc(d)}`).join(" · ");
  $("#tabela-usuarios").innerHTML = `<thead><tr><th>Nome</th><th>E-mail</th><th>Papel</th><th>Ativo</th><th>Último acesso</th></tr></thead><tbody>${
    usuarios.map((u) => `<tr><td>${esc(u.nome)}</td><td>${esc(u.email)}</td><td>${esc(u.papel)}</td><td>${u.ativo ? "Sim" : "Não"}</td><td>${dataBR(u.ultimo_acesso)}</td></tr>`).join("")}</tbody>`;
  $("#tabela-chaves").innerHTML = `<thead><tr><th>Nome</th><th>Prefixo</th><th>Escopos</th><th>Dono</th><th>Último uso</th><th></th></tr></thead><tbody>${
    chaves.map((c) => `<tr><td>${esc(c.nome)}</td><td><code>${esc(c.prefixo)}…</code></td><td>${esc(c.escopos.join(", "))}</td><td>${esc(c.usuario)}</td><td>${dataBR(c.ultimo_uso)}</td><td>${c.revogada_em ? "revogada" : `<button class="discreto" data-revogar="${c.id}">Revogar</button>`}</td></tr>`).join("")}</tbody>`;
  document.querySelectorAll("[data-revogar]").forEach((b) => b.addEventListener("click", async () => {
    if (confirm("Revogar esta chave? Integrações que a usam param de funcionar.")) { await api(`/api/chaves/${b.dataset.revogar}`, { method: "DELETE" }); carregarAdmin(); }
  }));
  $("#tabela-consultas").innerHTML = `<thead><tr><th>Quando</th><th>Quem</th><th>Origem</th><th>Consulta</th><th class="num">ms</th></tr></thead><tbody>${
    consultas.map((c) => `<tr><td>${dataBR(c.criado_em)}</td><td>${esc(c.usuario || "")}</td><td>${esc(c.origem)}</td><td>${esc(c.operacao)} <span class="mudo">${esc(JSON.stringify(c.parametros))}</span></td><td class="num">${num(c.duracao_ms)}</td></tr>`).join("")}</tbody>`;
}

$("#form-usuario").addEventListener("submit", async (e) => {
  e.preventDefault();
  const dados = Object.fromEntries(new FormData(e.target));
  if (!dados.senha) delete dados.senha;
  try { await api("/api/usuarios", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(dados) }); e.target.reset(); carregarAdmin(); }
  catch (err) { alert(err.message); }
});

$("#form-chave").addEventListener("submit", async (e) => {
  e.preventDefault();
  const dados = Object.fromEntries(new FormData(e.target));
  const r = await api("/api/chaves", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ nome: dados.nome, escopos: [dados.escopo] }) });
  $("#chave-criada").innerHTML = `<div class="aviso">${esc(r.aviso)}<code class="chave">${esc(r.chave)}</code></div>`;
  e.target.reset();
  carregarAdmin();
});

// ---------------------------------------------------------------- Início

async function carregarStatus() {
  const s = await api("/api/status");
  const leads = s.ultimas_importacoes?.leads;
  $("#base-atualizada").textContent = leads ? `Base de ${dataBR(leads.concluido_em)}` : "Base ainda não importada";
}

async function iniciar() {
  try { estado.usuario = await api("/api/eu"); } catch { return; }
  $("#tela-login").hidden = true;
  $("#app").hidden = false;
  $("#nome-usuario").textContent = estado.usuario.nome;
  document.querySelectorAll("[data-permissao]").forEach((el) => (el.hidden = !pode(el.dataset.permissao)));
  montarFiltrosLaterais();
  montarAbasRanking();
  await lerDaUrl();
  carregarStatus();
  aplicar();
}

iniciar();
