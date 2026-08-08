# -*- coding: utf-8 -*-
import os
import sys
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# ==========================================
# 📦 SISTEMA DE AUTO-INSTALAÇÃO DE MÓDULOS
# ==========================================
def instalar_modulo(package, pip_name=None):
    if pip_name is None:
        pip_name = package
    try:
        __import__(package)
    except ImportError:
        print(f"📦 O módulo '{package}' não está instalado. Instalando '{pip_name}' automaticamente...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name])
        except:
            pass

instalar_modulo("telegram", "python-telegram-bot")
instalar_modulo("aiohttp")
instalar_modulo("dotenv", "python-dotenv")

import asyncio
import re
import time
import json
import socket
import aiohttp
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, parse_qs
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatMemberStatus
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, ConversationHandler, filters
)
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# 🌐 SERVIDOR WEB FALSO PARA ENGANAR O RENDER
# ==========================================
class DummyHandler(BaseHTTPRequestHandler):
    def _responder_online(self, incluir_corpo=True):
        corpo = b"Bot do Giovani esta ONLINE e operante!"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        if incluir_corpo:
            self.wfile.write(corpo)

    def do_GET(self):
        self._responder_online(incluir_corpo=True)

    # O Render usa HEAD para verificar a saude do Web Service.
    def do_HEAD(self):
        self._responder_online(incluir_corpo=False)

    def log_message(self, format, *args):
        # Mantem os logs do Render limpos sem esconder erros do bot.
        return

class RenderHTTPServer(HTTPServer):
    allow_reuse_address = True

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    server = RenderHTTPServer(("0.0.0.0", port), DummyHandler)
    server.serve_forever()

# Impede que o mesmo container inicie duas copias do polling por engano.
_instance_lock = None

