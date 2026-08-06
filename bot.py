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
            print(f"✅ '{pip_name}' instalado com sucesso!")
        except Exception as e:
            print(f"❌ Erro ao instalar via pip: {str(e)}")

instalar_modulo("telegram", "python-telegram-bot")
instalar_modulo("aiohttp")
instalar_modulo("nest_asyncio")
instalar_modulo("dotenv", "python-dotenv")

import asyncio
import re
import time
import json
import socket
import nest_asyncio
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
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"Bot do Giovani esta ONLINE e operante!")

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), DummyHandler)
    server.serve_forever()

# ==========================================
# 🛡️ CONFIGURAÇÃO DO BOT E CONTROLE PRIVADO
# ==========================================
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    print("❌ ERRO: Token do Telegram não encontrado. Verifique seu arquivo .env!")
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

        progresso_msg = await context.bot.send_message(chat_id=chat_id, text=f"🚀 **GIOVANI V15.6: INTEGRANDO...**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 PARAR", callback_data="stop_scan")]]), message_thread_id=thread_id)
        
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=60, ttl_dns_cache=300)) as session:
            teste_alvo = await testar_url_completo(session, dns_alvo, usuario, senha)
            status_dns_alvo, canais_alvo = ("ON" if teste_alvo["valido"] else "OFF"), teste_alvo.get("tv", 0)
            if teste_alvo["valido"]: dados_conta.update({k: teste_alvo.get(k, "N/A") for k in ["conexoes_ativas", "conexoes_maximas", "vencimento", "tipo_conta", "criacao", "formatos"]})
            
            for b in range(0, total_banco, 100):
                if not consultas_ativas.get(chat_id, True): break
                lote = todas_dns_txt[b:b+100]
                resultados = await asyncio.gather(*[testar_url_completo(session, u, usuario, senha) for u in lote])
                for res in resultados:
                    if res["valido"] and res["dns"] != dns_alvo and not any(c in res["dns"] for c in DOMINIOS_CURINGAS):
                        if res["tv"] > 5 and (canais_alvo == 0 or abs(res["tv"] - canais_alvo) <= 15 or res["tv"] >= 20):
                            espelhos_de_ouro.append(res)

        try: await progresso_msg.delete()
        except: pass
        consultas_ativas.pop(chat_id, None)

        status_dns_alvo = "ON" if status_dns_alvo == "OFF" and espelhos_de_ouro else status_dns_alvo
        relatorio = [f"🛡 **GIOVANI DETECTOR V15.6 SMART FILTER**", f"────────────────────", f"🛰 DNS ALVO: `{dns_alvo}` {'(🟢 ONLINE)' if status_dns_alvo == 'ON' else '(🔴 OFFLINE)'}"]
        if espelhos_de_ouro:
            relatorio.append(f"🔥 ESPELHOS DE OURO CONFIRMADOS ({len(espelhos_de_ouro)}):")
            for item in espelhos_de_ouro[:40]: relatorio.append(f" └🔗 `{item['dns']}` 📺 🔥")
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
    print(f"⚠️ Ocorreu um erro interno de conexão: {context.error}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    thread_id = update.message.message_thread_id if hasattr(update.message, "message_thread_id") else None
    salvar_grupo_id(chat.id, thread_id)
    await update.message.reply_text("🛡️ **GIOVANI DETECTOR V15.6 SMART FILTER OPERANTE**", message_thread_id=thread_id)

async def dnschecker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_autorizacao(update, context): return ConversationHandler.END
    await update.message.reply_text("📥 **Aguardando link M3U ativo...**")
    return GET_M3U_LINK

async def receber_m3u(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    if not re.compile(r"http[s]?://.*get\.php\?[^ ]*username=[^&]+&password=[^&]+").search(texto):
        await update.message.reply_text("❌ Link M3U Inválido.")
        return GET_M3U_LINK
    asyncio.create_task(processar_giovani_hibrido(texto, update.message.from_user.id, context, update.effective_chat.id))
    return ConversationHandler.END

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if chat_id in consultas_ativas:
        consultas_ativas[chat_id] = False
        await update.message.reply_text("🛑 Comando de parada enviado.")

def main():
    # Inicia o Servidor Falso em uma thread paralela
    threading.Thread(target=run_dummy_server, daemon=True).start()
    
    nest_asyncio.apply()
    asyncio.get_event_loop().run_until_complete(baixar_lista_automatica(forçar=True))
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("dnschecker", dnschecker)],
        states={GET_M3U_LINK: [MessageHandler(filters.TEXT & (~filters.COMMAND), receber_m3u)]},
        fallbacks=[CommandHandler("cancelar", cancelar)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancelar", cancelar))
    app.add_handler(conv_handler)
    app.add_error_handler(error_handler)

    print("✅ GIOVANI DETECTOR V15.6 SMART FILTER ONLINE")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
