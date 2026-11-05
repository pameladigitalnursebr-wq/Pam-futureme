# Instruções para o Claude

Este repositório tem duas partes:

1. **Pré-vendas outbound** (`OPERACAO.md`, `templates/`): ver o `README.md`.
2. **Editor de vídeo** (`.claude/skills/editor-de-video/`, `motor/`, `scripts/`), copiado de
   [nomicsadmin/editor-video-ia](https://github.com/nomicsadmin/editor-video-ia) (MIT, ver `LICENSE-editor-video-ia`).

## Editor de vídeo

- Qualquer pedido de edição ("edita esse vídeo", "corta", "legenda", "ajusta"): use a skill `editor-de-video`
  (`.claude/skills/editor-de-video/SKILL.md`).
- Efeito pedido em português ("o número conta quando eu falar 377", "apaga a luz nessa frase"):
  `.claude/skills/editor-de-video/referencias/efeitos-prontos.md`.
- "Aprende o estilo desses vídeos", "salva como X", "edita no estilo X": `motor/referencia.py` (`--estilo`, `--aplicar`,
  `--lista`), detalhe em `.claude/skills/editor-de-video/referencias/referencia.md`.
- Primeira vez: `bash scripts/diagnostico.sh`; se faltar algo, `bash scripts/setup.sh` (Mac ou Windows/Git Bash;
  explique em uma frase o que ele instala e peça permissão).
- Python do projeto: `.venv/bin/python` (Mac) ou `.venv/Scripts/python.exe` (Windows).
- A pessoa provavelmente não é técnica: uma pergunta por vez, linguagem simples, plano antes de cortar.
- Nunca invente número, print ou depoimento. Nunca mande o vídeo para fora do computador. Nunca publique.
- **Repositório público:** vídeos, transcrições, marca e edições ficam fora do git (ver `.gitignore`).