def adquirir_bloqueio_de_instancia():
    global _instance_lock
    try:
        import fcntl
        _instance_lock = open("/tmp/giovani_detector.lock", "w")
        fcntl.flock(_instance_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _instance_lock.write(str(os.getpid()))
        _instance_lock.flush()
    except BlockingIOError:
        print("❌ Outra instancia do GIOVANI DETECTOR ja esta rodando neste servidor.")
        sys.exit(1)
    except (ImportError, OSError) as erro:
        # O Render usa Linux e suporta fcntl. Em outro sistema, o bot segue
        # funcionando normalmente caso esse bloqueio nao esteja disponivel.
        print(f"⚠️ Bloqueio de instancia indisponivel: {erro}")

# ==========================================
# 🛡️ CONFIGURAÇÃO DO BOT E CONTROLE PRIVADO
# ==========================================
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    sys.exit(1)

ARQUIVO_BANCO = "lista_dns.txt"
GRUPO_FILE = "grupo.txt"
LINK_LISTA_FIXA = "COLE_O_LINK_DO_SEU_TXT_AQUI"

admin_env = os.getenv("ADMIN_IDS", "8716721711")
ADMIN_IDS = [int(id.strip()) for id in admin_env.split(",") if id.strip().isdigit()]

GET_M3U_LINK = 0
DNS_BLACKLIST = ["brothersplay.com", "www.brothersplay.com"]
DOMINIOS_CURINGAS = ["adultiptv.net", "iptvxxx.net", "dimaiptv.com"]

HEADERS = {
    "User-Agent": "VLC",
    "X-User-Agent": "Model: MAG254; Link: Ethernet",
}

consultas_ativas = {}
user_timeout_tasks = {}
scan_tasks = set()

def finalizar_tarefa_scan(tarefa, chat_id):
    scan_tasks.discard(tarefa)
    consultas_ativas.pop(chat_id, None)
    if not tarefa.cancelled() and tarefa.exception() is not None:
        print(f"⚠️ Varredura encerrada com erro: {tarefa.exception()}")

def salvar_grupo_id(chat_id, thread_id=None):
    with open(GRUPO_FILE, "w") as f:
        f.write(f"{chat_id}:{thread_id or ''}")

def obter_grupo_id():
    if os.path.exists(GRUPO_FILE):
        with open(GRUPO_FILE, "r") as f:
            dados = f.read().strip().split(":")
            return int(dados[0]), int(dados[1]) if len(dados) > 1 and dados[1] else None
    return None, None

async def check_autorizacao(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat = update.effective_chat
    user = update.effective_user
    grupo_aut, thread_aut = obter_grupo_id()

    if chat.type in ["group", "supergroup"]:
        if chat.id != grupo_aut: return False
        message_obj = update.message or (update.callback_query.message if update.callback_query else None)
        thread_id = getattr(message_obj, "message_thread_id", None)
        if thread_aut and thread_aut != thread_id: return False
        return True

    if chat.type == "private":
        if user.id in ADMIN_IDS: return True
        try:
            membro = await context.bot.get_chat_member(chat.id, user.id)
            if membro.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]: return True
        except: pass
        return False
    return False

async def baixar_lista_automatica(forçar=False):
    if not LINK_LISTA_FIXA or "COLE_O_LINK" in LINK_LISTA_FIXA:
        if not os.path.exists(ARQUIVO_BANCO):
            with open(ARQUIVO_BANCO, "w", encoding="utf-8") as f: f.write("")
        return False
    if forçar and os.path.exists(ARQUIVO_BANCO):
        try: os.remove(ARQUIVO_BANCO)
        except: pass
    try:
        headers_github = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        async with aiohttp.ClientSession() as session:
            async with session.get(LINK_LISTA_FIXA, headers=headers_github, timeout=15) as response:
                if response.status == 200:
                    conteudo = await response.text()
                    with open(ARQUIVO_BANCO, "w", encoding="utf-8", errors="ignore") as f:
                        f.write(conteudo)
                    return True
    except: pass
    if not os.path.exists(ARQUIVO_BANCO):
        with open(ARQUIVO_BANCO, "w", encoding="utf-8") as f: f.write("")
    return False

def extrair_hosts(texto):
    try:
        linhas = texto.split('\n')
        hosts = []
        for line in linhas:
            linha_limpa = line.replace(",", " ").strip()
            host = re.sub(r'https?://', '', linha_limpa).split('/')[0].split('?')[0].strip().lower()
            if ":" in host: host = host.split(":")[0]
            if "." in host and len(host) > 4:
                if host not in DNS_BLACKLIST and not any(curinga in host for curinga in DOMINIOS_CURINGAS):
                    hosts.append(host)
        return list(set(hosts))
    except: return []

async def testar_url_completo(session, url_banco, user, password):
    url_base = f"http://{url_banco}/player_api.php?username={user}&password={password}"
    try:
        async with session.get(url_base, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=3.5)) as response:
            if response.status not in [200, 301, 302, 403, 406, 429, 503]:
                return {"dns": url_banco, "valido": False, "tv": 0, "vod": 0, "series": 0}
            texto_resposta = await response.text()
            is_valid = False
            active_cons, max_cons, exp_date = "N/A", "N/A", "N/A"
            created_at, is_trial, formatos = "N/A", "N/A", "N/A"
            total_tv, total_vod, total_series = 0, 0, 0
            try:
                dados_json = json.loads(texto_resposta)
                total_tv = int(dados_json.get("live_count", 0))
                total_vod = int(dados_json.get("vod_count", dados_json.get("movie_count", 0)))
                total_series = int(dados_json.get("series_count", 0))
                if "user_info" in dados_json:
                    info = dados_json["user_info"]
                    status_val = str(info.get("status", "")).strip().lower()
                    if status_val in ["active", "1", "true", "ativado", "on"]:
                        is_valid = True
                        active_cons = info.get("active_connections", "0")
                        max_cons = info.get("max_connections", "0")
                        if info.get("exp_date") and str(info.get("exp_date")).isdigit():
                            exp_date = datetime.fromtimestamp(int(info.get("exp_date"))).strftime("%d/%m/%Y")
                        if info.get("created_at") and str(info.get("created_at")).isdigit():
                            created_at = datetime.fromtimestamp(int(info.get("created_at"))).strftime("%d/%m/%Y")
                        is_trial = "Teste (Trial)" if str(info.get("is_trial", "0")).lower() in ["1", "true"] else "Oficial"
                        formatos = ", ".join(info.get("allowed_output_formats", [])) if isinstance(info.get("allowed_output_formats"), list) else info.get("allowed_output_formats", "m3u8, ts (Padrão)")
            except:
                if 'username' in texto_resposta.lower() and ('"active"' in texto_resposta.lower() or '"status": 1' in texto_resposta.lower() or 'active' in texto_resposta.lower()):
                    is_valid = True
            return {
                "dns": url_banco, "valido": is_valid, "conexoes_ativas": active_cons, "conexoes_maximas": max_cons, 
                "vencimento": exp_date, "tv": total_tv, "vod": total_vod, "series": total_series,
                "tipo_conta": is_trial, "criacao": created_at, "formatos": formatos
            }
    except: return {"dns": url_banco, "valido": False, "tv": 0, "vod": 0, "series": 0}

