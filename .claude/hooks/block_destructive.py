#!/usr/bin/env python3
"""PreToolUse hook — bloqueia ações destrutivas ANTES de executarem.

Cobre: comandos Bash/PowerShell e qualquer tool do MCP `databricks` (o SQL passa por aqui).
Contrato do Claude Code: exit 2 = bloqueia; a mensagem no stderr volta para o
modelo explicando o porquê. Exit 0 = segue o jogo. QUALQUER outro código é tratado
como erro não-bloqueante (o comando roda!), por isso o script falha fechado com exit 2.
"""

import json
import re
import sys

# No Windows stdin/stderr vêm em cp1252; o payload do Claude Code é UTF-8.
sys.stderr.reconfigure(encoding="utf-8")

# (padrão, motivo) — case-insensitive
RULES = [
    (
        r"\bdatabricks\s+bundle\s+destroy\b",
        "`bundle destroy` é proibido para o agente. Se precisar destruir, o humano faz no terminal.",
    ),
    (
        # CLI do Databricks: catalogs/schemas/tables/volumes/pipelines/jobs/workspace... delete,
        # fs rm, api delete etc. — o equivalente a um DROP sem escrever SQL.
        r"\bdatabricks\s+(?:[\w-]+\s+){1,3}?(?:delete|delete-[\w-]+|rm|purge|destroy)\b",
        "Remoção via CLI do Databricks (`... delete` / `fs rm`) é bloqueada — o agente opera em modo "
        "não destrutivo. Peça ao humano.",
    ),
    (
        r"\bDROP\s+(?:TABLE|SCHEMA|CATALOG|VIEW|MATERIALIZED\s+VIEW|STREAMING\s+TABLE|DATABASE|VOLUME|FUNCTION)\b",
        "DROP é bloqueado — o agente opera em modo não destrutivo. Peça ao humano.",
    ),
    (
        r"\bTRUNCATE\s+TABLE\b",
        "TRUNCATE é bloqueado — o agente opera em modo não destrutivo.",
    ),
    (
        r"\bDELETE\s+FROM\b",
        "DELETE é bloqueado — o agente opera em modo não destrutivo.",
    ),
    (
        r"\brm\s+-[a-zA-Z]*f",
        "rm forçado é bloqueado. Remova arquivos individualmente e sem -f.",
    ),
    (
        r"\bgit\s+push\b.*(--force\b|-f\b)",
        "push forçado é bloqueado — histórico não se reescreve ao vivo.",
    ),
]

# deploy em prod: deploy + alvo prod em qualquer ordem/formato de flag
DEPLOY = re.compile(r"\bdatabricks\s+bundle\s+deploy\b", re.IGNORECASE)
TARGET_PROD = re.compile(r"(--target[=\s]+|-t[=\s]+)['\"]?prod\b", re.IGNORECASE)


def main() -> None:
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except Exception as exc:
        # falha fechada: se não dá para inspecionar, não deixa passar
        block(f"payload do hook ilegível ({exc}); comando não inspecionado.")

    tool = data.get("tool_name", "")
    tool_input = data.get("tool_input", {}) or {}

    if tool in ("Bash", "PowerShell"):
        text = tool_input.get("command", "")
    else:  # tools MCP: inspeciona o payload inteiro (queries SQL vêm aqui)
        text = json.dumps(tool_input, ensure_ascii=False)

    if DEPLOY.search(text) and TARGET_PROD.search(text):
        block(
            "Deploy em prod é EXCLUSIVO da esteira de CI/CD (GitHub Actions + service principal). "
            "Faça commit e push; a esteira cuida do resto."
        )

    for pattern, reason in RULES:
        if re.search(pattern, text, re.IGNORECASE):
            block(reason)

    sys.exit(0)


def block(reason: str) -> None:
    print(f"GUARDRAIL ATIVADO — nada foi executado. {reason}", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # bug no próprio hook também falha fechado
        block(f"erro interno do hook ({exc!r}).")