async def processar_giovani_hibrido(dados_entrada, user_id, context, chat_id):
    inicio = time.time()
    agora_br = datetime.now(timezone.utc) - timedelta(hours=3)
    dt_hr = agora_br.strftime("%d/%m/%Y | %H:%M:%S")
    _, thread_id = obter_grupo_id()

    if not os.path.exists(ARQUIVO_BANCO):
        await baixar_lista_automatica(forçar=True)
    try:
        with open(ARQUIVO_BANCO, "r", encoding="utf-8", errors="ignore") as f:
            todas_dns_txt = extrair_hosts(f.read())
    except: todas_dns_txt = []
    total_banco = len(todas_dns_txt)

    is_link_completo = "username=" in dados_entrada and "password=" in dados_entrada
    espelhos_de_ouro = []
    status_dns_alvo = "OFF"
    
    dados_conta = {"user": "N/A", "pass": "N/A", "ativas": "N/A", "max": "N/A", "vence": "N/A", "tipo": "N/A", "criacao": "N/A", "formatos": "N/A", "vod": 0, "series": 0}
    dados_rede = {"ip": "N/A", "isp": "N/A", "pais": "N/A", "hostname": "N/A"}

    if is_link_completo:
        try: dns_alvo = urlparse(dados_entrada).hostname.lower()
        except: dns_alvo = "N/A"
    else:
        dns_alvo = re.sub(r'https?://', '', dados_entrada.strip().split('\n')[0]).split('/')[0].split('?')[0].strip().lower()
        if ":" in dns_alvo: dns_alvo = dns_alvo.split(":")[0]

    try:
        dados_rede["ip"] = socket.gethostbyname(dns_alvo)
        try: dados_rede["hostname"] = socket.gethostbyaddr(dados_rede["ip"])[0]
        except: dados_rede["hostname"] = "Desconhecido"
        async with aiohttp.ClientSession() as session_geo:
            async with session_geo.get(f"http://ip-api.com/json/{dados_rede['ip']}?fields=isp,country", timeout=2.0) as res_geo:
                if res_geo.status == 200:
                    geo_json = await res_geo.json()
                    dados_rede["isp"], dados_rede["pais"] = geo_json.get("isp", "N/A"), geo_json.get("country", "N/A")
    except: pass

    if is_link_completo:
        consultas_ativas[chat_id] = True
        try:
            params = parse_qs(urlparse(dados_entrada).query)
            usuario, senha = params['username'][0], params['password'][0]
        except: return
        dados_conta["user"], dados_conta["pass"] = usuario, senha

        teclado_parar = InlineKeyboardMarkup([[InlineKeyboardButton("🛑 PARAR CONSULTA", callback_data="stop_scan")]])
        progresso_msg = await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "🚀 GIOVANI V15.6: INTEGRANDO E FILTRANDO ROTAS...\n\n"
                "░░░░░░░░░░ 0%\n"
                f"🔎 Processados: 0/{total_banco}"
            ),
            reply_markup=teclado_parar,
            message_thread_id=thread_id
        )
        ultima_atualizacao_progresso = 0.0
        
        # Limite conservador para evitar excesso de resolucoes DNS no Render.
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=30, ttl_dns_cache=300)) as session:
            teste_alvo = await testar_url_completo(session, dns_alvo, usuario, senha)
            status_dns_alvo, canais_alvo = ("ON" if teste_alvo["valido"] else "OFF"), teste_alvo.get("tv", 0)
            if teste_alvo["valido"]: dados_conta.update({k: teste_alvo.get(k, "N/A") for k in ["conexoes_ativas", "conexoes_maximas", "vencimento", "tipo_conta", "criacao", "formatos"]})
            
            for b in range(0, total_banco, 30):
                if not consultas_ativas.get(chat_id, True): break
                lote = todas_dns_txt[b:b+30]
                tarefas_lote = [
                    asyncio.create_task(testar_url_completo(session, u, usuario, senha))
                    for u in lote
                ]
                concluidas, pendentes = await asyncio.wait(tarefas_lote, timeout=6)
                for tarefa_pendente in pendentes:
                    tarefa_pendente.cancel()
                if pendentes:
                    # Nao aguarda cancelamentos presos na resolucao DNS.
                    # Uma passagem pelo loop entrega o cancelamento sem travar a barra.
                    await asyncio.sleep(0)
                resultados = []
                for tarefa_concluida in concluidas:
                    try:
                        resultados.append(tarefa_concluida.result())
                    except Exception as erro_lote:
                        resultados.append(erro_lote)
                for res in resultados:
                    if isinstance(res, BaseException):
                        continue
                    if res["valido"] and res["dns"] != dns_alvo and not any(c in res["dns"] for c in DOMINIOS_CURINGAS):
                        if res["tv"] > 5 and (canais_alvo == 0 or abs(res["tv"] - canais_alvo) <= 15 or res["tv"] >= 20):
                            espelhos_de_ouro.append(res)

                processados = min(b + len(lote), total_banco)
                agora_progresso = time.monotonic()
                if agora_progresso - ultima_atualizacao_progresso >= 3 or processados == total_banco:
                    percentual = int((processados / total_banco) * 100) if total_banco else 100
                    blocos = min(10, percentual // 10)
                    barra = "█" * blocos + "░" * (10 - blocos)
                    try:
                        await progresso_msg.edit_text(
                            "🚀 GIOVANI V15.6: INTEGRANDO E FILTRANDO ROTAS...\n\n"
                            f"{barra} {percentual}%\n"
                            f"🔎 Processados: {processados}/{total_banco}\n"
                            f"🔥 Espelhos encontrados: {len(espelhos_de_ouro)}",
                            reply_markup=teclado_parar
                        )
                        ultima_atualizacao_progresso = agora_progresso
                    except Exception as erro_progresso:
                        print(f"⚠️ Nao foi possivel atualizar o progresso: {erro_progresso}")

        try: await progresso_msg.delete()
        except: pass
        consultas_ativas.pop(chat_id, None)

        status_dns_alvo = "ON" if status_dns_alvo == "OFF" and espelhos_de_ouro else status_dns_alvo
        relatorio = [
            f"🛡 **GIOVANI DETECTOR V15.6 SMART FILTER**",
            f"────────────────────",
            f"👤 REQUISITANTE: `{user_id}`",
            f"📅 DATA/HORA: `{dt_hr}`",
            f"────────────────────",
            f"🛰 DNS ALVO: `{dns_alvo}` {'(🟢 ONLINE)' if status_dns_alvo == 'ON' else '(🔴 OFFLINE)'}",
            f"📍 IP: `{dados_rede['ip']}` | 📡 HOST: `{dados_rede['hostname']}`",
            f"🏢 ISP: `{dados_rede['isp']}` | 🌍 `{dados_rede['pais']}`",
            f"────────────────────",
            f"👤 USUÁRIO: `{dados_conta['user']}` | 🔑 SENHA: `{dados_conta['pass']}`",
            f"🏷 TIPO DA CONTA: `{dados_conta['tipo']}`",
            f"📅 CRIADA EM: `{dados_conta['criacao']}` | ⏳ VENCE EM: `{dados_conta['vence']}`",
            f"👥 CONEXÕES ATIVAS: `{dados_conta['ativas']}/{dados_conta['max']}`",
            f"📺 CANAIS: `{canais_alvo}` | 🎬 FILMES (VOD): `{dados_conta['vod']}` | 🎞 SÉRIES: `{dados_conta['series']}`",
            f"⚙️ FORMATOS SUPORTADOS: `{dados_conta['formatos']}`",
            f"────────────────────"
        ]
        if espelhos_de_ouro:
            relatorio.append(f"🔥 ESPELHOS DE OURO CONFIRMADOS ({len(espelhos_de_ouro)}):")
            for item in espelhos_de_ouro[:40]: relatorio.append(f" └🔗 `{item['dns']}` 📺 🔥 LIBERADA")
        else:
            relatorio.append(" ❌ Nenhum espelho válido com canais ativos respondeu para este login.")
        await context.bot.send_message(chat_id=chat_id, text="\n".join(relatorio), parse_mode='Markdown', message_thread_id=thread_id)

    else:
        status_dns_alvo = "OFF"
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session_teste:
            try:
                async with session_teste.get(f"http://{dns_alvo}", headers=HEADERS, timeout=aiohttp.ClientTimeout(total=2.5)) as resp:
                    if resp.status in [200, 301, 302, 403, 406, 429, 503]: status_dns_alvo = "ON"
            except: pass

        raiz_alvo = re.sub(r'\d+$', '', dns_alvo.split('.')[0])
        lista_texto = [d for d in todas_dns_txt if d != dns_alvo and d not in DNS_BLACKLIST and re.sub(r'\d+$', '', d.split('.')[0]) == raiz_alvo and len(raiz_alvo) >= 3]

        relatorio = [f"🛡 **GIOVANI DETECTOR V15.6 SMART FILTER**", f"────────────────────", f"🛰 DNS ALVO: `{dns_alvo}` {'(🟢 ONLINE)' if status_dns_alvo == 'ON' else '(🔴 OFFLINE)'}"]
        if lista_texto:
            relatorio.append(f"👥 PARALELAS POR PROXIMIDADE ({len(lista_texto)}):")
            for d in lista_texto[:40]: relatorio.append(f" └🔗 `{d}`")
        await context.bot.send_message(chat_id=chat_id, text="\n".join(relatorio), parse_mode='Markdown', message_thread_id=thread_id)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    erro = str(context.error)
    if "terminated by other getUpdates request" in erro or "Conflict" in erro:
        print(
            "⚠️ CONFLITO DO TELEGRAM: existe outra copia usando o mesmo token. "
            "Pare o outro servico/computador e deixe somente esta instancia ativa."
        )
        return
    print(f"⚠️ Ocorreu um erro interno de conexão: {erro}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    thread_id = update.message.message_thread_id if hasattr(update.message, "message_thread_id") else None
    salvar_grupo_id(chat.id, thread_id)
    await update.message.reply_text(
        "🛡️ **GIOVANI DETECTOR V15.6 SMART FILTER OPERANTE**\n\n"
        "• Envie um **domínio limpo** para verificar aproximação por texto.\n"
        "• Use o comando `/dnschecker` para rodar a varredura inteligente completa.",
        message_thread_id=thread_id if thread_id else None
    )

async def autorizar7(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type not in ["group", "supergroup"]: return
    membro = await context.bot.get_chat_member(chat.id, user.id)
    if membro.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER] and user.id not in ADMIN_IDS: return
    thread_id = update.message.message_thread_id if hasattr(update.message, "message_thread_id") else None
    salvar_grupo_id(chat.id, thread_id)
    await update.message.reply_text(f"✅ Grupo Autorizado com Sucesso!", message_thread_id=thread_id)

async def escutar_texto_direto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_autorizacao(update, context): return
    msg = update.message.text
    if msg and ("." in msg or "http" in msg) and not msg.startswith("/"):
        if "get.php" in msg:
            await update.message.reply_text("💡 Para testar listas M3U completas, use primeiro o comando `/dnschecker`.")
            return
        await processar_giovani_hibrido(msg, update.message.from_user.id, context, update.message.chat_id)

async def dnschecker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_autorizacao(update, context): return ConversationHandler.END
    await update.message.reply_text("📥 **Aguardando link M3U ativo para varredura...**")
    return GET_M3U_LINK

async def receber_m3u(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    if not re.compile(r"http[s]?://.*get\.php\?[^ ]*username=[^&]+&password=[^&]+").search(texto):
        await update.message.reply_text("❌ Link M3U Inválido.")
        return GET_M3U_LINK
    chat_id = update.effective_chat.id
    if consultas_ativas.get(chat_id):
        await update.message.reply_text("⏳ Já existe uma varredura em andamento neste chat.")
        return ConversationHandler.END
    consultas_ativas[chat_id] = True
    tarefa = asyncio.create_task(
        processar_giovani_hibrido(texto, update.message.from_user.id, context, chat_id),
        name=f"scan-{chat_id}"
    )
    scan_tasks.add(tarefa)
    tarefa.add_done_callback(lambda concluida: finalizar_tarefa_scan(concluida, chat_id))
    return ConversationHandler.END

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in consultas_ativas:
        consultas_ativas[chat_id] = False
        await update.message.reply_text("🛑 Comando de parada enviado ao motor.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    if query.data == "stop_scan":
        if chat_id in consultas_ativas:
            consultas_ativas[chat_id] = False
            await query.edit_message_text("🛑 Varredura interrompida. Aguardando finalização...")

async def gerenciar_atualizacao_documento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_autorizacao(update, context): return
    _, thread_id = obter_grupo_id()
    if update.message.document:
        await (await update.message.document.get_file()).download_to_drive(ARQUIVO_BANCO)
        with open(ARQUIVO_BANCO, "r", encoding="utf-8", errors="ignore") as f:
            total = len(extrair_hosts(f.read()))
        await update.message.reply_text(f"📥 **Banco Atualizado Manualmente!**\n📦 {total} domínios salvos em cache.", message_thread_id=thread_id)

async def iniciar_aplicacao(application):
    await baixar_lista_automatica(forçar=True)

async def encerrar_aplicacao(application):
    # Finaliza as varreduras antes de o python-telegram-bot fechar o event loop.
    for chat_id in list(consultas_ativas):
        consultas_ativas[chat_id] = False
    tarefas = [tarefa for tarefa in scan_tasks if not tarefa.done()]
    for tarefa in tarefas:
        tarefa.cancel()
    if tarefas:
        await asyncio.gather(*tarefas, return_exceptions=True)

def main():
    adquirir_bloqueio_de_instancia()
    threading.Thread(target=run_dummy_server, daemon=True).start()

    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .post_init(iniciar_aplicacao)
        .post_shutdown(encerrar_aplicacao)
        .build()
    )

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("dnschecker", dnschecker)],
        states={GET_M3U_LINK: [MessageHandler(filters.TEXT & (~filters.COMMAND), receber_m3u)]},
        fallbacks=[CommandHandler("cancelar", cancelar)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancelar", cancelar))
    app.add_handler(CommandHandler("autorizar7", autorizar7))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, gerenciar_atualizacao_documento))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), escutar_texto_direto))
    
    app.add_error_handler(error_handler)

    print("✅ GIOVANI DETECTOR V15.6 SMART FILTER ONLINE")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
